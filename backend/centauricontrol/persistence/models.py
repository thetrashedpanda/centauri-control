"""
CentauriControl – persistence data models.

Pure TypedDict definitions for every structured value stored to disk or passed
between layers.  No I/O, no imports from other centauricontrol modules.
"""

from __future__ import annotations

from typing import Literal, Optional, TypedDict


# ---------------------------------------------------------------------------
# Printer registry
# ---------------------------------------------------------------------------

class PrinterRecord(TypedDict):
    """One entry in the saved printers list."""

    id: str
    ip: str
    name: str
    printer_type: Literal["cc1", "cc2"]
    access_code: str


# ---------------------------------------------------------------------------
# Print history
# ---------------------------------------------------------------------------

class HistoryEntry(TypedDict):
    """One completed or cancelled print job recorded in local history."""

    timestamp: str       # ISO 8601, e.g. "2024-01-15T14:23:00"
    printer_id: str
    printer_name: str
    filename: str
    filament_mm: float   # total extrusion in millimetres
    filament_g: float    # mass derived from extrusion length
    print_time_s: int    # elapsed print time in seconds
    completed: bool      # True = successful completion, False = cancelled/stopped


# ---------------------------------------------------------------------------
# Dashboard layouts
# ---------------------------------------------------------------------------

class LayoutItem(TypedDict):
    """react-grid-layout grid position descriptor for one widget instance."""

    i: str   # maps to WidgetInstance.instanceId
    x: int
    y: int
    w: int
    h: int


class WidgetInstance(TypedDict):
    """Runtime configuration for a single placed widget on the dashboard."""

    instanceId: str
    widgetId: str            # references the widget plugin identifier
    printerId: Optional[str] # None for non-printer-specific widgets
    config: dict             # widget-specific settings
    size: str                # e.g. "sm", "md", "lg"


class SavedLayout(TypedDict):
    """One named dashboard layout that can be activated by the user."""

    id: str
    name: str
    instances: list[WidgetInstance]
    gridLayout: list[LayoutItem]
    updatedAt: str           # ISO 8601


class LayoutsFile(TypedDict):
    """Top-level structure of the layouts.json persistence file."""

    version: int
    activeLayoutId: str
    layouts: list[SavedLayout]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class AuthRecord(TypedDict):
    """Saved credentials stored in auth.json."""

    username: str
    pw_hash: str             # bcrypt hash string
