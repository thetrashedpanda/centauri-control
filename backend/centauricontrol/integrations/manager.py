"""
Built-in integration catalog and OpenFilament Sensor connection manager.

Integrations are application-owned code. User configuration can enable and
configure a bundled integration, but cannot load executable plugin packages.
"""

from __future__ import annotations

import asyncio
import copy
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from centauricontrol.persistence.store import DataStore

_CONFIG_FILE = "integrations.json"
_INTEGRATION_ID = "openfilamentsensor"
_POLL_INTERVAL_SECONDS = 3
_REQUEST_TIMEOUT_SECONDS = 2
_MAX_RESPONSE_BYTES = 16 * 1024

IntegrationUpdateCallback = Callable[[dict[str, Any]], Awaitable[None]]


def validate_sensor_url(value: str) -> str:
    """Validate and normalize a base URL for a local OpenFilament Sensor."""
    url = value.strip().rstrip("/")
    if not url or len(url) > 255:
        raise ValueError("Enter the sensor's HTTP address, such as http://192.168.1.50")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Sensor address must be an http:// host with no path, credentials, query, or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Sensor address has an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Sensor address port must be between 1 and 65535")
    return url


def _request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "CentauriControl/2"},
    )
    with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
        body = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError("Sensor response exceeded the size limit")
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Sensor returned an invalid status document")
    return parsed


def fetch_sensor_status(base_url: str) -> dict[str, Any]:
    """Read v2 status, falling back to the legacy endpoint during upgrades."""
    base_url = validate_sensor_url(base_url)
    try:
        payload = _request_json(f"{base_url}/api/v2/status")
        if payload.get("api_version") != 2:
            raise ValueError("Sensor API version is not supported")
        for section in ("device", "filament", "printer"):
            if not isinstance(payload.get(section), dict):
                raise ValueError(f"Sensor status is missing the {section} section")
        return {
            "schema_version": 2,
            "device": payload["device"],
            "filament": payload["filament"],
            "printer": payload["printer"],
        }
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise

    legacy = _request_json(f"{base_url}/sensor_status")
    printer = legacy.get("elegoo")
    if not isinstance(printer, dict):
        raise ValueError("Legacy sensor status is missing printer telemetry")
    return {
        "schema_version": 1,
        "device": {
            "firmware_version": "legacy",
            "chip_family": "",
            "mac": legacy.get("mac", ""),
            "ip": legacy.get("ip", ""),
            "uptime_seconds": legacy.get("uptimeSec", 0),
        },
        "filament": {
            "runout": legacy.get("filamentRunout", False),
            "stopped": legacy.get("stopped", False),
            "movement_pulses": printer.get("movementPulses", 0),
            "hard_jam_percent": printer.get("hardJamPercent", 0),
            "soft_jam_percent": printer.get("softJamPercent", 0),
            "telemetry_available": printer.get("telemetryAvailable", False),
            "grace_active": printer.get("graceActive", False),
            "current_deficit_mm": printer.get("currentDeficitMm", 0),
            "expected_filament_mm": printer.get("expectedFilament", 0),
            "actual_filament_mm": printer.get("actualFilament", 0),
            "expected_rate_mm_per_sec": printer.get("expectedRateMmPerSec", 0),
            "actual_rate_mm_per_sec": printer.get("actualRateMmPerSec", 0),
        },
        "printer": {
            "connected": printer.get("isWebsocketConnected", False),
            "is_printing": printer.get("isPrinting", False),
            "print_status": printer.get("printStatus", 0),
            "progress_percent": printer.get("progress", 0),
            "current_layer": printer.get("currentLayer", 0),
            "total_layer": printer.get("totalLayer", 0),
        },
    }


class IntegrationManager:
    """Persists bundled integration settings and polls enabled sensor links."""

    def __init__(
        self,
        store: DataStore,
        on_update: IntegrationUpdateCallback,
    ) -> None:
        self._store = store
        self._on_update = on_update
        self._states: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _configuration(self) -> dict[str, Any]:
        value = self._store.read(_CONFIG_FILE)
        if not isinstance(value, dict):
            return {"version": 1, "integrations": {_INTEGRATION_ID: {"printers": {}}}}
        integrations = value.get("integrations")
        if not isinstance(integrations, dict):
            integrations = {}
        sensor = integrations.get(_INTEGRATION_ID)
        if not isinstance(sensor, dict) or not isinstance(sensor.get("printers"), dict):
            integrations[_INTEGRATION_ID] = {"printers": {}}
        return {"version": 1, "integrations": integrations}

    def configure_sensor(
        self,
        printer_id: str,
        enabled: bool,
        base_url: str,
    ) -> dict[str, Any]:
        if not printer_id or len(printer_id) > 128:
            raise ValueError("A valid printer ID is required")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        normalized_url = validate_sensor_url(base_url) if base_url.strip() else ""
        if enabled and not normalized_url:
            raise ValueError("Enter the sensor address before enabling the integration")

        config = self._configuration()
        sensor_config = config["integrations"][_INTEGRATION_ID]["printers"]
        if normalized_url or enabled:
            sensor_config[printer_id] = {"enabled": enabled, "base_url": normalized_url}
        else:
            sensor_config.pop(printer_id, None)
        self._store.write(_CONFIG_FILE, config)
        return self.catalog()

    def catalog(self, printer_ids: list[str] | None = None) -> dict[str, Any]:
        config = self._configuration()["integrations"][_INTEGRATION_ID]["printers"]
        with self._lock:
            states = copy.deepcopy(self._states)
        ids = sorted(set(printer_ids or []) | set(config))
        sensor_printers: dict[str, Any] = {}
        for printer_id in ids:
            item = config.get(printer_id, {})
            status = states.get(printer_id)
            if status is None and item:
                status = {
                    "integration_id": _INTEGRATION_ID,
                    "printer_id": printer_id,
                    "enabled": bool(item.get("enabled", False)),
                    "connected": False,
                    "base_url": str(item.get("base_url", "")),
                    "last_seen": None,
                    "error": None,
                    "data": None,
                }
            sensor_printers[printer_id] = {
                "enabled": bool(item.get("enabled", False)),
                "base_url": str(item.get("base_url", "")),
                "status": status,
            }
        return {
            "integrations": [
                {
                    "id": _INTEGRATION_ID,
                    "name": "OpenFilament Sensor",
                    "version": "2",
                    "description": "Read filament runout and jam-detection telemetry from a local sensor.",
                    "category": "filament",
                    "supports_printer_binding": True,
                    "enabled_printers": sum(
                        1 for value in sensor_printers.values() if value["enabled"]
                    ),
                    "printers": sensor_printers,
                }
            ]
        }

    def statuses(self) -> list[dict[str, Any]]:
        config = self._configuration()["integrations"][_INTEGRATION_ID]["printers"]
        with self._lock:
            states = copy.deepcopy(self._states)
        for printer_id, item in config.items():
            states.setdefault(
                printer_id,
                {
                    "integration_id": _INTEGRATION_ID,
                    "printer_id": printer_id,
                    "enabled": bool(item.get("enabled", False)),
                    "connected": False,
                    "base_url": str(item.get("base_url", "")),
                    "last_seen": None,
                    "error": None,
                    "data": None,
                },
            )
        return list(states.values())

    async def poll_forever(self, printer_ids: Callable[[], list[str]]) -> None:
        """Poll configured devices and publish their latest read-only state."""
        while True:
            config = self._configuration()["integrations"][_INTEGRATION_ID]["printers"]
            known_printers = set(printer_ids())
            configured_ids = set(config)

            for printer_id in sorted(configured_ids | known_printers):
                item = config.get(printer_id, {})
                enabled = bool(item.get("enabled", False))
                base_url = str(item.get("base_url", ""))
                if enabled and base_url and printer_id in known_printers:
                    try:
                        data = await asyncio.to_thread(fetch_sensor_status, base_url)
                        status = {
                            "integration_id": _INTEGRATION_ID,
                            "printer_id": printer_id,
                            "enabled": True,
                            "connected": True,
                            "base_url": base_url,
                            "last_seen": datetime.now(timezone.utc).isoformat(),
                            "error": None,
                            "data": data,
                        }
                    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
                        with self._lock:
                            previous = self._states.get(printer_id, {})
                        status = {
                            "integration_id": _INTEGRATION_ID,
                            "printer_id": printer_id,
                            "enabled": True,
                            "connected": False,
                            "base_url": base_url,
                            "last_seen": previous.get("last_seen"),
                            "error": str(exc)[:200],
                            "data": previous.get("data"),
                        }
                else:
                    status = {
                        "integration_id": _INTEGRATION_ID,
                        "printer_id": printer_id,
                        "enabled": False,
                        "connected": False,
                        "base_url": base_url,
                        "last_seen": None,
                        "error": None,
                        "data": None,
                    }

                with self._lock:
                    self._states[printer_id] = status
                await self._on_update(status)

            with self._lock:
                for printer_id in set(self._states) - configured_ids - known_printers:
                    self._states.pop(printer_id, None)

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
