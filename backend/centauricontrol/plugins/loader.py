"""
CentauriControl – plugin loader.

Discovers and loads plugins from the PLUGINS_DIR directory.  Each plugin is
a directory containing a server.py with a `manifest` dict and an optional
`register(routes, ws_hooks, printer_event_hooks)` function.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from centauricontrol.config import PLUGINS_DIR

_MANIFEST_FILE = "manifest.json"
_SERVER_MODULE  = "server.py"

_loaded_manifests: list[dict[str, Any]] = []


def load_plugins() -> None:
    """Discover and load all enabled plugins.  Called once at startup."""
    manifest_path = PLUGINS_DIR / _MANIFEST_FILE
    if not manifest_path.exists():
        return

    try:
        enabled: list[str] = json.loads(manifest_path.read_text()).get("enabled", [])
    except Exception as exc:
        print(f"[Plugins] Failed to read manifest.json: {exc!r}")
        return

    for plugin_id in enabled:
        plugin_dir = PLUGINS_DIR / plugin_id
        server_file = plugin_dir / _SERVER_MODULE
        if not server_file.exists():
            print(f"[Plugins] Plugin '{plugin_id}' has no server.py — skipping")
            continue
        try:
            _load_plugin(plugin_id, plugin_dir, server_file)
        except Exception as exc:
            print(f"[Plugins] Failed to load plugin '{plugin_id}': {exc!r}")


def _load_plugin(plugin_id: str, plugin_dir: Path, server_file: Path) -> None:
    spec = importlib.util.spec_from_file_location(f"centauricontrol_plugin_{plugin_id}", server_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {server_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"centauricontrol_plugin_{plugin_id}"] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]

    manifest: dict[str, Any] = getattr(module, "manifest", {"id": plugin_id})
    manifest.setdefault("id", plugin_id)
    _loaded_manifests.append(manifest)

    if hasattr(module, "register"):
        # Provide stub hooks — a real implementation would pass real registries
        module.register(routes=[], ws_hooks=[], printer_event_hooks=[])

    print(f"[Plugins] Loaded '{plugin_id}': {manifest.get('name', plugin_id)}")


def get_plugin_manifests() -> list[dict[str, Any]]:
    """Return the list of loaded plugin manifests."""
    return list(_loaded_manifests)
