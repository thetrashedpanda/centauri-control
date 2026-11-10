"""
CentauriControl – SDCP v3.0 protocol helpers.

Pure functions and constants for the Smart Device Control Protocol used by
Elegoo Centauri Carbon printers.  No network I/O, no asyncio, no imports
from other centauricontrol modules.

Protocol reference: OpenCentauri api.md (written by remmylee, Elegoo Discord)
and SDCP v3.0 specification.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from typing import Any


# ---------------------------------------------------------------------------
# Command constants (SDCP Cmd field values)
# ---------------------------------------------------------------------------

#: Request status refresh – printer replies with current Status object.
CMD_STATUS: int = 0

#: Request attribute refresh – printer replies with Attributes object.
CMD_ATTRS: int = 1

#: Start a print job.
CMD_START: int = 128

#: Pause the current print job.
CMD_PAUSE: int = 129

#: Stop (cancel) the current print job.
CMD_STOP: int = 130

#: Resume a paused print job.
CMD_RESUME: int = 131

#: Stop automatic material (filament) feeding.
CMD_STOP_FEED: int = 132

#: Skip the preheating phase of the current print.
CMD_SKIP_PREHEAT: int = 133

#: Change the printer's display name (stored on the mainboard).
CMD_SET_NAME: int = 192

#: Terminate an in-progress file transfer.
CMD_TERMINATE_TRANSFER: int = 255

#: Retrieve the list of files in a directory.
CMD_LIST_FILES: int = 258

#: Batch-delete files and/or folders.
CMD_DELETE_FILES: int = 259

#: Retrieve the list of historical print task IDs.
CMD_HISTORY_LIST: int = 320

#: Retrieve detailed information for one or more historical tasks.
CMD_HISTORY_DETAIL: int = 321

#: Enable or disable the MJPEG video stream.
CMD_CAMERA: int = 386

#: Enable or disable time-lapse photography.
CMD_TIMELAPSE: int = 387

#: Runtime adjustments: print speed percentage and/or fan speeds.
#
# NOTE: Cmd 403 is overloaded – the firmware keys behaviour off which fields
# are present in Data, not the Cmd number alone.  The same integer is used for
# the light-control payload on CC1 printers (LightStatus) and for print-speed
# (PrintSpeedPct) / fan-speed (TargetFanSpeed) on CC2 printers.
CMD_LIGHT: int = 403
CMD_SET_RUNTIME: int = 403   # alias; same wire value

# Axis-control commands captured from the official ELEGOO web app.
CMD_EDIT_PRINTER_AXIS_NUMBER: int = 401
CMD_EDIT_PRINTER_AXIS_ZERO: int = 402

# ---------------------------------------------------------------------------
# Print status codes  (PrintInfo.Status field)
# ---------------------------------------------------------------------------

#: Maps the integer ``PrintInfo.Status`` value to a human-readable string.
PRINT_STATUS: dict[int, str] = {
    0:  "idle",
    1:  "homing",
    2:  "dropping",       # resin: platform descending (repurposed for FDM warmup)
    3:  "printing",
    4:  "lifting",        # resin: platform lifting (repurposed for FDM layer change)
    5:  "pausing",
    6:  "paused",
    7:  "stopping",
    8:  "stopped",        # cancelled
    9:  "complete",
    10: "file_checking",
    12: "preheating",
    13: "printing",       # duplicate used by some firmware builds
    14: "error",
    15: "warming_up",
    16: "calibrating",
    18: "printing",       # resuming from pause, firmware variant
    19: "printing",
    20: "printing",
    21: "printing",
}

#: Maps the integer ``CurrentStatus`` (machine-level) value to a string.
MACHINE_STATUS: dict[int, str] = {
    0: "idle",
    1: "printing",
    2: "file_transferring",
    3: "calibrating",
    4: "device_testing",
}


# ---------------------------------------------------------------------------
# Message construction
# ---------------------------------------------------------------------------

def make_msg(
    cmd: int,
    data: dict,
    request_id: str | None = None,
    mainboard_id: str = "",
) -> str:
    """Build a JSON-encoded SDCP request message string.

    Args:
        cmd:          SDCP command integer (one of the ``CMD_*`` constants).
        data:         Command-specific payload dict for the inner ``Data`` key.
        request_id:   Optional explicit request ID.  A random UUID hex string
                      is generated if omitted.
        mainboard_id: Printer mainboard identifier string.  Empty string is
                      valid before the ID is discovered.

    Returns:
        JSON string ready to send over the WebSocket connection.

    Example::

        raw = make_msg(CMD_STATUS, {})
        ws.send(raw)
    """
    if request_id is None:
        request_id = uuid.uuid4().hex  # 32-char lowercase hex, no hyphens

    envelope: dict[str, Any] = {
        "Id": request_id,
        "Data": {
            "Cmd": cmd,
            "Data": data,
            "RequestID": request_id,
            "MainboardID": mainboard_id,
            "TimeStamp": int(time.time()),
            "From": "Web",
        },
        "Topic": f"sdcp/request/{mainboard_id}",
    }
    return json.dumps(envelope)


# ---------------------------------------------------------------------------
# PrintInfo normalisation
# ---------------------------------------------------------------------------

def decode_printinfo(raw: dict) -> dict:
    """Normalise a raw ``PrintInfo`` dict from the printer.

    Elegoo firmware versions differ in how they encode field names:

    * Older CC1 builds sometimes send field names as space-separated hex bytes,
      e.g. ``"54 6F 74 61 6C 45 78 74 72 75 73 69 6F 6E 00"`` → ``"TotalExtrusion"``.
    * Some firmware builds use ``"FileName"`` while others use ``"Filename"``.
      This function normalises the former to the latter so callers always read
      ``"Filename"``.

    Args:
        raw: The ``PrintInfo`` dict as received from the printer.

    Returns:
        A new dict with hex-encoded key names decoded and ``FileName`` aliased
        to ``Filename``.
    """
    result: dict = {}
    for k, v in raw.items():
        parts = k.split()
        if (
            len(parts) > 1
            and all(
                len(p) == 2 and all(c in "0123456789abcdefABCDEF" for c in p)
                for p in parts
            )
        ):
            try:
                decoded_key = bytes(int(p, 16) for p in parts).rstrip(b"\x00").decode("utf-8")
                result[decoded_key] = v
                continue
            except Exception:
                pass
        result[k] = v

    # Firmware spelling inconsistency: normalise "FileName" → "Filename".
    if "FileName" in result:
        wrong = result.pop("FileName")
        result.setdefault("Filename", wrong)

    return result


# ---------------------------------------------------------------------------
# State merging (CC2 partial updates)
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, update: dict, max_keys: int = 500) -> dict:
    """Recursively merge *update* into *base* in-place and return *base*.

    Nested dicts are merged recursively; scalar values are overwritten.  A
    ``max_keys`` guard prevents unbounded growth if malformed data arrives.

    Args:
        base:     The dict to merge into (modified in-place).
        update:   The incoming partial state dict.
        max_keys: Safety cap on the number of keys in *base* after merging.

    Returns:
        *base* (the same object, modified in-place).
    """
    for k, v in update.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v, max_keys)
        else:
            base[k] = v
        if len(base) > max_keys:
            break
    return base


# ---------------------------------------------------------------------------
# Filament mass calculation
# ---------------------------------------------------------------------------

def filament_mm_to_grams(
    mm: float,
    density: float = 1.24,
    diameter: float = 1.75,
) -> float:
    """Convert an extrusion length to filament mass in grams.

    Uses the standard cross-section formula::

        mass = π × (diameter/2)² × (length_cm) × density

    Args:
        mm:       Total extrusion length in millimetres.
        density:  Filament material density in g/cm³.  Defaults to PLA (1.24).
        diameter: Filament diameter in millimetres.  Defaults to 1.75 mm.

    Returns:
        Mass in grams, rounded to one decimal place.

    Example::

        >>> filament_mm_to_grams(1000)
        3.8
    """
    radius_cm = (diameter / 2) / 10  # mm → cm
    length_cm = mm / 10              # mm → cm
    volume_cm3 = math.pi * radius_cm ** 2 * length_cm
    return round(volume_cm3 * density, 1)
