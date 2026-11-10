"""
CentauriControl – CC1Connection (SDCP / WebSocket).

Manages a persistent WebSocket connection to an Elegoo Centauri Carbon CC1
printer using the SDCP v3 protocol.  Reconnects automatically on drop with
exponential backoff, heartbeat keepalive, and comprehensive logging.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import websockets
from websockets.asyncio.client import connect as ws_connect

from centauricontrol.config import CC1_PORT
from centauricontrol.logging_config import get_logger
from centauricontrol.printers.base import PrinterConnection, StateChangeCallback
from centauricontrol.printers import sdcp


_HEARTBEAT_INTERVAL = 10.0   # seconds between heartbeat pings
_HEARTBEAT_TIMEOUT = 5.0     # seconds to wait for pong before timeout
_COMMAND_TIMEOUT = 5.0       # seconds to wait for command response
_STATUS_INTERVAL = 5.0       # seconds between proactive status polls
_ATTRS_INTERVAL  = 60.0      # seconds between proactive attrs polls
_INITIAL_RECONNECT_DELAY = 1.0      # seconds for first retry
_MAX_RECONNECT_DELAY = 60.0          # max seconds between retries
_FAILURE_THRESHOLD = 3               # consecutive failures before increased backoff


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
        self._logger = get_logger(f"cc1.{ip}")
        self._pending_responses: dict[str, asyncio.Future] = {}
        self._reconnect_delay = _INITIAL_RECONNECT_DELAY
        self._consecutive_failures = 0

    # ------------------------------------------------------------------
    # PrinterConnection interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect and loop forever, reconnecting on any drop with exponential backoff."""
        while True:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                self._logger.info("Cancelled, shutting down")
                raise
            except Exception as exc:
                self._consecutive_failures += 1
                self._logger.error(
                    f"Connection error (attempt {self._consecutive_failures}): {exc!r}. "
                    f"Retrying in {self._reconnect_delay:.1f}s…"
                )
            finally:
                if self.connected:
                    self._set_connected(False)
            
            await asyncio.sleep(self._reconnect_delay)
            self._update_reconnect_delay()

    async def send_cmd(self, cmd: int, data: dict[str, Any]) -> dict[str, Any]:
        """Send an SDCP command to the printer via the open WebSocket.
        
        Now with timeout handling and optional response correlation.
        Retries once on timeout.
        """
        if self._ws is None:
            self._logger.warning(f"send_cmd({cmd}) skipped — not connected")
            return {}
        
        try:
            request_id = str(uuid.uuid4())
            payload = sdcp.make_msg(cmd, data, mainboard_id=self.mainboard_id, request_id=request_id)
            
            self._logger.debug(f"Sending Cmd {cmd} (RequestID: {request_id})")
            
            # Create future for response correlation (if request_id present)
            response_future: asyncio.Future = asyncio.Future()
            self._pending_responses[request_id] = response_future
            
            try:
                await self._ws.send(payload)
            except Exception as send_exc:
                self._pending_responses.pop(request_id, None)
                self._logger.error(f"send_cmd({cmd}) failed to send: {send_exc!r}")
                return {}
            
            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(response_future, timeout=_COMMAND_TIMEOUT)
                self._logger.debug(f"Received response for Cmd {cmd}")
                return response
            except asyncio.TimeoutError:
                self._pending_responses.pop(request_id, None)
                self._logger.warning(f"Cmd {cmd} timeout (RequestID: {request_id}); retrying once...")
                
                # Single retry
                try:
                    response_future = asyncio.Future()
                    self._pending_responses[request_id] = response_future
                    await self._ws.send(payload)
                    response = await asyncio.wait_for(response_future, timeout=_COMMAND_TIMEOUT)
                    self._logger.info(f"Cmd {cmd} retry succeeded")
                    return response
                except Exception as retry_exc:
                    self._pending_responses.pop(request_id, None)
                    self._logger.error(f"Cmd {cmd} retry failed: {retry_exc!r}")
                    return {}
        except Exception as exc:
            self._logger.error(f"send_cmd({cmd}) unexpected error: {exc!r}", exc_info=True)
            return {}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_reconnect_delay(self) -> None:
        """Update reconnect delay with exponential backoff."""
        if self._consecutive_failures >= _FAILURE_THRESHOLD:
            self._reconnect_delay = min(
                self._reconnect_delay * 2,  # Double delay
                _MAX_RECONNECT_DELAY,       # Cap at max
            )
        else:
            self._reconnect_delay = _INITIAL_RECONNECT_DELAY

    async def _connect_and_run(self) -> None:
        uri = f"ws://{self.ip}:{CC1_PORT}/websocket"
        self._logger.info(f"Connecting to {uri}…")

        try:
            # ping_interval=None: printer's embedded WS server does not respond
            # to protocol-level PING frames. We use application-level heartbeat instead.
            async with ws_connect(uri, open_timeout=10, ping_interval=None) as ws:
                self._ws = ws
                self._consecutive_failures = 0  # Reset on successful connect
                self._reconnect_delay = _INITIAL_RECONNECT_DELAY
                self._set_connected(True)
                self._logger.info("Connected")

                await self.send_cmd(sdcp.CMD_ATTRS, {})
                await self.send_cmd(sdcp.CMD_STATUS, {})

                recv_task = asyncio.create_task(self._recv_loop(ws))
                poll_task = asyncio.create_task(self._poll_loop())
                heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                try:
                    done, pending = await asyncio.wait(
                        [recv_task, poll_task, heartbeat_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                    # Re-raise if any task exited with an error
                    for t in done:
                        t.result()
                finally:
                    recv_task.cancel()
                    poll_task.cancel()
                    heartbeat_task.cancel()
        finally:
            self._ws = None

    async def _recv_loop(self, ws: Any) -> None:
        """Receive messages from the printer indefinitely."""
        self._logger.debug("Receive loop started")
        try:
            async for raw in ws:
                try:
                    self._handle_message(raw)
                except Exception as exc:
                    self._logger.error(f"Message handling error: {exc!r}", exc_info=True)
        except Exception as exc:
            self._logger.error(f"Receive loop error: {exc!r}", exc_info=True)
            raise

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat pings to detect stale connections."""
        self._logger.debug("Heartbeat loop started")
        while True:
            try:
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                if self._ws is None:
                    break
                
                self._logger.debug("Sending heartbeat ping")
                try:
                    await asyncio.wait_for(self._ws.send("ping"), timeout=2.0)
                except asyncio.TimeoutError:
                    self._logger.warning("Heartbeat send timed out")
                    break
                except Exception as exc:
                    self._logger.error(f"Heartbeat send failed: {exc!r}")
                    break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.error(f"Heartbeat loop error: {exc!r}", exc_info=True)
                break

    async def _poll_loop(self) -> None:
        """Send periodic status/attrs requests as an application-level keepalive."""
        self._logger.debug("Poll loop started")
        last_attrs = time.monotonic()
        try:
            while True:
                await asyncio.sleep(_STATUS_INTERVAL)
                await self.send_cmd(sdcp.CMD_STATUS, {})
                if time.monotonic() - last_attrs >= _ATTRS_INTERVAL:
                    await self.send_cmd(sdcp.CMD_ATTRS, {})
                    last_attrs = time.monotonic()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._logger.error(f"Poll loop error: {exc!r}", exc_info=True)
            raise

    def _handle_message(self, raw: str | bytes) -> None:
        """Parse an incoming SDCP message and update local state.

        Handles:
          - Heartbeat pong responses
          - Status updates (Topic: sdcp/status/{id})
          - Attribute updates (Topic: sdcp/attributes/{id})
          - Command responses with RequestID correlation
        """
        # Handle heartbeat pong
        if raw == "pong":
            self._logger.debug("Received heartbeat pong")
            return
        
        try:
            msg: dict = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._logger.warning(f"Failed to parse JSON message: {raw!r}")
            return

        # Check for RequestID in Data section (response correlation)
        if isinstance(msg.get("Data"), dict):
            request_id = msg["Data"].get("RequestID")
            if request_id and request_id in self._pending_responses:
                future = self._pending_responses.pop(request_id)
                if not future.done():
                    self._logger.debug(f"Received response for RequestID {request_id}")
                    future.set_result(msg.get("Data", {}))
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
