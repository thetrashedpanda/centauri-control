# CentauriControl

A local, self-hosted dashboard for managing Elegoo Centauri 3D printers. Monitor printer status, control movements, manage print jobs, and integrate third-party sensors—all from a secure, single-machine web interface.

## Features

- **Printer Management** — Add CC1 and CC2 Elegoo Centauri printers by IP address. Store printer access codes securely. Remove printers from the dashboard without affecting physical devices.
- **Real-time Status & Control** — Live printer state, temperature monitoring, movement controls (jog, axis homing), and print job management via WebSocket.
- **Camera Support** — Integrated camera feeds with automatic reconnection and backoff retry on stream interruption.
- **Customizable Dashboard** — Drag-and-drop widget-based layout with real-time synchronization across sessions.
- **Device Integrations** — Built-in support for third-party sensors (e.g., OpenFilament Sensor on ESP32) with one-click integration testing.
- **Print History** — Track completed and failed prints with timestamp and file information.
- **Session Authentication** — Secure login with session-based authentication; optional setup mode for initial configuration.
- **HTTPS & Secure WebSocket** — Enforced TLS encryption for all network traffic; plain HTTP redirects to HTTPS.

## Hardware Support

- **Elegoo Centauri CC1** — SDCP protocol over local WebSocket (port 3030)
- **Elegoo Centauri CC2** — MQTT protocol via local broker
- **OpenFilament Sensor** — ESP32-C3 with `/api/v2/status` API (with fallback to `/sensor_status`)

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+ (frontend build only)
- Local network access to Centauri printers
- TLS certificate (self-signed generated at first startup)

### Installation

```bash
# Clone the repository
git clone https://github.com/thetrashedpanda/centauri-control.git
cd centauri-control

# Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e '.[dev]'

# Frontend setup (in another terminal)
cd frontend
npm ci
npm run build

# Run the application
cd ../backend
python -m centauricontrol
```

The dashboard will be available at `https://localhost:8443`. On first run, you will be prompted to set an admin password.

### Development

```bash
# Backend (with auto-reload)
cd backend
python -m centauricontrol

# Frontend (with dev server and hot reload)
cd frontend
npm run dev
# The dev server proxies /api, /camera, and /ws to https://127.0.0.1:8443
```

## Configuration

### Adding Printers

1. Open the **Add Printer** dialog in the dashboard
2. Enter the printer's IP address, an optional name, and printer type (CC1 or CC2)
3. For CC2 printers, provide the MQTT access code if required
4. Verify the connection and save

### Integrating Sensors

1. Open **Settings → Integrations**
2. Select the integration type (e.g., OpenFilament Sensor)
3. Enter the sensor's HTTP address (e.g., `http://192.168.1.50`)
4. Click **Test** to verify connectivity
5. Save and add the integration widget to your dashboard

**Note:** Keep sensor APIs on a trusted local network; do not expose them directly to the internet.

### Customizing the Dashboard

- **Edit Mode** — Click the **Edit** button to rearrange widgets
- **Drag to Move** — Click and drag a widget's header
- **Resize** — Use the bottom-right corner handle to resize
- **Add Widgets** — Click **Add Widget** to add new monitoring or control panels
- **Persistent Layout** — Your layout is automatically saved and synced across sessions

## Architecture

### Backend

- **Language:** Python 3.12+
- **Framework:** Native `http.server` (ThreadingHTTPServer) + asyncio
- **WebSocket:** `websockets` library for browser and printer communication
- **MQTT:** `aiomqtt` for CC2 printer support
- **Authentication:** Session cookies with bcrypt password hashing

### Frontend

- **Language:** TypeScript (strict mode)
- **Framework:** React 18 + Vite
- **State:** Zustand (per-domain slices)
- **UI:** React Grid Layout + Tailwind CSS v4
- **WebSocket:** Native browser WebSocket API

### Security

- **TLS Enforcement:** HTTPS only; plain HTTP redirects to HTTPS
- **Session Authentication:** Login required for all protected routes
- **Secret Management:** Credentials and TLS keys excluded from Git
- **Input Validation:** All API inputs validated and type-checked
- **CORS & Origin Checks:** WebSocket connections validated by origin and session

## API Overview

All API endpoints require session authentication (except `/api/auth/login`, `/api/auth/setup`, `/api/auth/status`, and `/health`).

### Printer Management

- `GET /api/printers` — List all printers
- `POST /api/printers` — Add a new printer
- `PUT /api/printers/{id}` — Update printer name/access code
- `DELETE /api/printers/{id}` — Remove a printer
- `POST /api/printers/{id}/print` — Start a print job

### Dashboard

- `GET /api/layout` — Get the current layout
- `PUT /api/layout` — Save the layout
- `GET /api/history` — Get print history

### Integrations

- `GET /api/integrations` — List active integrations
- `PUT /api/integrations/{type}` — Configure an integration
- `POST /api/integrations/{type}/test` — Test connection

### WebSocket (`wss://localhost:8765`)

Bidirectional real-time updates: printer state changes, print progress, and control commands.

## Development & Testing

```bash
# Run backend tests
cd backend
pytest

# Run frontend linting
cd frontend
npm run lint

# Type-check frontend
npm run type-check

# Build for production
npm run build
```

## Troubleshooting

### Certificate Errors

CentauriControl generates a self-signed TLS certificate at startup. Browsers will show a security warning; this is expected. You can either:
- Accept the certificate warning in your browser
- Import the certificate into your system's trusted store
- Replace the certificate with one from a trusted authority

### Printer Not Responding

- Verify the printer's IP address and network connectivity
- Ensure the printer is powered on and connected to the same network
- Check that the MQTT access code (CC2) is correct
- Try removing and re-adding the printer

### Camera Stream Not Working

- Verify the printer's camera is enabled and accessible
- Check that the camera URL matches the printer's address
- Try refreshing the dashboard; the widget will reconnect automatically

## Architecture Notes

- **No circular dependencies** — Modules follow a strict dependency graph
- **Thread-safe broadcasts** — HTTP handlers use `asyncio.run_coroutine_threadsafe` to signal printer updates
- **Async I/O** — Blocking operations (file I/O, crypto) use `loop.run_in_executor`
- **Type-safe frontend** — No `any` types; strict TypeScript enforcement

## License

See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please ensure:
- Backend tests pass (`pytest`)
- Frontend type-checks pass (`npm run type-check`)
- Code follows the project structure and conventions
- Security and performance best practices are maintained
