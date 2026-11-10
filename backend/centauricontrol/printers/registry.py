"""
CentauriControl – PrinterRegistry.

Owns the set of active printer connections, lifecycle management (start/stop),
persistence of the printer list, and the state-change callback chain that
feeds the WebSocket broadcast layer.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Optional

from centauricontrol.persistence.store import DataStore
from centauricontrol.persistence.models import PrinterRecord
from centauricontrol.printers.base import PrinterConnection, StateChangeCallback

_PRINTERS_FILE = "printers.json"

BroadcastCallback = Callable[[dict[str, Any]], None]


class PrinterRegistry:
    """Manages the set of active :class:`PrinterConnection` objects.

    Args:
        store:            DataStore used for reading/writing printers.json.
        on_state_change:  Callback fired whenever any printer's state changes.
                          Receives the printer's ``to_dict()`` snapshot.
    """

    def __init__(
        self,
        store: DataStore,
        on_state_change: BroadcastCallback,
    ) -> None:
        self._store = store
        self._on_state_change = on_state_change
        # id → connection object
        self._printers: dict[str, PrinterConnection] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load_saved(self) -> None:
        """Read printers.json and instantiate connections for each record."""
        raw = self._store.read(_PRINTERS_FILE)
        if not isinstance(raw, list):
            return
        for record in raw:
            if not isinstance(record, dict):
                continue
            self._create_connection(record)

    def start_all(self) -> None:
        """Schedule asyncio tasks for all loaded connections."""
        for conn in self._printers.values():
            self._start_connection(conn)

    async def stop_all(self) -> None:
        """Cancel all running connection tasks and wait for them to finish."""
        tasks = [
            conn._task
            for conn in self._printers.values()
            if conn._task is not None
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, printer_id: str) -> Optional[PrinterConnection]:
        """Return the connection for *printer_id*, or None."""
        return self._printers.get(printer_id)

    def all(self) -> list[dict[str, Any]]:
        """Return serialised state for every registered printer."""
        return [c.to_dict() for c in self._printers.values()]

    def add(
        self,
        ip: str,
        name: str,
        printer_type: str,
        access_code: str = "",
        printer_id: Optional[str] = None,
    ) -> PrinterConnection:
        """Add a new printer, persist it, and start its connection task.

        Args:
            ip:           IP address of the printer.
            name:         Human-readable display name.
            printer_type: ``"cc1"`` or ``"cc2"``.
            access_code:  MQTT password (CC2 only); empty string for CC1.
            printer_id:   Explicit ID; auto-generated UUID if omitted.

        Returns:
            The newly created :class:`PrinterConnection` instance.
        """
        if printer_id is None:
            printer_id = uuid.uuid4().hex

        record: PrinterRecord = {
            "id": printer_id,
            "ip": ip,
            "name": name,
            "printer_type": printer_type,  # type: ignore[typeddict-item]
            "access_code": access_code,
        }
        conn = self._create_connection(record)
        self._persist_all()
        self._start_connection(conn)
        return conn

    def remove(self, printer_id: str) -> bool:
        """Remove a printer, cancel its task, and persist the updated list.

        Returns:
            True if the printer was found and removed, False otherwise.
        """
        conn = self._printers.pop(printer_id, None)
        if conn is None:
            return False
        if conn._task is not None:
            conn._task.cancel()
        self._persist_all()
        return True

    def update(
        self,
        printer_id: str,
        name: Optional[str] = None,
        access_code: Optional[str] = None,
    ) -> bool:
        """Update mutable fields on an existing printer and re-persist.

        Returns:
            True if the printer was found and updated.
        """
        conn = self._printers.get(printer_id)
        if conn is None:
            return False
        if name is not None:
            conn.name = name
        if access_code is not None:
            conn.access_code = access_code
        self._persist_all()
        conn._emit()
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_callback(self, printer_id: str) -> StateChangeCallback:
        """Return a state-change callback that tags the update with the printer_id."""
        def _cb(state: dict[str, Any]) -> None:
            self._on_state_change(state)
        return _cb

    def _create_connection(self, record: dict[str, Any]) -> PrinterConnection:
        """Instantiate the right PrinterConnection subclass for *record*."""
        # Import here to avoid module-level circular imports.
        from centauricontrol.printers.cc1 import CC1Connection
        from centauricontrol.printers.cc2 import CC2Connection

        printer_id: str = record["id"]
        printer_type: str = record.get("printer_type", "cc1")
        callback = self._make_callback(printer_id)

        if printer_type == "cc2":
            conn: PrinterConnection = CC2Connection(
                printer_id=printer_id,
                ip=record["ip"],
                name=record["name"],
                printer_type=printer_type,
                access_code=record.get("access_code", ""),
                on_state_change=callback,
            )
        else:
            conn = CC1Connection(
                printer_id=printer_id,
                ip=record["ip"],
                name=record["name"],
                printer_type=printer_type,
                access_code=record.get("access_code", ""),
                on_state_change=callback,
            )

        self._printers[printer_id] = conn
        return conn

    def _start_connection(self, conn: PrinterConnection) -> None:
        """Schedule conn.start() as an asyncio task."""
        if conn._task is not None and not conn._task.done():
            return
        conn._task = asyncio.create_task(conn.start(), name=f"printer-{conn.id}")

    def _persist_all(self) -> None:
        """Write the current printer list to printers.json."""
        records = [
            {
                "id": c.id,
                "ip": c.ip,
                "name": c.name,
                "printer_type": c.printer_type,
                "access_code": c.access_code,
            }
            for c in self._printers.values()
        ]
        self._store.write(_PRINTERS_FILE, records)
