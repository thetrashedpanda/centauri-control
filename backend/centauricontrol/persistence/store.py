"""
CentauriControl – atomic JSON data store.

DataStore wraps a directory of JSON files with:
- Atomic writes via a .tmp → rename two-step (no partial files on crash).
- Per-file threading locks so concurrent callers never interleave writes.
- A convenience helper for append-only JSON arrays (e.g. history log).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Union


# Type alias for the JSON root value returned / accepted by this module.
_JsonRoot = Union[dict, list]


class DataStore:
    """Read and write JSON files atomically inside *data_dir*.

    All public methods are thread-safe: a ``threading.Lock`` is held for the
    duration of each read-modify-write cycle on a per-filename basis.

    Args:
        data_dir: Directory that contains (or will contain) the JSON files.
                  Created automatically if it does not exist.
    """

    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()  # protects _locks dict itself

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lock_for(self, filename: str) -> threading.Lock:
        """Return the per-file lock, creating it on first access."""
        with self._meta_lock:
            if filename not in self._locks:
                self._locks[filename] = threading.Lock()
            return self._locks[filename]

    def _path(self, filename: str) -> Path:
        return self._dir / filename

    def _tmp_path(self, filename: str) -> Path:
        return self._dir / (filename + ".tmp")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self, filename: str) -> _JsonRoot | None:
        """Read and deserialise *filename*.

        Returns:
            Parsed JSON value (``dict`` or ``list``) or ``None`` if the file
            does not exist.

        Raises:
            json.JSONDecodeError: If the file exists but contains invalid JSON.
        """
        path = self._path(filename)
        with self._lock_for(filename):
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def write(self, filename: str, data: _JsonRoot) -> None:
        """Serialise *data* and write it to *filename* atomically.

        The write strategy is:

        1. Serialise to a ``.tmp`` file in the same directory.
        2. Call ``os.replace()`` to atomically swap it into place.

        This guarantees that a reader never sees a partial write, even if the
        process is killed mid-operation.

        Args:
            filename: Target filename (basename only, no directory component).
            data:     JSON-serialisable ``dict`` or ``list``.
        """
        tmp = self._tmp_path(filename)
        target = self._path(filename)
        serialised = json.dumps(data, ensure_ascii=False, indent=2)

        with self._lock_for(filename):
            tmp.write_text(serialised, encoding="utf-8")
            os.replace(tmp, target)

    def append_json_array(self, filename: str, item: dict) -> None:
        """Append *item* to the JSON array stored in *filename*.

        If the file does not exist, a new single-element array is created.
        The underlying write is atomic (same two-step strategy as
        :meth:`write`).

        Args:
            filename: Target filename.
            item:     Dict to append to the array.
        """
        tmp = self._tmp_path(filename)
        target = self._path(filename)

        with self._lock_for(filename):
            # Read existing data inside the lock to avoid a TOCTOU race.
            if target.exists():
                try:
                    existing: list = json.loads(target.read_text(encoding="utf-8"))
                    if not isinstance(existing, list):
                        existing = []
                except (json.JSONDecodeError, OSError):
                    existing = []
            else:
                existing = []

            existing.append(item)
            serialised = json.dumps(existing, ensure_ascii=False, indent=2)
            tmp.write_text(serialised, encoding="utf-8")
            os.replace(tmp, target)
