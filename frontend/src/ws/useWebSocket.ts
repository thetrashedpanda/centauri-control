import { useEffect, useRef } from "react";
import type { InboundMessage, OutboundAction } from "@/types/ws-messages";
import { usePrintersStore } from "@/store/printers";
import { useIntegrationsStore } from "@/store/integrations";
import { useUiStore } from "@/store/ui";

const WS_PORT = 8765;
const WS_URL = window.location.port === "5173"
  ? `ws://${window.location.host}/ws`
  : `wss://${window.location.hostname}:${WS_PORT}`;

// Exponential backoff for unstable links, with jitter to avoid synchronized retries.
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS  = 30000;
const STABLE_CONNECTION_MS = 30000;

let _socket: WebSocket | null = null;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _stableConnectionTimer: ReturnType<typeof setTimeout> | null = null;
let _reconnectAttempts = 0;

function getSocket(): WebSocket | null {
  return _socket;
}

export function sendAction(action: OutboundAction): void {
  if (_socket?.readyState === WebSocket.OPEN) {
    _socket.send(JSON.stringify(action));
  }
}

function handleMessage(raw: string): void {
  let msg: InboundMessage;
  try {
    msg = JSON.parse(raw) as InboundMessage;
  } catch {
    return;
  }

  const { upsertPrinter, removePrinter, addDiscovered } = usePrintersStore.getState();
  const { upsertStatus, removePrinter: removeIntegrationStatus } = useIntegrationsStore.getState();
  const { addToast } = useUiStore.getState();

  switch (msg.type) {
    case "printer_update":
      upsertPrinter(msg.printer);
      break;
    case "printer_removed":
      removePrinter(msg.printer_id);
      removeIntegrationStatus(msg.printer_id);
      break;
    case "integration_update":
      upsertStatus(msg.status);
      break;
    case "discovered":
      addDiscovered(msg.printer);
      break;
    case "error":
      addToast(msg.message, "error");
      break;
    case "info":
      addToast(msg.message, "info");
      break;
    default:
      break;
  }
}

function scheduleReconnect(): void {
  if (_reconnectTimer) return;
  const baseDelay = Math.min(RECONNECT_BASE_MS * 2 ** _reconnectAttempts, RECONNECT_MAX_MS);
  const delay = Math.round(baseDelay * (0.8 + Math.random() * 0.4));
  _reconnectAttempts++;
  console.log(`[WS] Reconnecting in ${delay / 1000}s (attempt ${_reconnectAttempts})…`);
  _reconnectTimer = setTimeout(() => {
    _reconnectTimer = null;
    connect();
  }, delay);
}

function connect(): void {
  if (_socket && _socket.readyState <= WebSocket.OPEN) return;

  _socket = new WebSocket(WS_URL);

  _socket.onopen = () => {
    console.log("[WS] Connected");
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer);
      _reconnectTimer = null;
    }
    if (_stableConnectionTimer) clearTimeout(_stableConnectionTimer);
    _stableConnectionTimer = setTimeout(() => {
      _reconnectAttempts = 0;
      _stableConnectionTimer = null;
    }, STABLE_CONNECTION_MS);
  };

  _socket.onmessage = (e: MessageEvent<string>) => {
    handleMessage(e.data);
  };

  _socket.onclose = (e) => {
    // Code 1000 = normal close (e.g. server restart); still reconnect.
    console.log(`[WS] Closed (code=${e.code}), scheduling reconnect…`);
    if (_stableConnectionTimer) {
      clearTimeout(_stableConnectionTimer);
      _stableConnectionTimer = null;
    }
    _socket = null;
    scheduleReconnect();
  };

  _socket.onerror = () => {
    // onerror is always followed by onclose, so reconnect is handled there.
    _socket?.close();
  };
}

export function useWebSocket(): void {
  const mounted = useRef(false);

  useEffect(() => {
    if (mounted.current) return;
    mounted.current = true;
    connect();
  }, []);
}

export { getSocket };
