from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from centauricontrol.api import http


def _handler(monkeypatch, tmp_path):
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    monkeypatch.setattr(http, "PUBLIC_DIR", public_dir)
    handler_class = http.make_handler_class(None, None, None, None)
    handler = object.__new__(handler_class)
    responses: list[tuple[int, str, bytes]] = []
    handler._respond = lambda status, content_type, body, *_args: responses.append(
        (status, content_type, body)
    )
    return handler, responses, public_dir


def test_static_file_serving_rejects_paths_outside_public_directory(
    monkeypatch, tmp_path
) -> None:
    handler, responses, public_dir = _handler(monkeypatch, tmp_path)
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")
    (public_dir / "index.html").write_text("dashboard", encoding="utf-8")

    handler._serve_static("../secret.txt")

    assert responses == [(404, "text/plain", b"Not found")]


def test_static_file_serving_keeps_spa_fallback(monkeypatch, tmp_path) -> None:
    handler, responses, public_dir = _handler(monkeypatch, tmp_path)
    (public_dir / "index.html").write_text("dashboard", encoding="utf-8")

    handler._serve_static("/dashboard")

    assert responses == [(200, "text/html", b"dashboard")]


def test_thumbnail_requires_authentication(monkeypatch, tmp_path) -> None:
    handler, responses, _public_dir = _handler(monkeypatch, tmp_path)
    handler.path = "/api/printers/printer-1/thumbnail"
    handler._check_auth = lambda _path: False

    handler._api_thumbnail(handler.path)

    assert responses == [(401, "application/json", b'{"error": "Unauthorized"}')]


def test_plain_http_requests_redirect_to_https() -> None:
    handler_class = http.make_handler_class(None, None, None, None)
    handler = object.__new__(handler_class)
    handler.connection = object()
    handler.headers = {"Host": "printer.local:8080"}
    handler.path = "/api/auth/status?check=1"
    response_headers: list[tuple[str, str]] = []
    status_codes: list[int] = []
    handler.send_response = status_codes.append
    handler.send_header = lambda name, value: response_headers.append((name, value))
    handler.end_headers = lambda: None
    handler.close_connection = False

    redirected = handler._redirect_to_https()

    assert redirected is True
    assert status_codes == [308]
    assert ("Location", f"https://printer.local:{http.HTTPS_PORT}/api/auth/status?check=1") in response_headers
    assert handler.close_connection is True


def test_json_reader_rejects_non_object_bodies(monkeypatch, tmp_path) -> None:
    handler, responses, _public_dir = _handler(monkeypatch, tmp_path)
    handler.headers = {"Content-Length": "2"}
    handler.rfile = BytesIO(b"[]")

    assert handler._read_json() is None
    assert responses[0][0] == 400


def test_json_reader_rejects_oversized_bodies_without_reading(
    monkeypatch, tmp_path
) -> None:
    handler, responses, _public_dir = _handler(monkeypatch, tmp_path)
    handler.headers = {"Content-Length": str(http._MAX_JSON_BODY_BYTES + 1)}
    handler.close_connection = False

    class _UnreadableBody:
        def read(self, _length: int) -> bytes:
            raise AssertionError("oversized body should not be read")

    handler.rfile = _UnreadableBody()

    assert handler._read_json() is None
    assert responses[0][0] == 413
    assert handler.close_connection is True


def test_upload_proxy_streams_request_body_in_bounded_chunks(
    monkeypatch, tmp_path
) -> None:
    handler, _responses, _public_dir = _handler(monkeypatch, tmp_path)
    content = b"x" * (http._UPLOAD_CHUNK_BYTES * 2 + 3)
    chunks: list[bytes] = []

    class _UpstreamResponse:
        status = 200

        def read(self, _length: int) -> bytes:
            return b'{"ok": true}'

    class _UpstreamConnection:
        def __init__(self, _host: str, _port: int, timeout: int) -> None:
            assert timeout == 30

        def putrequest(self, method: str, path: str) -> None:
            assert (method, path) == ("POST", "/uploadFile/upload")

        def putheader(self, _name: str, _value: str) -> None:
            return None

        def endheaders(self) -> None:
            return None

        def send(self, chunk: bytes) -> None:
            chunks.append(chunk)

        def getresponse(self) -> _UpstreamResponse:
            return _UpstreamResponse()

        def close(self) -> None:
            return None

    monkeypatch.setattr(http.http.client, "HTTPConnection", _UpstreamConnection)
    handler.path = "/api/upload/printer-1"
    handler._check_auth = lambda _path: True
    handler._registry = SimpleNamespace(
        get=lambda _printer_id: SimpleNamespace(ip="printer.local")
    )
    handler.headers = {
        "Content-Length": str(len(content)),
        "Content-Type": "application/octet-stream",
    }
    handler.rfile = BytesIO(content)
    responses: list[tuple[int, str, bytes]] = []
    handler._json = lambda status, data, *_args: responses.append(
        (status, "application/json", http.json.dumps(data).encode("utf-8"))
    )

    handler._api_upload_proxy(handler.path)

    assert b"".join(chunks) == content
    assert all(len(chunk) <= http._UPLOAD_CHUNK_BYTES for chunk in chunks)
    assert responses == [(200, "application/json", b'{"ok": true}')]
