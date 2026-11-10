# centauricontrol package — Specification

## Purpose

The `centauricontrol` package is the top-level Python package for the backend service. It owns the application entrypoint (`__main__.py`), which wires all modules together, runs the startup sequence, and starts the asyncio event loop. It does NOT contain business logic — that lives in the sub-packages.

---

## Public API

```python
# Entry point — invoked via: python -m centauricontrol
# __main__.py
async def main() -> None: ...
```

The `main()` coroutine is the single root of the application. It must be called only via `asyncio.run(main())`.

---

## Invariants

- `main()` is called exactly once per process lifetime.
- All module-level singletons (DataStore, AuthManager, PrinterRegistry, etc.) are created inside `main()` and passed explicitly to sub-modules. No module-level global state is initialized at import time.
- If `websockets` is not installed, `main()` prints an error and calls `sys.exit(1)` before any server starts.
- The asyncio event loop reference is captured inside `main()` with `asyncio.get_running_loop()` and passed to modules that need to call `run_coroutine_threadsafe` from threads.

---

## Startup Sequence

`main()` executes in this exact order:

1. **Create persisted storage** — create `DATA_DIR` and initialize `DataStore`.
2. **Initialize authentication** — create and register `AuthManager`, then log the current setup state.
3. **Prepare event callbacks** — import the WebSocket, HTTP, and integration modules and capture the running event loop.
4. **Initialize registries** — create `PrinterRegistry` and `IntegrationManager` with their broadcast callbacks.
5. **Load and wire state** — load saved printers and supply the registry and integration-status provider to the WebSocket and Spoolman modules.
6. **Start polling and printer connections** — start saved printer tasks and the integration status poller.
7. **Start HTTP and HTTPS** — construct the authenticated request handler and start the HTTP thread; start HTTPS when certificate setup succeeds.
8. **Start browser WebSocket service** — serve browser connections, send initial printer and integration snapshots, then keep the application running.

## Integration Catalog

- Integration code is bundled with CentauriControl and selected/configured in **Settings → Integrations**. The application does not download or execute user-supplied integration packages.
- Per-printer integration configuration is stored in `data/integrations.json`, separately from printer records.
- `IntegrationManager` polls enabled sensor links and broadcasts read-only status. OpenFilament Sensor remains responsible for jam detection and printer pausing; CentauriControl does not issue pause commands through this integration.
- Integration catalog, configuration, and connection-test endpoints use the normal authenticated HTTP API.
- Manual axis movement and homing are not exposed through the documented Centauri SDCP interface. Legacy jog/home requests are rejected rather than sent as unverified printer commands.

---

## Module Loading Order

The entry point imports core dependencies first and defers the API, WebSocket, Spoolman, and integration imports until `main()` has initialized storage and authentication:

```python
from centauricontrol.persistence.store import DataStore
from centauricontrol.auth.manager import AuthManager
from centauricontrol.printers.registry import PrinterRegistry
from centauricontrol.integrations.manager import IntegrationManager
from centauricontrol.integrations.spoolman import set_registry as spoolman_set_registry
```

---

## Error Handling

- If `DATA_DIR` does not exist, create it with `DATA_DIR.mkdir(parents=True, exist_ok=True)`.
- If `DATA_DIR` is not writable, `DataStore.__init__` raises `PermissionError`; `main()` lets this propagate and crash with a clear traceback.
- If SSL cert generation fails, log the error and skip starting the HTTPS server; HTTP continues normally.
- `KeyboardInterrupt` is caught by the `asyncio.run()` caller and triggers a clean shutdown message.

---

## Do Not

- Do not put business logic in `__main__.py`. It must only wire, configure, and start.
- Do not import from `centauricontrol.websocket` or `centauricontrol.api` before `centauricontrol.persistence` and `centauricontrol.auth` are initialized.
- Do not start any asyncio tasks before step 6 (load saved printers), because the registry callback may reference an uninitialized broadcast function.

---

## Dependencies

Allowed standard library imports in `__main__.py`:
- `asyncio`, `threading`, `os`, `sys`, `pathlib.Path`, `ssl`, `socket`, `subprocess`

Allowed third-party imports:
- `websockets` (required), `aiomqtt` (optional), `bcrypt` (optional)

Allowed internal imports: all `centauricontrol.*` sub-packages as listed in Module Loading Order above.
