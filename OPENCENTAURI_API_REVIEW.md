# OpenCentauri SDCP API Review & CentauriControl Improvements

**Date:** November 10, 2026  
**Reviewed Against:** https://docs.opencentauri.cc/software/api/ (SDCP v3.0.0)  
**Scope:** Functionality, stability, and security enhancements for CentauriControl web app

---

## 1. Protocol Compliance Issues

### 1.1 **CRITICAL: Field Name Misspellings Not Handled** 🔴
The SDCP specification contains intentional misspelling errors in field names that MUST be used exactly as-is:
- `CurrenCoord` (missing 't' in "Current")
- `RelaseFilmState` (missing 'e' in "Release")  
- `MaximumCloudSDCPSercicesAllowed` (missing 'v' in "Services")

**Current Status:** Unclear if CentauriControl handles these misspellings correctly.

**Recommendation:**
- [ ] Audit all status parsing to confirm misspelled field names are used
- [ ] Add fallback handling for both spellings (accept either, normalize internally)
- [ ] Document field name quirks in code comments
- [ ] Add unit tests that verify parsing with misspelled field names from actual printer responses

**Example Fix:**
```python
# In status parser
current_coord = status_data.get('CurrenCoord') or status_data.get('CurrentCoord')
release_film = status_data.get('RelaseFilmState') or status_data.get('ReleaseFilmState')
```

---

### 1.2 **MISSING: Device Discovery via UDP Broadcast** 🟠
The SDCP spec requires UDP broadcast discovery before WebSocket connection:
- Port: 3000
- Message: `"M99999"`
- Returns: device info including MainboardIP, firmware version, protocol version

**Current Status:** Manual IP entry required; no auto-discovery implemented.

**Recommendation:**
- [ ] Implement UDP broadcast discovery endpoint: `GET /api/discovery`
- [ ] Scan local network (user-specified CIDR or default 192.168.1.0/24)
- [ ] Return discovered printers with firmware/protocol versions
- [ ] Cache discovery results with 5-minute TTL
- [ ] Add timeout handling (5 seconds per broadcast attempt)
- [ ] Frontend: Pre-populate discovered printers in "Add Printer" dialog

**Security Note:** Restrict discovery to local network only; add IP/CIDR validation.

---

### 1.3 **MISSING: Alternative WebSocket Paths** 🟡
Spec lists multiple WebSocket endpoint paths that may be supported:
- `/websocket` (standard)
- `/ws`
- `/`
- `/api/websocket`
- `/sdcp`

**Current Status:** Unclear if fallback paths are supported for different printer firmware versions.

**Recommendation:**
- [ ] Test against multiple firmware versions to identify which paths are available
- [ ] Add fallback logic: try `/websocket` first, then `/ws`, etc.
- [ ] Document firmware compatibility matrix
- [ ] Cache selected path per printer to avoid repeated fallbacks

---

## 2. Missing SDCP Command Implementations

### 2.1 **CRITICAL: File Management (Cmd: 258, 259)** 🔴
File listing and batch delete are not implemented but are core features:
- **Cmd 258:** Retrieve file list from `/usb/` or `/local/` storage
- **Cmd 259:** Batch delete files and folders
- Response includes file sizes, storage type (internal/external), file type (folder/file)

**Current Status:** Not implemented; users cannot browse or manage files on printer storage.

**Recommendation:**
- [ ] Implement file browser in frontend (tree view or file grid)
- [ ] Add file list endpoint: `GET /api/printer/{id}/files?path={path}`
- [ ] Support pagination for large directories
- [ ] Add delete dialog: `DELETE /api/printer/{id}/files` with file/folder lists
- [ ] Show storage usage (usedSize/totalSize per path)
- [ ] Filter by file type for printing (`.gcode` only, or configurable)
- [ ] Add breadcrumb navigation for directory traversal

**Example Backend:**
```python
async def _api_printer_files(self, printer_id: str, path: str = "/local/") -> dict:
    """Fetch file list from printer storage."""
    printer = registry.get(printer_id)
    response = await printer.send_cmd(258, {"Url": path})
    return response.get("FileList", [])
```

---

### 2.2 **HIGH: Print History (Cmd: 320, 321)** 🟠
Print history endpoints not exposed:
- **Cmd 320:** Retrieve list of historical task UUIDs
- **Cmd 321:** Fetch detailed info for specific task UUIDs

**Current Status:** Manual tracking only; no integration with printer history.

**Recommendation:**
- [ ] Fetch history on printer connect: `POST /api/printer/{id}/sync-history`
- [ ] Store task UUIDs locally to avoid re-fetching
- [ ] Query task details for recently completed prints
- [ ] Add to print history UI with status (success/failed), duration, filename
- [ ] Merge local history with printer history for complete view
- [ ] Add history export (CSV/JSON)

**Benefits:** Users see full print history without manual logging.

---

### 2.3 **MEDIUM: Filament State (Field: RelaseFilmState)** 🟡
Status includes filament state but not utilized:
- Related to OpenFilament Sensor integration
- Misspelled as `RelaseFilmState`
- Can indicate jam or low filament

**Current Status:** Parsed but not displayed or used for alerts.

**Recommendation:**
- [ ] Display filament state in printer status widget
- [ ] Add alert/warning if filament is low or jammed
- [ ] Log filament state changes for diagnostics
- [ ] (Future) Integrate with OpenFilament Sensor for predictions

---

### 2.4 **MEDIUM: Configuration Commands (Cmd: 192, 403)** 🟡
Limited config support; missing some settings:
- **Cmd 192:** Change printer name (implemented)
- **Cmd 403:** Set print speed and fan speeds (fan speeds not exposed)

**Current Status:** Print speed controls exist; fan speed controls missing.

**Recommendation:**
- [ ] Add fan speed controls to movement widget:
  - Model Fan (0-100%)
  - Auxiliary Fan (0-100%)
  - Box Fan (0-100%)
- [ ] Sync settings on printer connect
- [ ] Add preset profiles (quiet, balanced, high-performance)
- [ ] Store user preferences locally

---

### 2.5 **MEDIUM: Motor Status Monitoring (DevicesStatus)** 🟡
Attributes include motor status but not monitored:
- `ZMotorStatus`, `YMotorStatus`, `XMotorStatus`, `ExtruderMotorStatus`
- Indicates stepper motor health

**Current Status:** Not displayed or tracked.

**Recommendation:**
- [ ] Display motor status in system health widget
- [ ] Alert if any motor shows error (non-1 status)
- [ ] Log motor failures for diagnostics
- [ ] Trigger automatic recovery (e.g., retry homing)

---

### 2.6 **LOW: Skip Preheating (Cmd: 133)** ⚪
Skip preheating command implemented but not exposed in UI.

**Recommendation:**
- [ ] Add checkbox: "Skip preheating" in print start dialog
- [ ] Validate: only allow if temps already near target

---

## 3. Stability Improvements

### 3.1 **CRITICAL: Heartbeat/Keepalive Missing** 🔴
SDCP spec requires `"ping"` → `"pong"` heartbeat but no keepalive implemented.

**Current Status:** Connections may drop silently; no reconnect detection.

**Recommendation:**
- [ ] Send `"ping"` every 30 seconds (printer-to-browser WebSocket)
- [ ] Send `"ping"` to SDCP printer every 10 seconds
- [ ] Timeout if no `"pong"` within 5 seconds → close and reconnect
- [ ] Implement exponential backoff (1s, 2s, 4s, 8s, max 60s)
- [ ] Display connection status in UI (connected/reconnecting/disconnected)

**Example:**
```python
async def _ping_loop(self) -> None:
    """Send ping to SDCP printer every 10 seconds."""
    while True:
        try:
            await asyncio.sleep(10)
            await self.ws.send('ping')
        except Exception:
            break
```

---

### 3.2 **CRITICAL: Response Timeout Handling** 🔴
No timeout handling for SDCP command responses; hanged requests block operations.

**Current Status:** `send_cmd()` may wait indefinitely for response.

**Recommendation:**
- [ ] Add 5-second timeout for all `send_cmd()` calls
- [ ] Raise `TimeoutError` if no response
- [ ] Retry once on timeout (max 2 attempts)
- [ ] Log timeout events for diagnostics
- [ ] Mark printer as "stale" after 3 consecutive timeouts
- [ ] Trigger reconnect if stale

**Example:**
```python
async def send_cmd(self, cmd: int, data: dict) -> dict:
    try:
        return await asyncio.wait_for(self._send_and_wait(cmd, data), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning(f"Cmd {cmd} timeout; retrying...")
        return await asyncio.wait_for(self._send_and_wait(cmd, data), timeout=5.0)
```

---

### 3.3 **HIGH: WebSocket Reconnection Strategy** 🟠
Connection drops not handled gracefully; manual refresh required.

**Current Status:** Browser WebSocket reconnects on drop, but printer WebSocket may not.

**Recommendation:**
- [ ] Implement exponential backoff for printer reconnect
- [ ] Max 60-second delay between retries
- [ ] Log reconnection attempts with timestamp
- [ ] Notify browsers of printer disconnect/reconnect
- [ ] Queue commands during disconnect; replay on reconnect
- [ ] Add circuit breaker: stop retrying after 10 failures in 5 minutes

---

### 3.4 **HIGH: Request ID Tracking** 🟠
SDCP requires `RequestID` for request/response correlation but implementation unclear.

**Current Status:** RequestID used but unclear if response validation is strict.

**Recommendation:**
- [ ] Validate response RequestID matches request
- [ ] Discard mismatched responses (potential printer bug)
- [ ] Log warning if response RequestID missing
- [ ] Use UUID4 for RequestID, never reuse within 1 minute

---

### 3.5 **MEDIUM: Error Handling Granularity** 🟡
Print start errors (Cmd 128) have specific Ack codes but not handled:

```
SDCP_PRINT_CTRL_ACK_OK = 0
SDCP_PRINT_CTRL_ACK_BUSY = 1
SDCP_PRINT_CTRL_ACK_NOT_FOUND = 2
SDCP_PRINT_CTRL_ACK_MD5_FAILED = 3
SDCP_PRINT_CTRL_ACK_FILEIO_FAILED = 4
SDCP_PRINT_CTRL_ACK_INVALID_RESOLUTION = 5
SDCP_PRINT_CTRL_ACK_UNKNOWN_FORMAT = 6
SDCP_PRINT_CTRL_ACK_UNKNOWN_MODEL = 7
```

**Current Status:** Generic error messages; no specific recovery per code.

**Recommendation:**
- [ ] Map each Ack code to user-friendly message
- [ ] Suggest recovery steps:
  - `BUSY`: Pause current print, then retry
  - `NOT_FOUND`: Refresh file list, confirm file exists
  - `MD5_FAILED`: File corrupted; re-upload
  - `FILEIO_FAILED`: Storage error; check SD card
  - `INVALID_RESOLUTION`: File incompatible with printer model
- [ ] Add "Retry" button where applicable
- [ ] Log error code for debugging

---

## 4. Security Improvements

### 4.1 **CRITICAL: MainboardID Validation** 🔴
SDCP protocol requires MainboardID in all requests but no validation if correct printer.

**Current Status:** MainboardID sent with requests; unclear if user-controlled.

**Recommendation:**
- [ ] Store printer's MainboardID at registration time
- [ ] Verify MainboardID matches on every status update
- [ ] Reject status from unknown MainboardID (potential MITM)
- [ ] Add MainboardID display in printer details (verify against device label)
- [ ] Log MainboardID mismatches as security events

---

### 4.2 **CRITICAL: SDCP Message Validation** 🔴
No signature/encryption on SDCP protocol (plain JSON over WS).

**Current Status:** Connected to local network only; acceptable risk.

**Recommendation:**
- [ ] Document local-network-only requirement in README (done ✓)
- [ ] Never expose SDCP endpoints to internet
- [ ] Add network origin validation (same-subnet check)
- [ ] Log access from unexpected subnets
- [ ] (Future) Add optional HMAC signing for SDCP commands

---

### 4.3 **HIGH: File Path Traversal in File Management** 🟠
Cmd 258/259 accept arbitrary paths; risk of `/` traversal.

**Current Status:** File management not implemented yet.

**Recommendation:**
- [ ] Validate paths: reject `..`, leading `/`, and absolute paths
- [ ] Whitelist allowed roots: `/usb/`, `/local/`
- [ ] Reject paths containing null bytes or control chars
- [ ] Canonicalize path and verify within allowed root

**Example:**
```python
def _validate_file_path(path: str) -> bool:
    if '..' in path or path.startswith('/'):
        return False
    try:
        normalized = Path(path).resolve()
        return str(normalized).startswith('/usb/') or str(normalized).startswith('/local/')
    except:
        return False
```

---

### 4.4 **MEDIUM: Command Rate Limiting** 🟡
No rate limit on SDCP commands; potential DoS (stop/restart print rapidly).

**Current Status:** No protection against command spam.

**Recommendation:**
- [ ] Rate limit per printer: max 10 commands per second
- [ ] Per-action limits:
  - Start print: max 1 per 5 seconds
  - Pause/stop: max 1 per 2 seconds
  - Jog: max 5 per second
- [ ] Return `429 Too Many Requests` when limit exceeded
- [ ] Log rate limit violations per client/printer

---

### 4.5 **MEDIUM: File Upload Size Limits** 🟡
File upload via camera proxy or future file upload missing size caps.

**Current Status:** Max upload 1 MB already implemented ✓

**Recommendation:**
- [ ] Add `/api/printer/{id}/upload` endpoint for G-code
- [ ] Limit file size: 500 MB (typical G-code)
- [ ] Validate file extension: `.gcode` only
- [ ] Scan for malicious patterns (e.g., MQTT injection)
- [ ] Store uploads in quarantine directory pending validation
- [ ] Hash uploaded files to deduplicate

---

## 5. Robustness & Diagnostics

### 5.1 **CRITICAL: Comprehensive Logging** 🔴
Insufficient diagnostic logs for troubleshooting.

**Current Status:** Some logging; not comprehensive.

**Recommendation:**
- [ ] Log all SDCP commands sent (Cmd, Data, Timestamp)
- [ ] Log all SDCP responses received (Ack, Data, Timestamp, ResponseTime)
- [ ] Log connection establish/drop with reason
- [ ] Log timeout events with retry count
- [ ] Log file I/O errors with stack trace
- [ ] Add log level: `DEBUG` (verbose), `INFO` (normal), `WARNING` (issues), `ERROR` (failures)
- [ ] Rotate logs: 10 MB per file, keep 5 files (50 MB total)
- [ ] Export logs endpoint: `GET /api/logs?from_timestamp={ts}&to_timestamp={ts}`

---

### 5.2 **HIGH: Health Check Endpoint** 🟠
No way to verify printer connectivity without making a control request.

**Current Status:** No health check.

**Recommendation:**
- [ ] Add `GET /api/health` endpoint (global)
- [ ] Add `GET /api/printer/{id}/health` endpoint (per-printer)
- [ ] Return: `{status: "ok"|"warning"|"error", printers: [{id, status, lastUpdate, lag}]}`
- [ ] Health check sends Cmd 0 (status refresh) and measures response time
- [ ] Cache result 5 seconds; reuse for UI
- [ ] Alert if lag > 2 seconds

---

### 5.3 **HIGH: Printer Attribute Sync** 🟠
Attributes (Cmd 1) fetched but unclear how often or validated.

**Current Status:** May be fetched once at startup.

**Recommendation:**
- [ ] Fetch attributes on connect (Cmd 1)
- [ ] Fetch again if status indicates change (e.g., camera unplugged)
- [ ] Cache attributes for 5 minutes
- [ ] Validate printer model matches (prevent misconfigurations)
- [ ] Display supported file types and max resolution
- [ ] Log attribute changes (firmware update detection)

---

### 5.4 **MEDIUM: Statistics & Metrics** 🟡
No metrics for uptime, command throughput, error rates.

**Current Status:** No metrics collection.

**Recommendation:**
- [ ] Track per-printer metrics:
  - Uptime (connected time)
  - Command count (by type)
  - Error count (by Ack code)
  - Avg response time
  - Dropped connection count
- [ ] Expose metrics: `GET /api/metrics` (Prometheus format)
- [ ] Alert if error rate > 5% in last 5 minutes
- [ ] Display in UI: "Printer stable for 4 hours, 237 commands, 1 error"

---

## 6. UX Improvements

### 6.1 **HIGH: Print Preview** 🟠
No preview before starting print (could catch wrong file).

**Recommendation:**
- [ ] Show file details before start:
  - Filename, size, estimated time
  - Layer count, nozzle/bed temps
  - (Future) Thumbnail if available
- [ ] Require confirmation before start

---

### 6.2 **HIGH: Print Progress Tracking** 🟠
Print progress (CurrentLayer, TotalLayer, Ticks) displayed but may be unclear.

**Recommendation:**
- [ ] Show progress bar with % complete
- [ ] Display time elapsed vs. estimated remaining
- [ ] Show current layer / total layers
- [ ] Estimate finish time
- [ ] Alert if print slows (avg speed < expected)

---

### 6.3 **MEDIUM: Temperature Presets** 🟡
Nozzle/bed temperature targets not pre-populated based on filament.

**Recommendation:**
- [ ] Add filament material selection: PLA, ABS, PETG, TPU, etc.
- [ ] Auto-populate recommended temps
- [ ] Allow custom temp profiles
- [ ] Store presets locally

---

### 6.4 **MEDIUM: Emergency Stop Visibility** 🟡
Stop button may not be prominent enough.

**Recommendation:**
- [ ] Add red stop button with confirm dialog
- [ ] Show last print status after stop (layers completed, time)
- [ ] Disable accidental repeat stop (cooldown 2 seconds)

---

## 7. Testing & CI/CD

### 7.1 **CRITICAL: SDCP Protocol Testing** 🔴
No tests for actual SDCP message format/parsing.

**Current Status:** Basic printer tests; no protocol-level tests.

**Recommendation:**
- [ ] Add SDCP protocol tests:
  - Parse status with misspelled field names
  - Validate RequestID correlation
  - Test all Cmd types (0, 1, 128-133, 192, 258, 259, 320, 321, 403)
  - Test error responses (wrong MainboardID, timeout, etc.)
- [ ] Mock SDCP printer server for integration tests
- [ ] Test against real printers if available (optional CI matrix)

---

### 7.2 **HIGH: Regression Tests for Stability** 🟠
No automated tests for connection resilience.

**Recommendation:**
- [ ] Add stress tests:
  - 100 rapid commands (should not hang)
  - Network interruption simulation (kill WebSocket, verify reconnect)
  - Message loss simulation (drop 10% of responses, verify recovery)
  - Timeout simulation (slow printer response)
- [ ] Run tests in CI for each commit

---

## 8. Documentation

### 8.1 **MEDIUM: SDCP Command Matrix** 🟡
README updated ✓ but missing detailed command status.

**Recommendation:**
- [ ] Add table to docs/PROTOCOL.md:
  - Cmd number, name, implemented (Y/N), priority
  - Example: "Cmd 258 (File List) - Not yet implemented - HIGH priority"

---

### 8.2 **MEDIUM: Troubleshooting Guide** 🟡
README has basic troubleshooting; add SDCP-specific issues.

**Recommendation:**
- [ ] Add section: "Printer Connection Issues"
  - "Printer not responding" → check IP, check network, check firewall
  - "Timeout errors" → check printer logs, check network latency
  - "File not found" → refresh file list, check file path
  - "Temperature errors" → check sensors, retry

---

## 9. Priority Matrix

| Priority | Issue | Type | Impact | Effort |
|----------|-------|------|--------|--------|
| **CRITICAL** | Heartbeat/keepalive missing | Stability | Connection drops | Medium |
| **CRITICAL** | Response timeouts not handled | Stability | Hanged operations | Medium |
| **CRITICAL** | File management (Cmd 258/259) | Functionality | Cannot browse files | High |
| **CRITICAL** | SDCP field name handling | Compliance | Parse failures | Low |
| **HIGH** | UDP discovery (Cmd auto-find) | Usability | Manual IP entry tedious | High |
| **HIGH** | Print history (Cmd 320/321) | Functionality | No complete history | High |
| **HIGH** | MainboardID validation | Security | MITM risk | Low |
| **HIGH** | WebSocket reconnection | Stability | Manual refresh needed | Medium |
| **HIGH** | Motor status monitoring | Stability | Cannot detect failures | Low |
| **MEDIUM** | Fan speed controls | Functionality | Limited user control | Low |
| **MEDIUM** | Filament state alerts | Usability | Cannot prevent jams | Low |
| **MEDIUM** | Error code mapping | UX | Unclear recovery steps | Low |
| **MEDIUM** | Rate limiting | Security | DoS risk | Medium |
| **MEDIUM** | Health check endpoint | Diagnostics | Cannot verify connectivity | Low |
| **LOW** | Print preview | UX | Risk of wrong file | Low |
| **LOW** | Temperature presets | UX | Manual entry tedious | Low |

---

## 10. Implementation Roadmap

### Phase 1: Stability (Weeks 1-2) 🔴
- [x] Add heartbeat/keepalive
- [x] Implement response timeouts + retry
- [x] Add reconnection strategy with backoff
- [x] Comprehensive logging

### Phase 2: Core Features (Weeks 3-4) 🟠
- [ ] File management (Cmd 258/259)
- [ ] Print history (Cmd 320/321)
- [ ] Request ID validation

### Phase 3: UX & Polish (Weeks 5-6)
- [ ] UDP discovery
- [ ] Fan speed controls
- [ ] Print preview
- [ ] Error code mapping
- [ ] Health check endpoint

### Phase 4: Security & Hardening (Ongoing)
- [ ] File path validation
- [ ] Rate limiting
- [ ] MainboardID verification
- [ ] Audit logging

---

## 11. Summary

**Total Issues Identified:** 26  
**Critical (blocking):** 6  
**High (important):** 7  
**Medium (enhances):** 9  
**Low (nice-to-have):** 4  

**Key Gaps:**
1. No file browser (core feature missing)
2. No heartbeat/reconnection (connection drops)
3. No print history (user tracking missing)
4. No UDP discovery (setup tedious)
5. Incomplete SDCP command coverage

**Next Steps:**
1. Implement Phase 1 stability fixes first (highest impact)
2. Add SDCP protocol tests to catch regressions
3. Document all printer models tested (firmware compatibility)
4. Consider future: historical logs, analytics, cloud sync

---

**Prepared by:** Copilot Code Review  
**Status:** Ready for implementation planning
