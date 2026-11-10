"""
CentauriControl – browser WebSocket handler.

Manages all browser-facing WebSocket connections.  Handles inbound action
messages (printer commands, discovery, layout updates) and broadcasts printer
state updates to all connected clients.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Optional, TYPE_CHECKING
from urllib.parse import urlsplit

from centauricontrol.auth.manager import check_cookie
from centauricontrol.config import HTTPS_PORT
from centauricontrol.printers import sdcp

if TYPE_CHECKING:
    from centauricontrol.printers.registry import PrinterRegistry

# ---------------------------------------------------------------------------
# Global state (set at startup via set_registry)
# ---------------------------------------------------------------------------

_registry: Optional["PrinterRegistry"] = None
_integration_status_provider: Optional[Callable[[], list[dict[str, Any]]]] = None
_connected_browsers: set = set()  # set of websockets connection objects
_broadcast_lock = asyncio.Lock()


def set_registry(registry: "PrinterRegistry") -> None:
    """Wire the registry into this module at startup."""
    global _registry
    _registry = registry


def set_integration_status_provider(
    provider: Callable[[], list[dict[str, Any]]],
) -> None:
    """Wire the integration status snapshot provider at startup."""
    global _integration_status_provider
    _integration_status_provider = provider


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------

async def broadcast_to_browsers(msg: dict[str, Any]) -> None:
    """Send *msg* as JSON to every connected browser client."""
    if not _connected_browsers:
        return
    payload = json.dumps(msg)
    dead: set = set()
    for ws in list(_connected_browsers):
        try:
            await ws.send(payload)
        except Exception:
            dead.add(ws)
    _connected_browsers.difference_update(dead)


# ---------------------------------------------------------------------------
# Connection handler
# ---------------------------------------------------------------------------

async def browser_handler(ws: Any) -> None:
    """Asyncio handler called for each new browser WebSocket connection."""
    request = getattr(ws, "request", None)
    headers = getattr(request, "headers", None)
    if headers is None:
        headers = getattr(ws, "request_headers", {})
    request_headers = dict(headers)
    if not _is_allowed_origin(request_headers) or not check_cookie(request_headers):
        await ws.close(code=4401, reason="Unauthorized")
        return

    _connected_browsers.add(ws)
    try:
        # On connect, push the current state of all printers
        if _registry is not None:
            for printer_state in _registry.all():
                await ws.send(json.dumps({"type": "printer_update", "printer": printer_state}))
        if _integration_status_provider is not None:
            for status in _integration_status_provider():
                await ws.send(json.dumps({"type": "integration_update", "status": status}))

        async for raw in ws:
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                await ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            if not isinstance(msg, dict) or "action" not in msg:
                await ws.send(json.dumps({"type": "error", "message": "Missing 'action' field"}))
                continue

            try:
                await _dispatch(ws, msg)
            except Exception as exc:
                await ws.send(json.dumps({"type": "error", "message": str(exc)}))

    except Exception:
        pass
    finally:
        _connected_browsers.discard(ws)


def _is_allowed_origin(headers: dict[str, str]) -> bool:
    origin = headers.get("Origin") or headers.get("origin")
    if not origin:
        return True
    try:
        parsed_origin = urlsplit(origin)
        origin_port = parsed_origin.port
        request_host = urlsplit(f"//{headers.get('Host', '')}").hostname
    except ValueError:
        return False
    if (
        parsed_origin.scheme not in ("http", "https")
        or not parsed_origin.hostname
        or not request_host
        or parsed_origin.hostname.casefold() != request_host.casefold()
    ):
        return False
    if parsed_origin.scheme == "https":
        return origin_port in (None, 443, HTTPS_PORT)
    return origin_port == 5173


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

async def _dispatch(ws: Any, msg: dict[str, Any]) -> None:
    """Route a browser action message to the appropriate handler."""
    action: str = msg.get("action", "")
    reg = _registry

    # ── Discovery / printer management ────────────────────────────────────

    if action == "list_printers":
        if reg is not None:
            for state in reg.all():
                await ws.send(json.dumps({"type": "printer_update", "printer": state}))
        return

    if action == "discover":
        await _handle_discover(ws)
        return

    if action == "add_printer":
        await _handle_add_printer(ws, msg)
        return

    if action == "remove_printer":
        await _handle_remove_printer(ws, msg)
        return

    if action == "update_printer":
        await _handle_update_printer(ws, msg)
        return

    # ── Printer commands (require printer_id) ────────────────────────────

    printer_id: str = msg.get("printer_id", "")
    if not printer_id or reg is None:
        await ws.send(json.dumps({"type": "error", "message": "printer_id required"}))
        return

    conn = reg.get(printer_id)
    if conn is None:
        await ws.send(json.dumps({
            "type": "error",
            "printer_id": printer_id,
            "message": f"Printer '{printer_id}' not found",
        }))
        return

    # Simple no-arg commands
    if action == "pause":
        await conn.send_cmd(sdcp.CMD_PAUSE, {})
    elif action == "resume":
        await conn.send_cmd(sdcp.CMD_RESUME, {})
    elif action == "stop":
        await conn.send_cmd(sdcp.CMD_STOP, {})
    elif action == "status":
        await conn.send_cmd(sdcp.CMD_STATUS, {})
    elif action == "stop_feed":
        await conn.send_cmd(sdcp.CMD_STOP_FEED, {})
    elif action == "skip_preheat":
        await conn.send_cmd(sdcp.CMD_SKIP_PREHEAT, {})
    elif action == "light_on":
        await conn.send_cmd(sdcp.CMD_LIGHT, {"LightStatus": {"SecondLight": True, "RgbLight": [0, 0, 0]}})
    elif action == "light_off":
        await conn.send_cmd(sdcp.CMD_LIGHT, {"LightStatus": {"SecondLight": False, "RgbLight": [0, 0, 0]}})
    elif action == "camera_on":
        await conn.send_cmd(sdcp.CMD_CAMERA, {"Enable": 1})
    elif action == "camera_off":
        await conn.send_cmd(sdcp.CMD_CAMERA, {"Enable": 0})
    elif action == "timelapse_on":
        await conn.send_cmd(sdcp.CMD_TIMELAPSE, {"Enable": 1})
    elif action == "timelapse_off":
        await conn.send_cmd(sdcp.CMD_TIMELAPSE, {"Enable": 0})

    elif action == "set_speed":
        pct = int(msg.get("speed_pct", 100))
        await conn.send_cmd(sdcp.CMD_SET_RUNTIME, {"PrintSpeedPct": pct})

    elif action == "set_fans":
        fan_data: dict[str, Any] = {}
        for key in ("ModelFan", "AuxiliaryFan", "BoxFan"):
            if key in msg:
                fan_data[key] = int(msg[key])
        if fan_data:
            await conn.send_cmd(sdcp.CMD_SET_RUNTIME, {"TargetFanSpeed": fan_data})

    elif action in ("jog", "home"):
        axis = msg.get("axis")
        if axis not in ("X", "Y", "Z"):
            await ws.send(json.dumps({
                "type": "error",
                "printer_id": printer_id,
                "message": "A valid axis (X, Y, or Z) is required.",
            }))
            return

        if not conn.connected:
            await ws.send(json.dumps({
                "type": "error",
                "printer_id": printer_id,
                "message": "Cannot move axes while the printer is offline.",
            }))
            return

        print_info = conn.status.get("PrintInfo", {})
        status_code = print_info.get("Status") if isinstance(print_info, dict) else None
        current_status = conn.status.get("CurrentStatus", [])
        if (
            (status_code is not None and status_code not in (0, 8, 9, 14))
            or (isinstance(current_status, list) and current_status[:1] == [9])
        ):
            await ws.send(json.dumps({
                "type": "error",
                "printer_id": printer_id,
                "message": "Axis movement and homing are only available while the printer is idle.",
            }))
            return

        if action == "home":
            await conn.send_cmd(sdcp.CMD_EDIT_PRINTER_AXIS_ZERO, {"Axis": axis})
            return

        distance = msg.get("distance")
        if (
            isinstance(distance, bool)
            or not isinstance(distance, (int, float))
            or distance not in (-100, -10, -1, -0.1, 0.1, 1, 10, 100)
        ):
            await ws.send(json.dumps({
                "type": "error",
                "printer_id": printer_id,
                "message": "Jog distance must be one of ±0.1, ±1, ±10, or ±100 mm.",
            }))
            return

        await conn.send_cmd(
            sdcp.CMD_EDIT_PRINTER_AXIS_NUMBER,
            {"Axis": axis, "Step": distance},
        )

    elif action == "set_printer_name":
        name = str(msg.get("name", ""))
        if name:
            await conn.send_cmd(sdcp.CMD_SET_NAME, {"Name": name})

    elif action == "start_print":
        filename = msg.get("filename", "")
        if not isinstance(filename, str):
            await ws.send(json.dumps({
                "type": "error",
                "printer_id": printer_id,
                "message": "filename must be a string",
            }))
            return
        start_layer = msg.get("start_layer", 0)
        if isinstance(start_layer, bool) or not isinstance(start_layer, int) or start_layer < 0:
            await ws.send(json.dumps({
                "type": "error",
                "printer_id": printer_id,
                "message": "start_layer must be a non-negative integer",
            }))
            return
        if filename:
            await conn.send_cmd(sdcp.CMD_START, {"Filename": filename, "StartLayer": start_layer})

    elif action == "list_files":
        url = str(msg.get("url", "/"))
        await conn.send_cmd(sdcp.CMD_LIST_FILES, {"Url": url})

    elif action == "delete_files":
        files: list = msg.get("files", [])
        if files:
            await conn.send_cmd(sdcp.CMD_DELETE_FILES, {"FileList": files})

    elif action == "printer_history":
        await conn.send_cmd(sdcp.CMD_HISTORY_LIST, {})

    elif action == "history_detail":
        ids: list = msg.get("ids", [])
        if ids:
            await conn.send_cmd(sdcp.CMD_HISTORY_DETAIL, {"IdList": ids})

    else:
        await ws.send(json.dumps({"type": "error", "message": f"Unknown action: {action}"}))


# ---------------------------------------------------------------------------
# Complex action handlers
# ---------------------------------------------------------------------------

async def _handle_discover(ws: Any) -> None:
    """Run UDP discovery in a thread and push results to the client."""
    await ws.send(json.dumps({"type": "info", "message": "Scanning network…"}))
    loop = asyncio.get_running_loop()
    from centauricontrol.printers.discovery import discover_printers
    found = await loop.run_in_executor(None, discover_printers)
    for printer in found:
        await ws.send(json.dumps({"type": "discovered", "printer": printer}))
    await ws.send(json.dumps({"type": "info", "message": f"Discovery complete — {len(found)} printer(s) found"}))


async def _handle_add_printer(ws: Any, msg: dict[str, Any]) -> None:
    ip = str(msg.get("ip", "")).strip()
    name = str(msg.get("name", "") or f"Printer @ {ip}")
    printer_type = str(msg.get("printer_type", "cc1"))
    access_code = str(msg.get("access_code", "") or "")

    if not ip:
        await ws.send(json.dumps({"type": "error", "message": "ip is required"}))
        return
    if printer_type not in ("cc1", "cc2"):
        await ws.send(json.dumps({"type": "error", "message": "printer_type must be cc1 or cc2"}))
        return

    if _registry is None:
        return
    conn = _registry.add(ip=ip, name=name, printer_type=printer_type, access_code=access_code)
    await ws.send(json.dumps({"type": "printer_update", "printer": conn.to_dict()}))


async def _handle_remove_printer(ws: Any, msg: dict[str, Any]) -> None:
    printer_id = str(msg.get("printer_id", ""))
    if not printer_id or _registry is None:
        return
    removed = _registry.remove(printer_id)
    if removed:
        await broadcast_to_browsers({"type": "printer_removed", "printer_id": printer_id})
    else:
        await ws.send(json.dumps({"type": "error", "message": f"Printer '{printer_id}' not found"}))


async def _handle_update_printer(ws: Any, msg: dict[str, Any]) -> None:
    printer_id = str(msg.get("printer_id", ""))
    name = msg.get("name")
    access_code = msg.get("access_code")
    if not printer_id or _registry is None:
        return
    if name is not None and not isinstance(name, str):
        await ws.send(json.dumps({"type": "error", "message": "name must be a string"}))
        return
    if access_code is not None and not isinstance(access_code, str):
        await ws.send(json.dumps({"type": "error", "message": "access_code must be a string"}))
        return
    updated = _registry.update(printer_id, name=name, access_code=access_code)
    if not updated:
        await ws.send(json.dumps({"type": "error", "message": f"Printer '{printer_id}' not found"}))
