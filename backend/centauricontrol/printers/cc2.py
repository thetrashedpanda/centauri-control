"""
CentauriControl – CC2Connection (MQTT / aiomqtt).

Manages a persistent MQTT connection to an Elegoo Centauri Carbon CC2 printer.
The CC2 uses a local MQTT broker embedded in the printer; we subscribe to
status/attribute topics and publish commands via the SDCP request topic.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from centauricontrol.config import MQTT_PORT
from centauricontrol.printers.base import PrinterConnection, StateChangeCallback
from centauricontrol.printers import sdcp


_RECONNECT_DELAY = 5.0
_STATUS_INTERVAL = 5.0
_ATTRS_INTERVAL  = 60.0

# MQTT topics (CC2 firmware standard)
_TOPIC_STATUS   = "sdcp/status/{mainboard_id}"
_TOPIC_ATTRS    = "sdcp/attributes/{mainboard_id}"
_TOPIC_RESPONSE = "sdcp/response/{mainboard_id}"
_TOPIC_REQUEST  = "sdcp/request/{mainboard_id}"

# CC2 discovery topic — the printer announces itself here periodically
_TOPIC_ANNOUNCE = "sdcp/bcast/cc"


class CC2Connection(PrinterConnection):
    """MQTT connection to a Centauri Carbon CC2 printer."""

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
        self._client: Any = None

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
                print(f"[CC2:{self.ip}] Connection error: {exc!r}. Retrying in {_RECONNECT_DELAY}s…")
            finally:
                if self.connected:
                    self._set_connected(False)
            await asyncio.sleep(_RECONNECT_DELAY)

    async def send_cmd(self, cmd: int, data: dict[str, Any]) -> None:
        """Publish an SDCP command to the printer's request topic."""
        if self._client is None:
            print(f"[CC2:{self.ip}] send_cmd({cmd}) skipped — not connected")
            return
        try:
            payload = sdcp.make_msg(cmd, data, mainboard_id=self.mainboard_id)
            topic = _TOPIC_REQUEST.format(mainboard_id=self.mainboard_id)
            await self._client.publish(topic, payload)
        except Exception as exc:
            print(f"[CC2:{self.ip}] send_cmd({cmd}) failed: {exc!r}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _connect_and_run(self) -> None:
        try:
            import aiomqtt
        except ImportError:
            print(f"[CC2:{self.ip}] aiomqtt not installed — CC2 connection impossible")
            await asyncio.sleep(3600)
            return

        print(f"[CC2:{self.ip}] Connecting to MQTT broker…")

        # CC2 MQTT broker uses access_code as the password
        mqtt_kwargs: dict[str, Any] = {
            "hostname": self.ip,
            "port": MQTT_PORT,
        }
        if self.access_code:
            mqtt_kwargs["username"] = "bblp"
            mqtt_kwargs["password"] = self.access_code

        async with aiomqtt.Client(**mqtt_kwargs) as client:
            self._client = client
            self._set_connected(True)
            print(f"[CC2:{self.ip}] MQTT connected.")

            # Subscribe to the broadcast topic first to discover mainboard ID
            await client.subscribe(_TOPIC_ANNOUNCE)

            # If we already know the mainboard ID (reconnecting), subscribe immediately
            if self.mainboard_id:
                await self._subscribe_printer_topics(client)
                await self.send_cmd(sdcp.CMD_ATTRS, {})
                await self.send_cmd(sdcp.CMD_STATUS, {})

            last_status_poll = time.monotonic()
            last_attrs_poll  = time.monotonic()

            async for message in client.messages:
                try:
                    await self._handle_message(str(message.topic), message.payload)
                except Exception as exc:
                    print(f"[CC2:{self.ip}] Message handling error: {exc!r}")

                now = time.monotonic()
                if self.mainboard_id and now - last_status_poll >= _STATUS_INTERVAL:
                    await self.send_cmd(sdcp.CMD_STATUS, {})
                    last_status_poll = now
                if self.mainboard_id and now - last_attrs_poll >= _ATTRS_INTERVAL:
                    await self.send_cmd(sdcp.CMD_ATTRS, {})
                    last_attrs_poll = now

        self._client = None

    async def _subscribe_printer_topics(self, client: Any) -> None:
        mid = self.mainboard_id
        await client.subscribe(_TOPIC_STATUS.format(mainboard_id=mid))
        await client.subscribe(_TOPIC_ATTRS.format(mainboard_id=mid))
        await client.subscribe(_TOPIC_RESPONSE.format(mainboard_id=mid))

    async def _handle_message(self, topic: str, payload: bytes | bytearray | str) -> None:
        """Parse an incoming MQTT message and update local state."""
        try:
            raw = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
            msg: dict = json.loads(raw)
        except Exception:
            return

        # Announcement broadcast — extract mainboard ID and subscribe
        if topic == _TOPIC_ANNOUNCE or "MainboardID" in msg:
            await self._handle_announce(msg)
            return

        # Status push
        if _TOPIC_STATUS.replace("{mainboard_id}", self.mainboard_id) in topic:
            data = msg.get("Data", msg)
            if isinstance(data, dict):
                sdcp._deep_merge(self.status, data)
                self._update_filament()
                self._emit()
            return

        # Attributes push
        if _TOPIC_ATTRS.replace("{mainboard_id}", self.mainboard_id) in topic:
            data = msg.get("Data", msg)
            if isinstance(data, dict):
                self._apply_attrs(data)
            return

        # Response to a command we sent
        if _TOPIC_RESPONSE.replace("{mainboard_id}", self.mainboard_id) in topic:
            data = msg.get("Data", {})
            inner = data.get("Data", {}) if isinstance(data, dict) else {}
            if isinstance(inner, dict) and inner:
                if "MainboardID" in inner:
                    self._apply_attrs(inner)
                else:
                    sdcp._deep_merge(self.status, inner)
                    self._update_filament()
                    self._emit()

    async def _handle_announce(self, msg: dict[str, Any]) -> None:
        """Handle a CC2 discovery broadcast to get the mainboard ID."""
        new_id = msg.get("MainboardID") or msg.get("Data", {}).get("MainboardID", "")
        if not new_id or new_id == self.mainboard_id:
            return

        self.mainboard_id = new_id
        self.camera_url = f"http://{self.ip}:8080/video_stream"
        if self._client is not None:
            await self._subscribe_printer_topics(self._client)
            await self.send_cmd(sdcp.CMD_ATTRS, {})
            await self.send_cmd(sdcp.CMD_STATUS, {})

    def _apply_attrs(self, attrs: dict[str, Any]) -> None:
        sdcp._deep_merge(self.attrs, attrs)
        if "MainboardID" in attrs:
            self.mainboard_id = attrs["MainboardID"]
        if "Name" in attrs:
            self.name = attrs["Name"]
        self._emit()

    def _update_filament(self) -> None:
        pi = self.status.get("PrintInfo")
        if not isinstance(pi, dict):
            return
        mm = pi.get("TotalExtrusion", 0)
        if isinstance(mm, (int, float)) and mm > 0:
            self.filament_mm = float(mm)
            self.filament_g = sdcp.filament_mm_to_grams(self.filament_mm)
