# CentauriControl v2 — Project Specification

## Project Purpose

CentauriControl is a self-hosted web dashboard for monitoring and controlling Elegoo Centauri Carbon FDM 3D printers on a local network. It replaces a monolithic Python + vanilla-JS v2 application with a modular, widget-based architecture. The backend is a Python 3.12 asyncio service that maintains persistent WebSocket connections to one or more printers (CC1 via SDCP/WebSocket on port 3030; CC2 via MQTT on port 1883), proxies MJPEG camera streams, and exposes a REST API and a browser-facing WebSocket. The frontend is a React 18 single-page application that renders a drag-and-drop dashboard grid of independently configurable widgets, each subscribing to a shared Zustand store that mirrors live printer state pushed over the WebSocket.

---

## Technology Stack

### Backend
- **Language:** Python 3.12
- **Concurrency:** asyncio event loop (single loop); blocking work (UDP discovery, file I/O, Spoolman HTTP calls) run in `loop.run_in_executor(None, ...)` to avoid blocking the loop
- **HTTP server:** `http.server.ThreadingHTTPServer` running in daemon threads (one for HTTP on 8080, one for HTTPS on 8443); threads call back into the asyncio loop via `asyncio.run_coroutine_threadsafe` for broadcasts
- **Browser WebSocket:** `websockets` library, `asyncio`-native server (`websockets.asyncio.server.serve`) on port 8765
- **Printer MQTT (CC2):** `aiomqtt` async client, one client per CC2 printer
- **Auth:** `bcrypt` (rounds=12) for password hashing; session tokens via `secrets.token_urlsafe(32)`, 30-day TTL
- **Persistence:** Plain JSON files under `DATA_DIR`; all writes are atomic (write `.tmp` then `os.rename`)
- **SSL:** Self-signed cert generated via `openssl` subprocess if `cert.pem`/`key.pem` absent

### Frontend
- **Language:** TypeScript (strict mode, no `any` permitted anywhere)
- **Framework:** React 18
- **Build tool:** Vite
- **State:** Zustand (one store per domain slice: printers, spools, layout, ui)
- **Layout:** `react-grid-layout` for drag-and-drop widget grid
- **Styling:** Tailwind CSS v4 with custom design tokens (see Custom Colors below)
- **Routing:** `react-router-dom` v6 (`/login`, `/setup`, `/dashboard`)
- **WebSocket client:** native browser `WebSocket` API, wrapped in a singleton hook

---

## Port Layout

| Service | Port | Protocol |
|---|---|---|
| HTTP redirect | 8080 | HTTP → HTTPS |
| HTTPS UI + REST API | 8443 | HTTPS (self-signed) |
| Browser WebSocket | 8765 | WSS |
| CC1 Printer (SDCP) | 3030 | WS |
| CC2 Printer (MQTT) | 1883 | TCP (MQTT) |
| UDP Discovery | 3000 | UDP broadcast |
| Spoolman | 7912 | HTTP |

---

## Architectural Rules

1. **No circular dependencies.** Module dependency graph must be a DAG. `persistence` imports nothing from `centauricontrol.*`. `printers` imports `persistence` but not `websocket`. `websocket` imports `printers` and `persistence` but not `api`. `api` may import all others.
2. **No `any` in TypeScript.** ESLint rule `@typescript-eslint/no-explicit-any` set to `error`. All store slices, WS message types, and widget props must have explicit type annotations.
3. **Strict mode everywhere.** Both Python (`from __future__ import annotations`) and TypeScript (`"strict": true` in tsconfig).
4. **Atomic file writes.** Every JSON file write must go through `DataStore.write()` which writes to `.tmp` then calls `os.rename()`.
5. **WS message format is frozen.** The browser WebSocket message schema (both inbound actions and outbound broadcast types) is defined in `websocket/SPEC.md` and must not be changed without a coordinated frontend update. New fields may be additive only; no field removals or renames without a version bump.
6. **No global mutable state in Python modules.** All mutable state lives in `PrinterRegistry` or `DataStore` instances that are passed explicitly or accessed via a module-level singleton initialized at startup. No module-level `printers = {}` dicts outside the registry class.
7. **Event-driven broadcast.** Printer connection objects emit state changes by calling a callback registered with `PrinterRegistry`; they do not call `broadcast_to_browsers` directly. This keeps the printer layer decoupled from the WebSocket layer.

---

## Custom Colors (Tailwind CSS v4)

| Token | Hex | Usage |
|---|---|---|
| `bg` | `#0d0e12` | Page/app background |
| `surface` | `#16181f` | Widget card background |
| `surface2` | `#1e2028` | Inset/nested background |
| `border` | `#2a2d38` | All borders and dividers |
| `accent` | `#ff6b2b` | Primary interactive color (buttons, highlights) |
| `muted` | `#6b7280` | Secondary text, labels |

---

## Widget System Overview

A **widget** is a self-contained React component that displays a single category of printer data or controls. Every widget:

- Exports a `WidgetDef` object: `{ id, displayName, category, allowedSizes, defaultSize, requiresPrinterBinding }`.
- Receives `WidgetComponentProps`: `{ instanceId: string, printerId: string | null, config: Record<string, unknown>, size: WidgetSize, isEditMode: boolean }`.
- Reads live data exclusively from Zustand store selectors (never local fetch calls for printer state).
- Dispatches control actions by sending JSON over the shared WebSocket connection.
- Renders a loading/offline state gracefully when `printerId` is null or the printer is disconnected.

The dashboard grid uses `react-grid-layout` with a 12-column responsive layout. Widget instances are stored in the layout config (persisted via `PUT /api/layout`). Multiple instances of the same widget type may coexist (e.g., one TemperatureWidget per printer).

---

## Integration System Overview

CentauriControl v2 uses a built-in integration catalog. Each integration is reviewed application code under `backend/centauricontrol/integrations/`; the UI enables and configures those integrations, but does not install or execute arbitrary code packages.

Integration configuration is persisted atomically in `DATA_DIR/integrations.json`, separately from printer records. Integrations bind their own settings and status to printer IDs, publish typed `integration_update` messages over the browser WebSocket, and may expose status widgets through the static widget registry.

The first device integration is OpenFilament Sensor. It polls the sensor's read-only status endpoint and surfaces runout, flow telemetry, and jam percentages. It does not send printer commands. OpenFilament Sensor retains ownership of jam detection and pausing.

---

## Wave-by-Wave Implementation Order

### Wave 1 — Foundation
1. `persistence/` — `DataStore` class, TypedDict models, atomic writes
2. `auth/` — `AuthManager` backed by `DataStore`
3. `printers/sdcp.py` — pure SDCP message helpers (no I/O)
4. `printers/base.py` — `PrinterConnection` abstract base class
5. `printers/registry.py` — `PrinterRegistry` with callback pattern
6. `__main__.py` — startup sequence, module wiring

### Wave 2 — Printer Connections
7. `printers/cc1.py` — `CC1Connection` (SDCP/WebSocket)
8. `printers/cc2.py` — `CC2Connection` (MQTT/aiomqtt)
9. `printers/discovery.py` — UDP broadcast discovery

### Wave 3 — Server Layer
10. `websocket/` — browser WS handler, broadcast, all action handlers
11. `api/` — REST endpoints, auth routes, camera proxy, upload proxy
12. `integrations/` — Spoolman deduct + DB fetch

### Wave 4 — Frontend Core
13. Zustand store slices + WS message type definitions
14. `App.tsx`, routing, login/setup pages
15. Widget scaffold + `react-grid-layout` grid
16. Layout persistence (GET/PUT `/api/layout`)

### Wave 5 — Widgets (one per wave sub-task)
17. PrinterStatusWidget, CameraWidget
18. TemperatureWidget, ProgressWidget
19. ControlsWidget, SpeedFansWidget
20. SpoolWidget, SpoolInventoryWidget
21. FileBrowserWidget, HistoryWidget

### Wave 6 — Integration System
22. Built-in integration catalog and configuration API
23. Integration status polling, WebSocket events, and registered dashboard widgets

### Wave 7 — Polish & Deploy
24. PWA manifest, service worker
25. SSL cert generation, HTTPS mode
26. Docker / setup scripts
