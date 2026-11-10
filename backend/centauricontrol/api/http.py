"""
CentauriControl – HTTP request handler.

All HTTP traffic (REST API, auth routes, static files, camera proxy, file
upload proxy) is served by a single ThreadingHTTPServer running in a daemon
thread.  The handler calls back into the asyncio loop via
asyncio.run_coroutine_threadsafe for broadcasts.
"""

from __future__ import annotations

import asyncio
import http
import http.client
import http.server
import json
import mimetypes
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, TYPE_CHECKING

from centauricontrol.config import HTTPS_PORT, PUBLIC_DIR, SPOOLMAN_URL
from centauricontrol.auth.manager import AuthManager, check_cookie, extract_token, SESSION_COOKIE, AUTH_ENABLED

if TYPE_CHECKING:
    from centauricontrol.persistence.store import DataStore
    from centauricontrol.integrations.manager import IntegrationManager
    from centauricontrol.printers.registry import PrinterRegistry


_LAYOUTS_FILE = "layouts.json"
_COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days
_MAX_JSON_BODY_BYTES = 1024 * 1024
_UPLOAD_CHUNK_BYTES = 64 * 1024
_MAX_UPLOAD_RESPONSE_BYTES = 1024 * 1024
_CAMERA_READ_TIMEOUT_SECONDS = 30
_CAMERA_CONNECT_RETRIES = 3
_CAMERA_RETRY_INITIAL_SECONDS = 0.5
_CAMERA_RETRY_MAX_SECONDS = 5


def make_handler_class(
    store: "DataStore",
    auth: AuthManager,
    registry: "PrinterRegistry",
    loop: asyncio.AbstractEventLoop,
    integration_manager: "IntegrationManager | None" = None,
) -> type[BaseHTTPRequestHandler]:
    """Factory: returns a request-handler class with dependencies baked in."""

    class SPHandler(BaseHTTPRequestHandler):
        _store = store
        _auth = auth
        _registry = registry
        _loop = loop
        _integrations = integration_manager

        # Silence access log spam
        def log_message(self, fmt: str, *args: Any) -> None:
            pass

        # ------------------------------------------------------------------
        # Routing
        # ------------------------------------------------------------------

        def do_GET(self) -> None:
            if self._redirect_to_https():
                return
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            if path == "/api/printers":
                return self._api_printers()
            if path == "/api/layout":
                return self._api_layout_get()
            if path == "/api/history":
                return self._api_history_get()
            if path == "/api/spoolman/spools":
                return self._api_spoolman_proxy("/api/v1/spool")
            if path == "/api/integrations":
                return self._api_integrations()
            if path == "/api/plugins":
                return self._api_plugins()
            if path.startswith("/camera/"):
                return self._camera_proxy(path)
            if path.startswith("/api/printers/") and path.endswith("/thumbnail"):
                return self._api_thumbnail(path)
            if path == "/api/auth/status":
                return self._api_auth_status()
            if path == "/health":
                return self._json(200, {"ok": True})
            # Static files
            return self._serve_static(path)

        def do_POST(self) -> None:
            if self._redirect_to_https():
                return
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            if path == "/api/auth/login":
                return self._api_login()
            if path == "/api/auth/logout":
                return self._api_logout()
            if path == "/api/auth/setup":
                return self._api_setup()
            if path == "/api/integrations/openfilamentsensor/test":
                return self._api_test_sensor_integration()
            if path == "/api/printers":
                return self._api_add_printer()
            if path.startswith("/api/printers/") and path.endswith("/print"):
                return self._api_start_print(path)
            if path.startswith("/api/upload/"):
                return self._api_upload_proxy(path)

            self._json(404, {"error": "Not found"})

        def do_PUT(self) -> None:
            if self._redirect_to_https():
                return
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            if path == "/api/layout":
                return self._api_layout_put()
            if path == "/api/integrations/openfilamentsensor":
                return self._api_configure_sensor_integration()
            if path.startswith("/api/printers/"):
                return self._api_update_printer(path)

            self._json(404, {"error": "Not found"})

        def do_DELETE(self) -> None:
            if self._redirect_to_https():
                return
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            if path.startswith("/api/printers/"):
                return self._api_delete_printer(path)

            self._json(404, {"error": "Not found"})

        # ------------------------------------------------------------------
        # Auth guard
        # ------------------------------------------------------------------

        def _redirect_to_https(self) -> bool:
            if isinstance(self.connection, ssl.SSLSocket):
                return False
            try:
                host = urllib.parse.urlsplit(f"//{self.headers.get('Host', '')}")
                target = urllib.parse.urlsplit(self.path)
                if (
                    not host.hostname
                    or host.username is not None
                    or host.password is not None
                    or not target.path.startswith("/")
                ):
                    raise ValueError("invalid request host or target")
            except ValueError:
                self._json(400, {"error": "Invalid request host or target"})
                return True
            hostname = f"[{host.hostname}]" if ":" in host.hostname else host.hostname
            location = f"https://{hostname}:{HTTPS_PORT}{target.path}"
            if target.query:
                location += f"?{target.query}"
            self.send_response(308)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.close_connection = True
            return True

        def _is_auth_exempt(self, path: str) -> bool:
            """Routes that don't need a session cookie."""
            return path in (
                "/api/auth/login",
                "/api/auth/setup",
                "/api/auth/status",
                "/health",
            ) or path.startswith("/login") or path.startswith("/setup")

        def _check_auth(self, path: str) -> bool:
            if not AUTH_ENABLED:
                return True
            if self._is_auth_exempt(path):
                return True
            return check_cookie(dict(self.headers))

        # ------------------------------------------------------------------
        # Auth endpoints
        # ------------------------------------------------------------------

        def _api_auth_status(self) -> None:
            has_pw = self._auth.has_password()
            authed = check_cookie(dict(self.headers))
            self._json(200, {
                "auth_enabled": AUTH_ENABLED,
                "has_password": has_pw,
                "authenticated": authed,
                "username": self._auth.get_username() if has_pw else None,
            })

        def _api_login(self) -> None:
            body = self._read_json()
            if body is None:
                return
            username = str(body.get("username", ""))
            password = str(body.get("password", ""))
            if not self._auth.verify(username, password):
                self._json(401, {"error": "Invalid credentials"})
                return
            token = self._auth.create_session()
            cookie = (
                f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Lax; "
                f"Max-Age={_COOKIE_MAX_AGE}"
            )
            self._json(200, {"ok": True}, extra_headers={"Set-Cookie": cookie})

        def _api_logout(self) -> None:
            cookie_header = self.headers.get("Cookie", "")
            token = extract_token(cookie_header)
            if token:
                self._auth.revoke_session(token)
            expired_cookie = (
                f"{SESSION_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0"
            )
            self._json(200, {"ok": True}, extra_headers={"Set-Cookie": expired_cookie})

        def _api_setup(self) -> None:
            if self._auth.has_password():
                # Setup already done — only allow if authenticated
                if not check_cookie(dict(self.headers)):
                    self._json(403, {"error": "Already configured; authenticate first"})
                    return
            body = self._read_json()
            if body is None:
                return
            username = str(body.get("username", "admin"))
            password = str(body.get("password", ""))
            try:
                self._auth.set_password(username, password)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            except RuntimeError as exc:
                self._json(500, {"error": str(exc)})
                return
            token = self._auth.create_session()
            cookie = (
                f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Lax; "
                f"Max-Age={_COOKIE_MAX_AGE}"
            )
            self._json(200, {"ok": True}, extra_headers={"Set-Cookie": cookie})

        # ------------------------------------------------------------------
        # Printer REST API
        # ------------------------------------------------------------------

        def _api_printers(self) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            self._json(200, {"printers": self._registry.all()})

        def _api_add_printer(self) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            body = self._read_json()
            if body is None:
                return
            ip = body.get("ip", "")
            if not isinstance(ip, str):
                self._json(400, {"error": "ip must be a string"})
                return
            ip = ip.strip()
            name = body.get("name", "")
            printer_type = body.get("printer_type", "cc1")
            access_code = body.get("access_code", "")
            if not isinstance(name, str) or not isinstance(printer_type, str) or not isinstance(access_code, str):
                self._json(400, {"error": "name, printer_type, and access_code must be strings"})
                return
            name = name or f"Printer @ {ip}"
            access_code = access_code or ""
            if not ip:
                self._json(400, {"error": "ip is required"})
                return
            if printer_type not in ("cc1", "cc2"):
                self._json(400, {"error": "printer_type must be cc1 or cc2"})
                return
            conn = self._registry.add(ip=ip, name=name, printer_type=printer_type, access_code=access_code)
            self._json(201, {"printer": conn.to_dict()})

        def _api_delete_printer(self, path: str) -> None:
            if not self._check_auth(path):
                self._json(401, {"error": "Unauthorized"})
                return
            printer_id = path.split("/api/printers/", 1)[-1].strip("/")
            removed = self._registry.remove(printer_id)
            if removed:
                asyncio.run_coroutine_threadsafe(
                    _broadcast_removed(printer_id), self._loop
                )
                self._json(200, {"ok": True})
            else:
                self._json(404, {"error": "Printer not found"})

        def _api_update_printer(self, path: str) -> None:
            if not self._check_auth(path):
                self._json(401, {"error": "Unauthorized"})
                return
            printer_id = path.split("/api/printers/", 1)[-1].strip("/")
            body = self._read_json()
            if body is None:
                return
            if body.get("name") is not None and not isinstance(body["name"], str):
                self._json(400, {"error": "name must be a string"})
                return
            if body.get("access_code") is not None and not isinstance(body["access_code"], str):
                self._json(400, {"error": "access_code must be a string"})
                return
            updated = self._registry.update(
                printer_id,
                name=body.get("name"),
                access_code=body.get("access_code"),
            )
            if updated:
                conn = self._registry.get(printer_id)
                self._json(200, {"printer": conn.to_dict() if conn else {}})
            else:
                self._json(404, {"error": "Printer not found"})

        def _api_start_print(self, path: str) -> None:
            if not self._check_auth(path):
                self._json(401, {"error": "Unauthorized"})
                return
            # /api/printers/{id}/print
            parts = path.split("/")
            printer_id = parts[3] if len(parts) > 3 else ""
            conn = self._registry.get(printer_id)
            if conn is None:
                self._json(404, {"error": "Printer not found"})
                return
            body = self._read_json()
            if body is None:
                return
            filename = body.get("filename", "")
            if not isinstance(filename, str) or not filename:
                self._json(400, {"error": "filename required"})
                return
            start_layer = body.get("start_layer", 0)
            if isinstance(start_layer, bool) or not isinstance(start_layer, int) or start_layer < 0:
                self._json(400, {"error": "start_layer must be a non-negative integer"})
                return
            asyncio.run_coroutine_threadsafe(
                conn.send_cmd(1, {"Filename": filename, "StartLayer": start_layer}),
                self._loop,
            )
            self._json(200, {"ok": True})

        # ------------------------------------------------------------------
        # Layout API
        # ------------------------------------------------------------------

        def _api_layout_get(self) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            data = self._store.read(_LAYOUTS_FILE)
            if data is None:
                data = {"version": 1, "activeLayoutId": "default", "layouts": []}
            self._json(200, data)

        def _api_layout_put(self) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            body = self._read_json()
            if body is None:
                return
            self._store.write(_LAYOUTS_FILE, body)
            self._json(200, {"ok": True})

        # ------------------------------------------------------------------
        # History API
        # ------------------------------------------------------------------

        def _api_history_get(self) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            data = self._store.read("history.json")
            if not isinstance(data, list):
                data = []
            self._json(200, data)

        # ------------------------------------------------------------------
        # Spoolman proxy
        # ------------------------------------------------------------------

        def _api_spoolman_proxy(self, spoolman_path: str) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            url = f"{SPOOLMAN_URL}{spoolman_path}"
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self._json(200, data)
            except Exception as exc:
                self._json(502, {"error": f"Spoolman unavailable: {exc}"})

        # ------------------------------------------------------------------
        # Built-in integrations
        # ------------------------------------------------------------------

        def _api_integrations(self) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            if self._integrations is None:
                self._json(503, {"error": "Integrations are not initialized"})
                return
            printer_ids = [str(printer["id"]) for printer in self._registry.all()]
            self._json(200, self._integrations.catalog(printer_ids))

        def _api_configure_sensor_integration(self) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            if self._integrations is None:
                self._json(503, {"error": "Integrations are not initialized"})
                return
            body = self._read_json()
            if body is None:
                return
            if not isinstance(body, dict):
                self._json(400, {"error": "Expected a JSON object"})
                return
            printer_id = str(body.get("printer_id", "")).strip()
            if self._registry.get(printer_id) is None:
                self._json(404, {"error": "Printer not found"})
                return
            enabled = body.get("enabled")
            base_url = body.get("base_url", "")
            if not isinstance(base_url, str):
                self._json(400, {"error": "base_url must be a string"})
                return
            try:
                self._integrations.configure_sensor(printer_id, enabled, base_url)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            printer_ids = [str(printer["id"]) for printer in self._registry.all()]
            self._json(200, self._integrations.catalog(printer_ids))

        def _api_test_sensor_integration(self) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            body = self._read_json()
            if body is None:
                return
            if not isinstance(body, dict):
                self._json(400, {"error": "Expected a JSON object"})
                return
            base_url = body.get("base_url", "")
            if not isinstance(base_url, str):
                self._json(400, {"error": "base_url must be a string"})
                return
            from centauricontrol.integrations.manager import (
                fetch_sensor_status,
                validate_sensor_url,
            )
            try:
                normalized_url = validate_sensor_url(base_url)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            try:
                status = fetch_sensor_status(normalized_url)
            except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
                self._json(502, {"error": f"Sensor is unavailable or returned invalid data: {exc}"})
                return
            self._json(200, {"ok": True, "status": status})

        # ------------------------------------------------------------------
        # Plugins list
        # ------------------------------------------------------------------

        def _api_plugins(self) -> None:
            if not self._check_auth(self.path):
                self._json(401, {"error": "Unauthorized"})
                return
            from centauricontrol.plugins.loader import get_plugin_manifests
            self._json(200, {"plugins": get_plugin_manifests()})

        # ------------------------------------------------------------------
        # Thumbnail route
        # ------------------------------------------------------------------

        def _api_thumbnail(self, path: str) -> None:
            if not self._check_auth(path):
                self._json(401, {"error": "Unauthorized"})
                return
            import base64
            parts = path.strip("/").split("/")
            # /api/printers/{id}/thumbnail
            if len(parts) < 4:
                self._json(404, {"error": "Not found"})
                return
            printer_id = parts[2]
            conn = self._registry.get(printer_id)
            if conn is None or not conn.thumbnail_b64:
                self._json(404, {"error": "No thumbnail"})
                return
            try:
                data = base64.b64decode(conn.thumbnail_b64)
            except Exception:
                self._json(500, {"error": "Bad thumbnail data"})
                return
            # Detect PNG vs JPEG by magic bytes
            mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        # ------------------------------------------------------------------
        # Camera proxy (MJPEG passthrough)
        # ------------------------------------------------------------------

        def _camera_proxy(self, path: str) -> None:
            if not self._check_auth(path):
                self._json(401, {"error": "Unauthorized"})
                return
            # /camera/{printer_id}/stream
            parts = path.strip("/").split("/")
            if len(parts) < 2:
                self._json(404, {"error": "Not found"})
                return
            printer_id = parts[1]
            conn = self._registry.get(printer_id)
            if conn is None or not conn.camera_url:
                self._json(404, {"error": "Camera not available"})
                return
            request = urllib.request.Request(
                conn.camera_url,
                headers={"Accept": "multipart/x-mixed-replace", "Connection": "keep-alive"},
            )
            content_type: str | None = None
            response_started = False
            startup_failures = 0
            retry_delay = _CAMERA_RETRY_INITIAL_SECONDS
            stream_opened_at: float | None = None

            while True:
                try:
                    with urllib.request.urlopen(
                        request,
                        timeout=_CAMERA_READ_TIMEOUT_SECONDS,
                    ) as upstream:
                        upstream_content_type = upstream.headers.get(
                            "Content-Type",
                            "multipart/x-mixed-replace",
                        )
                        if content_type is None:
                            content_type = upstream_content_type
                        elif upstream_content_type != content_type:
                            print(
                                f"[Camera] Stream format changed for printer {printer_id}; "
                                "restarting the browser stream"
                            )
                            return

                        stream_opened_at = time.monotonic()
                        if not response_started:
                            self.send_response(200)
                            self.send_header("Content-Type", content_type)
                            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                            self.send_header("X-Accel-Buffering", "no")
                            self.end_headers()
                            response_started = True

                        while True:
                            chunk = upstream.read(4096)
                            if not chunk:
                                raise ConnectionError("Camera stream ended")
                            try:
                                self.wfile.write(chunk)
                                self.wfile.flush()
                            except OSError:
                                return
                except urllib.error.HTTPError as exc:
                    if 500 <= exc.code < 600:
                        if not response_started:
                            startup_failures += 1
                        else:
                            print(f"[Camera] Upstream returned HTTP {exc.code} for printer {printer_id}")
                    else:
                        if response_started:
                            print(f"[Camera] Upstream returned HTTP {exc.code} for printer {printer_id}")
                            return
                        self._json(502, {"error": f"Camera stream returned HTTP {exc.code}"})
                        return
                except (OSError, TimeoutError, http.client.HTTPException, urllib.error.URLError) as exc:
                    if not response_started:
                        startup_failures += 1
                    else:
                        print(f"[Camera] Stream interrupted for printer {printer_id}: {exc}")

                if not response_started and startup_failures >= _CAMERA_CONNECT_RETRIES:
                    self._json(502, {"error": "Camera stream unavailable after repeated connection attempts"})
                    return

                if stream_opened_at is not None and time.monotonic() - stream_opened_at >= 30:
                    retry_delay = _CAMERA_RETRY_INITIAL_SECONDS
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, _CAMERA_RETRY_MAX_SECONDS)

        # ------------------------------------------------------------------
        # File upload proxy (POST /api/upload/{printer_id})
        # ------------------------------------------------------------------

        def _api_upload_proxy(self, path: str) -> None:
            if not self._check_auth(path):
                self._json(401, {"error": "Unauthorized"})
                return
            parts = path.strip("/").split("/")
            if len(parts) < 3:
                self._json(400, {"error": "printer_id required"})
                return
            printer_id = parts[2]
            conn = self._registry.get(printer_id)
            if conn is None:
                self._json(404, {"error": "Printer not found"})
                return
            try:
                content_length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self._json(400, {"error": "Invalid Content-Length"})
                return
            if content_length <= 0:
                self._json(400, {"error": "A positive Content-Length is required"})
                return
            content_type = self.headers.get("Content-Type", "application/octet-stream")
            if "\r" in content_type or "\n" in content_type:
                self._json(400, {"error": "Invalid Content-Type"})
                return

            printer_connection = http.client.HTTPConnection(conn.ip, 58080, timeout=30)
            try:
                printer_connection.putrequest("POST", "/uploadFile/upload")
                printer_connection.putheader("Content-Type", content_type)
                printer_connection.putheader("Content-Length", str(content_length))
                printer_connection.endheaders()
                remaining = content_length
                while remaining:
                    chunk = self.rfile.read(min(_UPLOAD_CHUNK_BYTES, remaining))
                    if not chunk:
                        raise ConnectionError("Upload body ended before Content-Length bytes arrived")
                    printer_connection.send(chunk)
                    remaining -= len(chunk)

                response = printer_connection.getresponse()
                if response.status >= 400:
                    raise http.client.HTTPException(
                        f"Printer upload returned HTTP {response.status}"
                    )
                response_body = response.read(_MAX_UPLOAD_RESPONSE_BYTES + 1)
                if len(response_body) > _MAX_UPLOAD_RESPONSE_BYTES:
                    raise ValueError("Printer upload response exceeded the size limit")
                result = json.loads(response_body.decode("utf-8"))
                self._json(200, result)
            except (OSError, ValueError, http.client.HTTPException) as exc:
                self._json(502, {"error": f"Upload failed: {exc}"})
            finally:
                printer_connection.close()

        # ------------------------------------------------------------------
        # Static file serving (SPA fallback)
        # ------------------------------------------------------------------

        def _serve_static(self, path: str) -> None:
            # Strip leading slash
            rel = path.lstrip("/")
            public_dir = PUBLIC_DIR.resolve()
            file_path = (public_dir / rel if rel else public_dir / "index.html").resolve()
            try:
                file_path.relative_to(public_dir)
            except ValueError:
                self._respond(404, "text/plain", b"Not found")
                return

            # SPA fallback: if the path has no extension and no file exists, serve index.html
            if not file_path.exists() or file_path.is_dir():
                file_path = public_dir / "index.html"

            if not file_path.exists():
                self._respond(404, "text/plain", b"Not found")
                return

            mime, _ = mimetypes.guess_type(str(file_path))
            mime = mime or "application/octet-stream"
            try:
                content = file_path.read_bytes()
                self._respond(200, mime, content)
            except OSError:
                self._respond(500, "text/plain", b"Server error")

        # ------------------------------------------------------------------
        # Response helpers
        # ------------------------------------------------------------------

        def _json(
            self,
            status: int,
            data: Any,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._respond(status, "application/json", body, extra_headers)

        def _respond(
            self,
            status: int,
            content_type: str,
            body: bytes,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if extra_headers:
                for key, value in extra_headers.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self._json(400, {"error": "Invalid JSON body"})
                return None
            if length < 0:
                self._json(400, {"error": "Invalid JSON body"})
                return None
            if length > _MAX_JSON_BODY_BYTES:
                self.close_connection = True
                self._json(413, {"error": "JSON body is too large"})
                return None
            try:
                raw = self.rfile.read(length)
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(400, {"error": "Invalid JSON body"})
                return None
            if not isinstance(data, dict):
                self._json(400, {"error": "Expected a JSON object"})
                return None
            return data

    return SPHandler


# ---------------------------------------------------------------------------
# Broadcast helpers (called from threads via run_coroutine_threadsafe)
# ---------------------------------------------------------------------------

async def _broadcast_removed(printer_id: str) -> None:
    from centauricontrol.websocket.handler import broadcast_to_browsers
    await broadcast_to_browsers({"type": "printer_removed", "printer_id": printer_id})
