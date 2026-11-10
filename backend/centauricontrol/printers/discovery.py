"""
CentauriControl – UDP broadcast printer discovery.

Sends a SDCP discovery broadcast on the local network and collects responses
from Elegoo Centauri Carbon printers for a short window.  This is a blocking
function intended to be run in a thread executor.
"""

from __future__ import annotations

import json
import socket
import time

from centauricontrol.config import DISCOVERY_PORT


_BROADCAST_MSG = json.dumps({
    "Id": "discovery",
    "Data": {
        "Cmd": 0,
        "Data": {},
        "RequestID": "discovery",
        "MainboardID": "",
        "TimeStamp": 0,
        "From": "Web",
    },
    "Topic": "sdcp/request/",
}).encode("utf-8")

_LISTEN_SECONDS = 3.0


def discover_printers(timeout: float = _LISTEN_SECONDS) -> list[dict]:
    """Send a UDP broadcast and collect responding printers.

    Blocking.  Run inside a thread executor to avoid blocking the asyncio loop.

    Args:
        timeout: How many seconds to listen for responses after broadcasting.

    Returns:
        List of dicts, each with keys: ``ip``, ``name``, ``mainboard_id``,
        ``printer_type`` (always ``"cc1"`` for discovered printers).
    """
    results: list[dict] = []
    seen_ips: set[str] = set()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.5)
        sock.bind(("", DISCOVERY_PORT))

        # Send the broadcast
        sock.sendto(_BROADCAST_MSG, ("<broadcast>", DISCOVERY_PORT))

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
                ip = addr[0]
                if ip in seen_ips:
                    continue
                seen_ips.add(ip)
                _parse_response(data, ip, results)
            except socket.timeout:
                continue
            except OSError:
                break
    finally:
        sock.close()

    return results


def _parse_response(data: bytes, ip: str, results: list[dict]) -> None:
    """Parse a UDP response and append a result entry if valid."""
    try:
        msg = json.loads(data.decode("utf-8"))
    except Exception:
        return

    inner_data = msg.get("Data", {})
    if isinstance(inner_data, dict):
        inner_data = inner_data.get("Data", inner_data)

    if not isinstance(inner_data, dict):
        return

    mainboard_id = (
        inner_data.get("MainboardID")
        or msg.get("Data", {}).get("MainboardID", "")
        or ""
    )
    name = (
        inner_data.get("Name")
        or inner_data.get("MachineName")
        or f"Printer @ {ip}"
    )

    results.append({
        "ip": ip,
        "name": name,
        "mainboard_id": mainboard_id,
        "printer_type": "cc1",
    })
