"""
CentauriControl – Spoolman integration.

Provides filament deduction (POST /api/v1/spool/{id}/use) and spool database
fetching (GET /api/v1/spool).  All HTTP calls are blocking and must be run
inside a thread executor.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Optional, TYPE_CHECKING

from centauricontrol.config import SPOOLMAN_URL

if TYPE_CHECKING:
    from centauricontrol.printers.registry import PrinterRegistry

_registry: Optional["PrinterRegistry"] = None


def set_registry(registry: "PrinterRegistry") -> None:
    """Wire the printer registry into this module at startup."""
    global _registry
    _registry = registry


# ---------------------------------------------------------------------------
# Public API (blocking — run in executor)
# ---------------------------------------------------------------------------

def get_spoolman_spools() -> list[dict[str, Any]]:
    """Fetch all spools from Spoolman.  Returns [] on any error."""
    url = f"{SPOOLMAN_URL}/api/v1/spool"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"[Spoolman] Failed to fetch spools: {exc!r}")
        return []


def spoolman_deduct(spool_id: int, length_mm: float) -> bool:
    """Deduct *length_mm* millimetres from spool *spool_id* in Spoolman.

    Returns True on success, False on any error.

    Blocking — must be called from a thread executor.
    """
    url = f"{SPOOLMAN_URL}/api/v1/spool/{spool_id}/use"
    payload = json.dumps({"use_length": length_mm}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status < 400
    except Exception as exc:
        print(f"[Spoolman] Deduct failed for spool {spool_id}: {exc!r}")
        return False
