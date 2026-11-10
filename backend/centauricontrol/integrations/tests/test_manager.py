from __future__ import annotations

import urllib.error

import pytest

from centauricontrol.integrations import manager
from centauricontrol.persistence.store import DataStore


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://192.168.1.40", "http://192.168.1.40"),
        (" http://ofs.local:80/ ", "http://ofs.local:80"),
    ],
)
def test_validate_sensor_url_normalizes_base_url(value: str, expected: str) -> None:
    assert manager.validate_sensor_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://ofs.local",
        "http://user:password@ofs.local",
        "http://ofs.local/api",
        "http://ofs.local?token=secret",
        "http://ofs.local:99999",
    ],
)
def test_validate_sensor_url_rejects_unsupported_urls(value: str) -> None:
    with pytest.raises(ValueError):
        manager.validate_sensor_url(value)


def test_fetch_sensor_status_accepts_v2_document(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "api_version": 2,
        "device": {"firmware_version": "2.0.0"},
        "filament": {"runout": False},
        "printer": {"connected": True},
    }
    monkeypatch.setattr(manager, "_request_json", lambda _url: payload)

    result = manager.fetch_sensor_status("http://ofs.local")

    assert result == {
        "schema_version": 2,
        "device": payload["device"],
        "filament": payload["filament"],
        "printer": payload["printer"],
    }


def test_fetch_sensor_status_falls_back_to_legacy_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str] = []

    def request_json(url: str) -> dict:
        requested.append(url)
        if url.endswith("/api/v2/status"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return {
            "filamentRunout": False,
            "elegoo": {
                "movementPulses": 12,
                "isWebsocketConnected": True,
            },
        }

    monkeypatch.setattr(manager, "_request_json", request_json)

    result = manager.fetch_sensor_status("http://ofs.local/")

    assert requested == [
        "http://ofs.local/api/v2/status",
        "http://ofs.local/sensor_status",
    ]
    assert result["schema_version"] == 1
    assert result["filament"]["movement_pulses"] == 12
    assert result["printer"]["connected"] is True


def test_configure_sensor_persists_per_printer_settings(tmp_path) -> None:
    store = DataStore(tmp_path)
    integration_manager = manager.IntegrationManager(store, _noop_update)

    integration_manager.configure_sensor("printer-1", True, "http://ofs.local")

    saved = store.read("integrations.json")
    assert saved == {
        "version": 1,
        "integrations": {
            "openfilamentsensor": {
                "printers": {
                    "printer-1": {
                        "enabled": True,
                        "base_url": "http://ofs.local",
                    }
                }
            }
        },
    }


def test_configured_sensor_is_visible_before_first_poll(tmp_path) -> None:
    store = DataStore(tmp_path)
    integration_manager = manager.IntegrationManager(store, _noop_update)
    integration_manager.configure_sensor("printer-1", True, "http://ofs.local")

    status = integration_manager.statuses()[0]
    assert status == {
        "integration_id": "openfilamentsensor",
        "printer_id": "printer-1",
        "enabled": True,
        "connected": False,
        "base_url": "http://ofs.local",
        "last_seen": None,
        "error": None,
        "data": None,
    }
    catalog = integration_manager.catalog(["printer-1"])
    assert catalog["integrations"][0]["printers"]["printer-1"]["status"] == status


async def _noop_update(_status: dict) -> None:
    return None
