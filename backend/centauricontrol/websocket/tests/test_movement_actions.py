from __future__ import annotations

import json

import pytest

from centauricontrol.websocket import handler


class _Printer:
    connected = True
    status: dict[str, object] = {}

    def __init__(self) -> None:
        self.commands: list[tuple[int, dict[str, object]]] = []

    async def send_cmd(self, cmd: int, data: dict[str, object]) -> None:
        self.commands.append((cmd, data))


class _Registry:
    def __init__(self, printer: _Printer) -> None:
        self.printer = printer

    def get(self, _printer_id: str) -> _Printer:
        return self.printer


class _WebSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)

    async def close(self, code: int, reason: str) -> None:
        self.close_info = (code, reason)

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


@pytest.mark.parametrize(
    ("message", "expected_command"),
    [
        (
            {"action": "jog", "printer_id": "printer-1", "axis": "X", "distance": -0.1},
            (401, {"Axis": "X", "Step": -0.1}),
        ),
        (
            {"action": "home", "printer_id": "printer-1", "axis": "Z"},
            (402, {"Axis": "Z"}),
        ),
    ],
)
async def test_movement_actions_send_captured_sdcp_payloads(
    monkeypatch: pytest.MonkeyPatch,
    message: dict[str, object],
    expected_command: tuple[int, dict[str, object]],
) -> None:
    printer = _Printer()
    monkeypatch.setattr(handler, "_registry", _Registry(printer))
    websocket = _WebSocket()

    await handler._dispatch(websocket, message)

    assert printer.commands == [expected_command]
    assert websocket.messages == []


@pytest.mark.parametrize(
    "message",
    [
        {"action": "jog", "printer_id": "printer-1", "axis": "A", "distance": 1},
        {"action": "jog", "printer_id": "printer-1", "axis": "X", "distance": 0},
        {"action": "jog", "printer_id": "printer-1", "axis": "X", "distance": 1.5},
        {"action": "jog", "printer_id": "printer-1", "axis": "X", "distance": 10**1000},
        {"action": "jog", "printer_id": "printer-1", "axis": "X", "distance": True},
        {"action": "home", "printer_id": "printer-1"},
    ],
)
async def test_invalid_movement_actions_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    message: dict[str, object],
) -> None:
    printer = _Printer()
    monkeypatch.setattr(handler, "_registry", _Registry(printer))
    websocket = _WebSocket()

    await handler._dispatch(websocket, message)

    assert printer.commands == []
    assert json.loads(websocket.messages[0])["type"] == "error"


async def test_movement_actions_are_rejected_while_printer_is_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = _Printer()
    printer.status = {"PrintInfo": {"Status": 3}}
    monkeypatch.setattr(handler, "_registry", _Registry(printer))
    websocket = _WebSocket()

    await handler._dispatch(
        websocket,
        {"action": "home", "printer_id": "printer-1", "axis": "Z"},
    )

    assert printer.commands == []
    assert "only available while the printer is idle" in json.loads(websocket.messages[0])["message"]


async def test_movement_actions_are_rejected_during_machine_homing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = _Printer()
    printer.status = {"PrintInfo": {"Status": 0}, "CurrentStatus": [9]}
    monkeypatch.setattr(handler, "_registry", _Registry(printer))
    websocket = _WebSocket()

    await handler._dispatch(
        websocket,
        {"action": "home", "printer_id": "printer-1", "axis": "Z"},
    )

    assert printer.commands == []
    assert "only available while the printer is idle" in json.loads(websocket.messages[0])["message"]


async def test_browser_websocket_rejects_unauthenticated_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    websocket = _WebSocket()
    websocket.request = type("Request", (), {"headers": {"Cookie": ""}})()
    monkeypatch.setattr(handler, "check_cookie", lambda _headers: False)

    await handler.browser_handler(websocket)

    assert websocket.close_info == (4401, "Unauthorized")


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Host": "printer.local:8765", "Origin": "http://printer.local:5173"}, True),
        ({"Host": "printer.local:8765", "Origin": "https://printer.local:8443"}, True),
        ({"Host": "printer.local:8765", "Origin": "http://attacker.local:8080"}, False),
        ({"Host": "printer.local:8765", "Origin": "http://printer.local:8080"}, False),
        ({"Host": "printer.local:8765", "Origin": "http://printer.local:9000"}, False),
    ],
)
def test_websocket_origin_is_limited_to_dashboard_origins(
    headers: dict[str, str],
    expected: bool,
) -> None:
    assert handler._is_allowed_origin(headers) is expected


async def test_start_print_rejects_invalid_start_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = _Printer()
    monkeypatch.setattr(handler, "_registry", _Registry(printer))
    websocket = _WebSocket()

    await handler._dispatch(
        websocket,
        {
            "action": "start_print",
            "printer_id": "printer-1",
            "filename": "test.gcode",
            "start_layer": "invalid",
        },
    )

    assert printer.commands == []
    assert "start_layer" in json.loads(websocket.messages[0])["message"]
