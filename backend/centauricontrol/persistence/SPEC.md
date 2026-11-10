# persistence — Specification

## Purpose

The `persistence` module owns all JSON file I/O for the application. It provides an atomic file write guarantee, centralized file access through a single `DataStore` class, and typed data models for all persisted structures. It does NOT contain business logic, does NOT make network calls, and does NOT import from any other `centauricontrol.*` module.

---

## Public API

### `class DataStore`

```python
class DataStore:
    def __init__(self, data_dir: Path) -> None:
        """Initialize with the directory where all data files are stored.
        Creates data_dir if it does not exist.
        Raises PermissionError if data_dir is not writable."""

    def read(self, filename: str) -> dict | list | None:
        """Read and parse a JSON file from data_dir.
        Returns the parsed object (dict or list) on success.
        Returns None if the file does not exist or contains invalid JSON.
        Never raises."""

    def write(self, filename: str, data: dict | list) -> None:
        """Atomically write data as JSON to data_dir/filename.
        Algorithm: serialize to bytes, write to filename+'.tmp', then os.rename(tmp, final).
        Raises OSError if the write or rename fails."""

    def append_json_array(self, filename: str, item: dict) -> None:
        """Read the existing JSON array from filename (or [] if absent/invalid),
        append item, then write the updated array atomically.
        Raises OSError if the write fails."""
```

### File Names (constants)

```python
PRINTERS_FILE: str = "printers.json"
HISTORY_FILE: str = "history.json"
AUTH_FILE: str = "auth.json"
LAYOUTS_FILE: str = "layouts.json"
```

---

## TypedDict Models

All persisted data structures are defined as `TypedDict` in `persistence/models.py`.

### `PrinterRecord`
```python
class PrinterRecord(TypedDict):
    id: str               # Unique printer ID (IP for manually added, MainboardID for discovered)
    ip: str               # IP address string
    name: str             # Display name
    printer_type: str     # "cc1" or "cc2"
    access_code: str      # CC2 MQTT password; empty string for CC1
```

### `HistoryEntry`
```python
class HistoryEntry(TypedDict):
    timestamp: str        # ISO 8601 string, e.g. "2024-01-15T14:30:00"
    printer_id: str
    printer_name: str
    filename: str
    filament_mm: float    # Total extrusion in millimeters
    filament_g: float     # Total extrusion in grams
    print_time_s: int     # Print duration in seconds
    completed: bool       # True=completed, False=cancelled/stopped
```

### `LayoutItem`
```python
class LayoutItem(TypedDict):
    i: str      # Instance ID (unique per widget instance on the grid)
    x: int      # Grid column position (0-11)
    y: int      # Grid row position
    w: int      # Width in grid columns
    h: int      # Height in grid rows
```

### `WidgetInstance`
```python
class WidgetInstance(TypedDict):
    instanceId: str               # Matches LayoutItem.i
    widgetId: str                 # Widget type ID (e.g. "printer-status")
    printerId: str | None         # Bound printer ID, or None if not bound
    config: dict[str, object]     # Per-widget settings dict
```

### `SavedLayout`
```python
class SavedLayout(TypedDict):
    id: str                          # Layout ID (e.g. "default")
    name: str                        # Display name
    layout: list[LayoutItem]         # react-grid-layout layout array
    widgets: list[WidgetInstance]    # Widget instance configurations
```

### `LayoutsFile`
```python
class LayoutsFile(TypedDict):
    active: str                    # ID of the active layout
    layouts: list[SavedLayout]
```

### `AuthRecord`
```python
class AuthRecord(TypedDict):
    username: str
    pw_hash: str    # bcrypt hash string (e.g. "$2b$12$...")
```

---

## Invariants

- `DataStore.write` is the only function that writes files. All other modules call `DataStore.write()`, never `Path.write_text()` directly.
- The `.tmp` file is always in the same directory as the target file, so `os.rename` is atomic on the same filesystem.
- `DataStore.read` never raises; it absorbs `FileNotFoundError`, `json.JSONDecodeError`, and `PermissionError` and returns `None`.
- `DataStore.append_json_array` is internally atomic — the read-modify-write happens within a single call to `DataStore.write`.
- All JSON files are UTF-8 encoded with 2-space indentation.
- `data_dir` is resolved to an absolute path in `__init__` via `Path(data_dir).resolve()`.

---

## Error Handling

| Failure | Behavior |
|---|---|
| File does not exist in `read()` | Return `None`; log nothing |
| File contains invalid JSON in `read()` | Return `None`; log `[DataStore] Warning: {filename} is not valid JSON` |
| `PermissionError` in `read()` | Return `None`; log the error |
| `os.rename` fails in `write()` | Raise `OSError`; the `.tmp` file may remain on disk |
| `data_dir` not writable at init | Raise `PermissionError` immediately in `__init__` |
| `append_json_array` reads invalid JSON | Treat as empty array `[]`, overwrite with `[item]` |

---

## Test Requirements

- Given a fresh `DataStore`, when `read("nonexistent.json")` is called, then it returns `None`.
- Given a fresh `DataStore`, when `write("test.json", {"key": "value"})` then `read("test.json")` is called, then it returns `{"key": "value"}`.
- Given `write` is called, when the filesystem is inspected during write (via mock), then a `.tmp` file exists before `os.rename` and the original file has the new content after.
- Given `write("file.json", data)` is called on a read-only directory, then it raises `OSError`.
- Given `append_json_array("hist.json", {"a": 1})` called twice, when `read("hist.json")` is called, then it returns a list of two entries.
- Given a file containing `"not json"`, when `read(filename)` is called, then it returns `None` without raising.
- Given `append_json_array` is called on a file containing invalid JSON, then it overwrites with `[item]` rather than appending.

---

## Do Not

- `DataStore` must NOT import from any other `centauricontrol` module (no `auth`, `printers`, `websocket`, `api`, `integrations`, `plugins`).
- Do not use `Path.write_text()` or `open(..., 'w')` directly in `write()` — always write to `.tmp` first then rename.
- Do not pretty-print with more than 2-space indent (keeps files readable but not bloated).
- Do not store binary data, images, or non-JSON content.
- Do not implement caching or TTL logic — that belongs in the caller.

---

## Dependencies

Allowed standard library imports:
- `json`, `os`, `pathlib.Path`, `typing`, `typing_extensions` (for `TypedDict` on Python < 3.12 if needed)

Allowed internal imports: none.
