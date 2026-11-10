# CentauriControl v2

CentauriControl v2 is a local, self-hosted dashboard for Elegoo Centauri printers. It is an independent v2 workspace based on the code in `CentauriControl-v1`; the v1 folder is not modified.

## Integrations

Open **Settings → Integrations** to configure bundled integrations. Integrations are maintained in CentauriControl's source and selected through the UI; v2 does not download or execute arbitrary third-party code packages.

The first device integration is **OpenFilament Sensor**. Configure one sensor HTTP address per printer (for example `http://192.168.1.50`), test the connection, and save it. Use a reserved DHCP address or stable hostname for each ESP32-C3. In dashboard edit mode, add an **OpenFilament Sensor** widget and bind it to the corresponding printer.

CentauriControl reads status from `GET /api/v2/status`. For compatibility while updating firmware, it falls back to the existing `GET /sensor_status` endpoint if the v2 route returns 404. The integration is read-only: OpenFilament Sensor remains responsible for filament/jam detection and issuing any printer pause.

The ESP32 status API is unauthenticated, as is the current device dashboard. Keep it on a trusted local network; do not expose it directly to the internet.

## Dashboard and camera

Select **Edit** to move or resize widgets: drag a widget's header to move it and use the highlighted bottom-right corner to resize it. The grid follows the available dashboard width.

The camera widget reconnects automatically after a stream error. CentauriControl also retries interrupted printer-camera streams with backoff; a retryable interruption should no longer require a page refresh.

The Movement widget supports axis jogs and individual X/Y/Z homing using the official app's SDCP command format. A jog was captured as `Cmd 401` with `Axis`/`Step`; a Z-home request was captured as `Cmd 402` with `Axis: "Z"`. Jog steps are limited to 0.1, 1, 10, or 100 mm, and the controls are available only while the printer is connected and idle. A combined **Home All** action is not exposed because its command payload has not been verified.

## Development

```sh
# Backend
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
python -m centauricontrol

# Frontend, in another terminal
cd frontend
npm ci
npm run dev
```

The backend serves the production frontend from `public/`; build it with `cd frontend && npm ci && npm run build`.

The integration configuration is stored in `data/integrations.json`, separately from printer records. The API routes are authenticated with the normal CentauriControl session.

The application requires a TLS certificate at startup. HTTP requests on port 8080 redirect to HTTPS on port 8443; use the HTTPS address for dashboard access.
