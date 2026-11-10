# Backend — Architectural Specification

## Purpose

The backend is a Python 3.12 asyncio service that manages persistent connections to Elegoo Centauri Carbon printers (CC1 via SDCP/WebSocket, CC2 via MQTT), exposes a REST API and browser WebSocket, and persists application state to JSON files. It owns all network communication with printers, all authentication logic, all file persistence, and the Spoolman integration. It does NOT own the frontend bundle (served as static files) or plugin widget bundles (served as static files from `/plugins/`).

---

## Package Layout

```
backend/
├── centauri-control/
│   ├── __init__.py
│   ├── __main__.py          # Entrypoint: asyncio.run(main())
│   ├── auth/
│   │   ├── __init__.py
│   │   └── manager.py       # AuthManager class
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── datastore.py     # DataStore class
│   │   └── models.py        # TypedDict models
│   ├── printers/
│   │   ├── __init__.py
│   │   ├── base.py          # PrinterConnection ABC
│   │   ├── cc1.py           # CC1Connection (SDCP/WebSocket)
│   │   ├── cc2.py           # CC2Connection (MQTT)
│   │   ├── registry.py      # PrinterRegistry
│   │   ├── sdcp.py          # Pure SDCP message helpers
│   │   └── discovery.py     # UDP broadcast discover_printers()
│   ├── websocket/
│   │   ├── __init__.py
│   │   └── handler.py       # browser_handler, broadcast_to_browsers
│   ├── api/
│   │   ├── __init__.py
│   │   └── http.py          # SPHandler (ThreadingHTTPServer request handler)
│   ├── integrations/
│   │   ├── __init__.py
│   │   └── spoolman.py      # spoolman_deduct, get_spoolman_db
│   └── plugins/
│       ├── __init__.py
│       └── loader.py        # Plugin discovery and registration
└── public/                  # Static frontend build (served by HTTP handler)
```

---

## Module Communication Rules

1. **No circular imports.** Import graph (direction = "may import"):
   - `persistence` → nothing in `centauricontrol.*`
   - `auth` → `persistence`
   - `printers` → `persistence` only
   - `integrations` → `persistence` (for caching), nothing in `printers` or `websocket`
   - `websocket` → `printers.registry`, `persistence`, `integrations`
   - `api` → `auth`, `printers.registry`, `persistence`, `integrations`
   - `plugins` → `api` (to register routes), `websocket` (to register hooks)
   - `__main__` → all of the above

2. **Printer events via registry callbacks.** `PrinterConnection` subclasses must never import `websocket.handler`. Instead, they call `self._on_state_change(self.to_dict())` which is a callback injected by `PrinterRegistry` at connection creation time. The registry's callback calls `asyncio.ensure_future(broadcast_to_browsers(...))` on the running loop.

3. **Thread safety for broadcasts.** `ThreadingHTTPServer` request handlers run in threads. They must call `asyncio.run_coroutine_threadsafe(broadcast_to_browsers(msg), loop)` when they need to broadcast. They must never `await` directly.

---

## Async Model

- One `asyncio` event loop runs in the main thread (via `asyncio.run(main())`).
- The loop hosts: all printer `asyncio.Task` objects, the `websockets` browser WS server, and `aiomqtt` MQTT clients.
- `ThreadingHTTPServer` for HTTP (port 8080) runs in a `daemon=True` thread.
- `ThreadingHTTPServer` for HTTPS (port 8443) runs in a `daemon=True` thread.
- TLS is required at startup; port 8080 redirects to HTTPS, and the browser WebSocket server uses the same TLS context.
- Browser WebSocket handshakes require a valid session cookie and an allowed same-host dashboard origin.
- Blocking operations (UDP discovery, Spoolman HTTP calls, file reads, `bcrypt` verify) are dispatched to the default thread pool via `loop.run_in_executor(None, fn, *args)`.
- `asyncio.CancelledError` from printer tasks must propagate (never caught without re-raise) so that `PrinterRegistry.stop_all()` can cleanly shut down all connections.

---

## Data Flow

```
Browser ──WS──► browser_handler()
                    │
                    ▼
              handle_browser_message(ws, raw)
                    │ routes by action
                    ▼
           PrinterRegistry.get(printer_id)
                    │
                    ▼
         PrinterConnection.send_cmd(cmd, data)
                    │
                    ▼ (CC1)               (CC2)
          ws.send(SDCP JSON)    mqtt.publish(api_request)
                    │
                    ▼ (async push from printer)
         PrinterConnection._handle_message()
                    │ updates self.status / self.attrs
                    ▼
         self._on_state_change(self.to_dict())
                    │ callback registered by registry
                    ▼
         broadcast_to_browsers({"type": "printer_update", "printer": ...})
                    │
                    ▼
          all connected browser WebSocket clients
```

REST routes follow the same auth → registry → printer pattern but respond synchronously via HTTP.

---

## Persistence Rules

1. All JSON file writes go through `DataStore.write(filename, data)`.
2. `DataStore.write` writes to `filename + ".tmp"` then calls `os.rename(tmp, final)`. This is atomic on POSIX systems.
3. `DataStore.read(filename)` returns `None` if the file does not exist or is not valid JSON; it never raises.
4. `DataStore.append_json_array(filename, item)` reads the existing array (or `[]`), appends the item, then writes atomically.
5. No module other than `DataStore` may directly read or write files in `DATA_DIR`.

---

## Configuration

All configuration is via environment variables with sensible defaults:

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | directory of `__main__.py` | Directory for all JSON persistence files |
| `AUTH_ENABLED` | `"true"` | Set to `"false"` to disable auth (unsafe on open networks) |
| `CENTAURICONTROL_USERNAME` | `""` | Overrides saved username when set |
| `CENTAURICONTROL_PW_HASH` | `""` | Overrides saved bcrypt hash when set |
| `SPOOLMAN_URL` | `"http://localhost:7912"` | Base URL of Spoolman instance |
