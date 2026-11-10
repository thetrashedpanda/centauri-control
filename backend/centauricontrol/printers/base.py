"""
CentauriControl – PrinterConnection abstract base class.

Every concrete printer driver (CC1, CC2) inherits from PrinterConnection and
must implement the abstract methods defined here.  The base class owns the
common state shape (status, attrs, connected flag) and the serialisation
method used by the broadcast layer.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


StateChangeCallback = Callable[[dict[str, Any]], None]


class PrinterConnection(ABC):
    """Abstract base for a single managed printer connection.

    Subclasses implement :meth:`start` (which loops forever reconnecting) and
    :meth:`send_cmd` (which serialises and sends a command to the printer).

    Args:
        printer_id:  Unique identifier (IP or mainboard ID).
        ip:          IP address string.
        name:        Human-readable display name.
        printer_type: ``"cc1"`` or ``"cc2"``.
        access_code: MQTT password for CC2; empty string for CC1.
        on_state_change: Callback fired whenever printer state changes.
                         Called with the result of :meth:`to_dict`.
    """

    def __init__(
        self,
        printer_id: str,
        ip: str,
        name: str,
        printer_type: str,
        access_code: str,
        on_state_change: StateChangeCallback,
    ) -> None:
        self.id: str = printer_id
        self.ip: str = ip
        self.name: str = name
        self.printer_type: str = printer_type
        self.access_code: str = access_code
        self._on_state_change: StateChangeCallback = on_state_change

        # Mutable state — updated by concrete subclass as messages arrive.
        self.connected: bool = False
        self.status: dict[str, Any] = {}
        self.attrs: dict[str, Any] = {}
        self.mainboard_id: str = ""
        self.camera_url: Optional[str] = None

        # Running filament counters (reset each print, accumulated by driver).
        self.filament_mm: float = 0.0
        self.filament_g: float = 0.0

        # Base64-encoded thumbnail for the current/last print task.
        self.thumbnail_b64: str = ""

        # Timestamp of the last broadcast; used to rate-limit state emissions.
        self._last_emit_time: float = 0.0
        self._pending_emit: bool = False

        # asyncio task that owns the connection lifecycle.
        self._task: Optional[asyncio.Task[None]] = None

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement these
    # ------------------------------------------------------------------

    @abstractmethod
    async def start(self) -> None:
        """Connect to the printer and loop forever (reconnecting on drop).

        Implementations should catch all connection errors internally and
        sleep before retrying.  ``asyncio.CancelledError`` must be allowed to
        propagate so :class:`PrinterRegistry` can cancel tasks cleanly.
        """

    @abstractmethod
    async def send_cmd(self, cmd: int, data: dict[str, Any]) -> None:
        """Send a command to the printer.

        Args:
            cmd:  SDCP command integer (one of the ``CMD_*`` constants).
            data: Command-specific payload dict.
        """

    # ------------------------------------------------------------------
    # Common helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise current state to a plain dict for broadcast/REST."""
        return {
            "id": self.id,
            "ip": self.ip,
            "name": self.name,
            "printer_type": self.printer_type,
            "mainboard_id": self.mainboard_id,
            "connected": self.connected,
            "status": self.status,
            "attrs": self.attrs,
            "camera_url": self.camera_url,
            "filament_mm": self.filament_mm,
            "filament_g": self.filament_g,
            "thumbnail_url": f"/api/printers/{self.id}/thumbnail" if self.thumbnail_b64 else None,
        }

    _EMIT_MIN_INTERVAL = 0.5  # seconds — max broadcast rate per printer

    def _emit(self, force: bool = False) -> None:
        """Call *on_state_change* with the current serialised state.

        Rate-limited to at most one broadcast per ``_EMIT_MIN_INTERVAL`` seconds
        to avoid flooding the browser WebSocket with rapid printer pushes.
        Connection-state changes (force=True) always go through immediately.
        """
        now = time.monotonic()
        if force or (now - self._last_emit_time) >= self._EMIT_MIN_INTERVAL:
            self._last_emit_time = now
            self._pending_emit = False
            self._on_state_change(self.to_dict())
        else:
            # Schedule a deferred emit so the last update always reaches the UI
            if not self._pending_emit:
                self._pending_emit = True
                delay = self._EMIT_MIN_INTERVAL - (now - self._last_emit_time)
                try:
                    loop = asyncio.get_running_loop()
                    loop.call_later(delay, self._deferred_emit)
                except RuntimeError:
                    pass  # no event loop in test context

    def _deferred_emit(self) -> None:
        if self._pending_emit:
            self._last_emit_time = time.monotonic()
            self._pending_emit = False
            self._on_state_change(self.to_dict())

    def _set_connected(self, value: bool) -> None:
        """Update the connected flag and emit immediately (bypasses rate limit)."""
        if self.connected != value:
            self.connected = value
            self._emit(force=True)
