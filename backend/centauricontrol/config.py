"""
CentauriControl – centralised configuration.

All environment variables, path constants, and port constants live here.
No other centauricontrol module should import os.getenv for configuration values.
"""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Directory paths
# ---------------------------------------------------------------------------

#: Root data directory – persisted state (JSON files, TLS cert, etc.)
DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))

#: Plugins directory – third-party widget bundles
PLUGINS_DIR: Path = Path(os.getenv("PLUGINS_DIR", str(Path(__file__).parent.parent.parent / "plugins")))

#: Public directory – static web assets served by the HTTP server
PUBLIC_DIR: Path = Path(os.getenv("PUBLIC_DIR", str(Path(__file__).parent.parent.parent / "public")))

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

#: When False the HTTP server skips session validation entirely.
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "true").lower() != "false"

# ---------------------------------------------------------------------------
# Integration URLs
# ---------------------------------------------------------------------------

#: Base URL for the local Spoolman instance.
SPOOLMAN_URL: str = os.getenv("SPOOLMAN_URL", "http://localhost:7912")

# ---------------------------------------------------------------------------
# Port constants
# ---------------------------------------------------------------------------

HTTP_PORT: int = 8080
HTTPS_PORT: int = 8443
WS_PORT: int = 8765
DISCOVERY_PORT: int = 3000   # UDP broadcast port for printer discovery
CC1_PORT: int = 3030         # WebSocket port on CC1 printers
MQTT_PORT: int = 1883        # MQTT broker port on CC2 printers

# ---------------------------------------------------------------------------
# Auth / session constants
# ---------------------------------------------------------------------------

SESSION_TTL_DAYS: int = 30

# ---------------------------------------------------------------------------
# TLS certificate paths
# ---------------------------------------------------------------------------

CERT_FILE: Path = DATA_DIR / "cert.pem"
KEY_FILE: Path = DATA_DIR / "key.pem"


# ---------------------------------------------------------------------------
# SSL certificate helpers
# ---------------------------------------------------------------------------

def ensure_ssl_cert() -> bool:
    """Generate a self-signed TLS certificate if one does not already exist.

    The certificate covers both ``localhost`` and the machine's current LAN IP
    so that browsers trust it when the app is accessed over the local network.

    Returns:
        True if the certificate is present (either pre-existing or freshly
        generated), False if generation failed.
    """
    if CERT_FILE.exists() and KEY_FILE.exists():
        return True

    # Resolve the current LAN IP for the Subject Alternative Name extension.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"

    # Ensure the data directory exists before writing the cert files.
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(KEY_FILE),
                "-out",    str(CERT_FILE),
                "-days",   "3650",
                "-nodes",
                "-subj",   "/CN=centauricontrol.local",
                "-addext", f"subjectAltName=IP:{local_ip},IP:127.0.0.1,DNS:localhost",
            ],
            check=True,
            capture_output=True,
        )
        print(f"[SSL] Certificate generated (IP: {local_ip})")
        return True
    except Exception as exc:
        print(f"[SSL] Could not generate certificate: {exc}")
        return False
