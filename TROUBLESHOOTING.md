# CentauriControl Troubleshooting Guide

## WebSocket Connection Failed (Browser Sandbox Issue)

### Symptom
When opening the app in VS Code's embedded browser, you see:
```
WebSocket connection to 'wss://127.0.0.1:8765/' failed: Error in connection establishment: net::ERR_CONNECTION_REFUSED
```

The Printer Management modal shows "No printer selected" and the "Add Printer" button is disabled.

### Root Cause
VS Code's embedded browser runs in an isolated Electron sandbox that cannot directly connect to custom ports (like 8765) on the host machine. The production build expects WebSocket connections to the direct port, not through a proxy.

### Solution: Use the Development Server (Recommended)

Run the application using the provided `dev.sh` script, which starts both the backend and the Vite dev server:

```bash
cd /Users/sam/Desktop/DEV/3D\ Printing/CentauriControl-v2
./dev.sh
```

Then access the application at:
```
http://localhost:5173
```

The Vite dev server (`localhost:5173`) has WebSocket proxying configured, so connections will work properly:
- Frontend connects to `ws://localhost:5173/ws` (local proxy)
- Vite proxies to `wss://127.0.0.1:8765` (actual WebSocket server)

### Alternative: Use a Real Browser

Instead of VS Code's embedded browser, open a real browser (Safari, Chrome, etc.) and navigate to:
```
https://localhost:8443
```

⚠️ **Note:** You'll see a self-signed certificate warning. Click "Show Details" → "Visit this website" to proceed.

Real browsers don't have the same sandbox restrictions as VS Code's embedded browser and can connect directly to port 8765.

---

## Session Disconnected After Server Restart

### Symptom
You're logged in, then the backend restarts, and you get "Unauthorized" WebSocket errors.

### Root Cause
Sessions were stored only in memory. When the backend restarted, all session tokens were lost, even though your browser still had the old cookie.

### Solution (Now Fixed in Version 8320d41+)
Session persistence has been implemented. Sessions are now saved to `data/sessions.json` and restored on startup.

With the latest version:
1. Your session cookie will persist across backend restarts
2. If the backend is restarted, your WebSocket connection will automatically reconnect with the valid session

If you're still on an older version, update to the latest commit.

---

## Network Discovery Not Working

### Symptom
Clicking the "Discover" button in the Printer Management modal doesn't find any printers.

### Root Cause
Network discovery requires the backend to:
1. Send UDP broadcast packets on the local network
2. Listen for responses from Centauri printers

This may fail if:
- Your firewall blocks UDP broadcasts
- You're on a VPN or isolated network
- Printers are on a different subnet
- UDP discovery hasn't been implemented yet in your version

### Solution

**Workaround: Manual IP Entry**
1. In the Printer Management modal, go to "Add Manually"
2. Enter your printer's IP address (e.g., `10.0.0.197`)
3. Click "Add Printer"

**How to find your printer's IP:**
- Check your router's DHCP client list
- Use `nmap -sn 192.168.1.0/24` (if printers are on 192.168.1.*)
- Consult the printer's touchscreen or documentation

**Future Fix**
Network discovery (UDP broadcast) is planned for Phase 3. Until then, manual IP entry is the standard approach.

---

## Printer Added But Not Connecting

### Symptom
You enter the IP address and click "Add Printer", but:
- No connection status update
- No printer state in the dashboard
- WebSocket shows errors

### Troubleshooting Steps

1. **Verify the printer is online:**
   ```bash
   ping 10.0.0.197  # (use your printer's IP)
   ```

2. **Check if the printer's WebSocket port is open:**
   ```bash
   nc -zv 10.0.0.197 3030  # (SDCP uses port 3030)
   ```

3. **Check backend logs for connection errors:**
   ```bash
   tail -f data/logs/centauricontrol.log | grep -i "connection\|error"
   ```

4. **Verify your network connectivity:**
   - Is the printer on the same subnet?
   - Does the firewall allow outbound WebSocket connections?
   - Try pinging the printer from the machine running CentauriControl

5. **Check if the printer requires an access code:**
   - Some Centauri printers require a security code
   - If prompted, enter it in the "Access code (CC1 only)" field

6. **Verify printer type:**
   - CC1 printers use SDCP over WebSocket (port 3030)
   - CC2 printers use MQTT (you'll need the broker address)

---

## Dashboard Widgets Show "No Printer Selected"

### Symptom
After adding a printer, dashboard widgets still show "No printer selected".

### Root Cause
Most common causes:
1. WebSocket connection failed (see "WebSocket Connection Failed" section above)
2. Printer added but not connected (see "Printer Added But Not Connecting" section above)
3. No printers have been added yet

### Solution

1. **Check WebSocket connection:**
   - Open browser DevTools (F12)
   - Go to Console tab
   - Look for messages like `[WS] Connected` or error messages
   - If errors, see "WebSocket Connection Failed" section

2. **Check printer status:**
   - Go to "Manage Printers" modal
   - Verify printers are listed in "Saved Printers"
   - Check connection status in backend logs

3. **Verify you've selected a printer:**
   - Click the printer name to select it
   - Dashboard should update to show its state

---

## Backend Crashes or Won't Start

### Symptom
Running `python -m centauricontrol` exits immediately with errors.

### Common Issues

**Missing dependencies:**
```
ModuleNotFoundError: No module named 'websockets'
```

**Fix:**
```bash
cd backend
pip install -e '.[dev]'
```

**TLS certificate error:**
```
RuntimeError: TLS certificate is required; refusing to start an insecure server
```

**Fix:**
The backend auto-generates self-signed certificates. If this fails, check:
- Permissions on `data/` directory
- Disk space
- Run: `cd data && rm -f cert.pem key.pem` (backend will regenerate)

**Port already in use:**
```
OSError: [Errno 48] Address already in use
```

**Fix:**
Kill the existing process:
```bash
lsof -i :8443  # Find process using port 8443
kill <PID>     # Kill it
```

---

## Frontend Build Issues

### Symptom
`npm run build` fails with TypeScript or module errors.

### Solution

```bash
cd frontend
npm ci              # Clean install
npm run build       # Build again
npm run tsc --noEmit   # Check TypeScript
```

If issues persist:
```bash
rm -rf node_modules package-lock.json
npm ci
npm run build
```

---

## Getting More Help

### Enable Debug Logging

Backend logs are at:
```
data/logs/centauricontrol.log
```

View in real-time:
```bash
tail -f data/logs/centauricontrol.log
```

Follow only specific components:
```bash
tail -f data/logs/centauricontrol.log | grep "cc1\|websocket\|auth"
```

### Browser Console

Open DevTools in your browser (F12) and check:
- Console tab for JavaScript errors
- Network tab for HTTP request failures
- Sources tab to debug WebSocket issues

### Report Issues

Include:
1. Backend logs (`data/logs/centauricontrol.log`)
2. Browser console output (screenshot or copy-paste)
3. Steps to reproduce
4. Your network setup (firewall, VPN, subnet info)
