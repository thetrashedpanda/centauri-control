"""
CentauriControl – CC1Connection (SDCP / WebSocket).

Manages a persistent WebSocket connection to an Elegoo Centauri Carbon CC1
printer using the SDCP v3 protocol.  Reconnects automatically on drop.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import websockets
from websockets.asyncio.client import connect as ws_connect

from centauricontrol.config import CC1_PORT
from centauricontrol.printers.base import PrinterConnection, StateChangeCallback
from centauricontrol.printers import sdcp


_RECONNECT_DELAY = 5.0   # seconds between reconnect attempts
_STATUS_INTERVAL = 5.0   # seconds between proactive status polls
_ATTRS_INTERVAL  = 60.0  # seconds between proactive attrs polls


class CC1Connection(PrinterConnection):
    """WebSocket connection to a Centauri Carbon CC1 printer (SDCP/WS)."""

    def __init__(
        self,
        printer_id: str,
        ip: str,
        name: str,
        printer_type: str,
        access_code: str,
        on_state_change: StateChangeCallback,
    ) -> None:
        super().__init__(printer_id, ip, name, printer_type, access_code, on_state_change)
        self._ws: Any = None   # websockets connection object
        self._last_print_status: int | None = None

    # ------------------------------------------------------------------
    # PrinterConnection interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect and loop forever, reconnecting on any drop."""
        while True:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[CC1:{self.ip}] Connection error: {exc!r}. Retrying in {_RECONNECT_DELAY}s…")
            finally:
                if self.connected:
                    self._set_connected(False)
            await asyncio.sleep(_RECONNECT_DELAY)

    async def send_cmd(self, cmd: int, data: dict[str, Any]) -> None:
        """Send an SDCP command to the printer via the open WebSocket."""
        if self._ws is None:
            print(f"[CC1:{self.ip}] send_cmd({cmd}) skipped — not connected")
            return
        try:
            payload = sdcp.make_msg(cmd, data, mainboard_id=self.mainboard_id)
            await self._ws.send(payload)
        except Exception as exc:
            print(f"[CC1:{self.ip}] send_cmd({cmd}) failed: {exc!r}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _connect_and_run(self) -> None:
        uri = f"ws://{self.ip}:{CC1_PORT}/websocket"
        print(f"[CC1:{self.ip}] Connecting to {uri}…")

        # ping_interval=None: the printer's embedded WS server does not respond
        # to protocol-level PING frames, causing spurious disconnects every ~30s.
        # The periodic status polls below serve as an application-level keepalive.
        async with ws_connect(uri, open_timeout=10, ping_interval=None) as ws:
            self._ws = ws
            self._set_connected(True)
            print(f"[CC1:{self.ip}] Connected.")

            await self.send_cmd(sdcp.CMD_ATTRS, {})
            await self.send_cmd(sdcp.CMD_STATUS, {})

            recv_task = asyncio.create_task(self._recv_loop(ws))
            poll_task = asyncio.create_task(self._poll_loop())
            try:
                done, pending = await asyncio.wait(
                    [recv_task, poll_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                # Re-raise if the recv loop exited with an error
                for t in done:
                    t.result()
            finally:
                recv_task.cancel()
                poll_task.cancel()

        self._ws = None

    async def _recv_loop(self, ws: Any) -> None:
        """Receive messages from the printer indefinitely."""
        async for raw in ws:
            try:
                self._handle_message(raw)
            except Exception as exc:
                print(f"[CC1:{self.ip}] Message handling error: {exc!r}")

    async def _poll_loop(self) -> None:
        """Send periodic status/attrs requests as an application-level keepalive."""
        last_attrs = time.monotonic()
        while True:
            await asyncio.sleep(_STATUS_INTERVAL)
            await self.send_cmd(sdcp.CMD_STATUS, {})
            if time.monotonic() - last_attrs >= _ATTRS_INTERVAL:
                await self.send_cmd(sdcp.CMD_ATTRS, {})
                last_attrs = time.monotonic()

    def _handle_message(self, raw: str | bytes) -> None:
        """Parse an incoming SDCP message and update local state.

        The printer routes messages by ``Topic`` string, matching the same
        envelope shape used over MQTT for CC2 printers:
          - "sdcp/status/{id}"     -> top-level "Status" key
          - "sdcp/attributes/{id}" -> top-level "Attributes" key
          - "sdcp/response/{id}"   -> "Data.Cmd" / "Data.Data" (command replies)
        """
        try:
            msg: dict = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return

        topic = msg.get("Topic", "")

        if "sdcp/status" in topic:
            status = msg.get("Status")
            if isinstance(status, dict):
                self._apply_status(status)
            return

        if "sdcp/attributes" in topic:
            attrs = msg.get("Attributes")
            if isinstance(attrs, dict):
                self._apply_attrs(attrs)
            return

        # "sdcp/response" or any other shape: fall back to Data.Cmd/Data.Data,
        # and also handle pushes that omit Topic but include Status/Attributes
        # directly (older firmware).
        if isinstance(msg.get("Status"), dict):
            self._apply_status(msg["Status"])
            return
        if isinstance(msg.get("Attributes"), dict):
            self._apply_attrs(msg["Attributes"])
            return

        data = msg.get("Data", {})
        if not isinstance(data, dict):
            return
        inner = data.get("Data", {})
        if not isinstance(inner, dict):
            inner = {}
        cmd = data.get("Cmd")
        if cmd == sdcp.CMD_HISTORY_DETAIL:
            self._apply_task_detail(inner)
        elif cmd == sdcp.CMD_STATUS or "PrintInfo" in inner or "TempOfNozzle" in inner:
            self._apply_status(inner)
        elif cmd == sdcp.CMD_ATTRS or "MainboardID" in inner:
            self._apply_attrs(inner)

    def _apply_status(self, status: dict[str, Any]) -> None:
        """Merge incoming status payload into self.status and emit."""
        if "PrintInfo" in status:
            pi = status["PrintInfo"]
            if isinstance(pi, dict):
                status["PrintInfo"] = sdcp.decode_printinfo(pi)

        old_task_id = self.status.get("PrintInfo", {}).get("TaskId")
        sdcp._deep_merge(self.status, status)
        self._update_filament()
        self._emit()

        new_task_id = self.status.get("PrintInfo", {}).get("TaskId")
        if new_task_id and new_task_id != old_task_id:
            import asyncio
            asyncio.ensure_future(
                self.send_cmd(sdcp.CMD_HISTORY_DETAIL, {"Id": new_task_id})
            )

    def _apply_task_detail(self, inner: dict[str, Any]) -> None:
        """Extract thumbnail from a CMD_HISTORY_DETAIL response and emit."""
        items = inner.get("HistoryDetailList", [])
        if not items or not isinstance(items, list):
            return
        thumbnail = items[0].get("Thumbnail", "")
        if thumbnail and thumbnail != self.thumbnail_b64:
            self.thumbnail_b64 = thumbnail
            self._emit()

    def _apply_attrs(self, attrs: dict[str, Any]) -> None:
        """Merge incoming attrs payload into self.attrs and emit."""
        sdcp._deep_merge(self.attrs, attrs)
        if "MainboardID" in attrs:
            self.mainboard_id = attrs["MainboardID"]
        if "Name" in attrs:
            self.name = attrs["Name"]
        # Use the URL the printer reports; fall back to the well-known path.
        reported = attrs.get("VideoStreamUrl") or attrs.get("CameraStreamUrl")
        self.camera_url = reported or f"http://{self.ip}:3031/video"
        self._emit()

    def _update_filament(self) -> None:
        """Update running filament counters from the latest PrintInfo."""
        pi = self.status.get("PrintInfo")
        if not isinstance(pi, dict):
            return
        mm = pi.get("TotalExtrusion", 0)
        if isinstance(mm, (int, float)) and mm > 0:
            self.filament_mm = float(mm)
            self.filament_g = sdcp.filament_mm_to_grams(self.filament_mm)
