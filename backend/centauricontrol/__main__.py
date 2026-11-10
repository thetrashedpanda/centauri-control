"""
CentauriControl – application entry point.

Invoked as:  python -m centauricontrol

Wires all modules together, runs the startup sequence, and hands control to
the asyncio event loop.  No business logic lives here.
"""

from __future__ import annotations

import asyncio
import ssl
import sys
import threading

# Validate hard dependency early
try:
    import websockets  # noqa: F401
except ImportError:
    print("[CentauriControl] FATAL: 'websockets' package is not installed. Run: pip install websockets")
    sys.exit(1)

# Optional dependency warnings
try:
    import bcrypt  # noqa: F401
except ImportError:
    print("[CentauriControl] WARNING: 'bcrypt' not installed — password auth unavailable")

try:
    import aiomqtt  # noqa: F401
except ImportError:
    print("[CentauriControl] WARNING: 'aiomqtt' not installed — CC2 printers unavailable")

from centauricontrol.config import (
    AUTH_ENABLED,
    CERT_FILE,
    DATA_DIR,
    HTTP_PORT,
    HTTPS_PORT,
    KEY_FILE,
    WS_PORT,
    ensure_ssl_cert,
)
from centauricontrol.logging_config import initialize_logging, get_logger
from centauricontrol.persistence.store import DataStore
from centauricontrol.auth.manager import AuthManager, set_auth_manager
from centauricontrol.printers.registry import PrinterRegistry


async def main() -> None:
    """Application root coroutine.  Called exactly once via asyncio.run()."""

    # 1. Initialize logging
    initialize_logging(log_dir=DATA_DIR / "logs")
    logger = get_logger(__name__)

    # 2. Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 3. Initialize DataStore
    store = DataStore(DATA_DIR)

    # 4. Initialize AuthManager
    auth = AuthManager(store)
    set_auth_manager(auth)

    # 5. Log auth status
    if not AUTH_ENABLED:
        logger.info("Authentication disabled (AUTH_ENABLED=false)")
    elif not auth.has_password():
        logger.warning("No password configured — first-time setup required at /setup")
    else:
        logger.info(f"Authentication enabled (user: {auth.get_username()})")

    # 6. Import WebSocket handler now so we can build the broadcast callback.
    #    Import is deferred to respect module loading order.
    from centauricontrol.websocket.handler import (
        broadcast_to_browsers,
        set_integration_status_provider,
        set_registry as ws_set_registry,
    )
    from centauricontrol.api.http import make_handler_class
    from centauricontrol.integrations.manager import IntegrationManager
    from centauricontrol.integrations.spoolman import set_registry as spoolman_set_registry

    loop = asyncio.get_running_loop()

    def _broadcast_callback(state: dict) -> None:
        msg = {"type": "printer_update", "printer": state}
        asyncio.run_coroutine_threadsafe(broadcast_to_browsers(msg), loop)

    async def _integration_update_callback(status: dict) -> None:
        await broadcast_to_browsers({"type": "integration_update", "status": status})

    # 7. Initialize PrinterRegistry
    registry = PrinterRegistry(store, on_state_change=_broadcast_callback)
    integrations = IntegrationManager(store, _integration_update_callback)

    # 8. Load saved printers
    registry.load_saved()

    # 9. Wire registry into WS handler and Spoolman integration
    ws_set_registry(registry)
    set_integration_status_provider(integrations.statuses)
    spoolman_set_registry(registry)

    # 10. Start printer connection tasks
    registry.start_all()
    asyncio.create_task(integrations.poll_forever(lambda: [str(p["id"]) for p in registry.all()]))

    # 11. Build HTTP request handler class
    handler_class = make_handler_class(store, auth, registry, loop, integrations)

    import http.server

    # 12. Require TLS for network access; the HTTP listener only redirects.
    if not ensure_ssl_cert():
        raise RuntimeError("TLS certificate is required; refusing to start an insecure server")
    try:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    except (OSError, ssl.SSLError) as exc:
        raise RuntimeError(f"Could not load TLS certificate: {exc}") from exc

    https_server = http.server.ThreadingHTTPServer(("0.0.0.0", HTTPS_PORT), handler_class)
    https_server.socket = ssl_ctx.wrap_socket(https_server.socket, server_side=True)
    https_thread = threading.Thread(target=https_server.serve_forever, daemon=True)
    https_thread.start()

    http_server = http.server.ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), handler_class)
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()

    # 13. Start browser WebSocket server and run forever
    from centauricontrol.websocket.handler import browser_handler
    from websockets.asyncio.server import serve as ws_serve

    logger.info(f"HTTP  → http://localhost:{HTTP_PORT} (redirects to HTTPS)")
    logger.info(f"HTTPS → https://localhost:{HTTPS_PORT}")
    logger.info(f"WSS  → wss://localhost:{WS_PORT}")
    logger.info("Ready")

    async with ws_serve(
        browser_handler,
        "0.0.0.0",
        WS_PORT,
        ssl=ssl_ctx,
        ping_interval=30,   # send keepalive ping every 30s
        ping_timeout=60,    # allow 60s for pong before closing
        max_size=10 * 1024 * 1024,  # 10 MB — large enough for thumbnail payloads
    ):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger = get_logger(__name__)
        logger.info("Shutting down")
