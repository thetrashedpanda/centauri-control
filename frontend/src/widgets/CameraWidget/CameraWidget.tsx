import { useEffect, useState } from "react";
import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { usePrinter } from "@/store/printers";

export function CameraWidget({ printerId }: WidgetComponentProps) {
  const printer = usePrinter(printerId);
  const [streamError, setStreamError] = useState(false);
  const [retryAttempt, setRetryAttempt] = useState(0);

  useEffect(() => {
    setStreamError(false);
    setRetryAttempt(0);
  }, [printer?.id, printer?.camera_url]);

  useEffect(() => {
    if (!streamError) return;
    const delay = Math.min(1000 * 2 ** retryAttempt, 15000);
    const timer = window.setTimeout(() => {
      setRetryAttempt((attempt) => attempt + 1);
      setStreamError(false);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [retryAttempt, streamError]);

  if (!printer) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        No printer selected
      </div>
    );
  }

  const streamUrl = printer.camera_url
    ? `/camera/${encodeURIComponent(printer.id)}/stream?retry=${retryAttempt}`
    : null;

  if (!printer.connected || !streamUrl) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        {!printer.connected ? "Printer offline" : "Camera unavailable"}
      </div>
    );
  }

  return (
    <div className="h-full flex items-center justify-center bg-black overflow-hidden rounded-b-xl">
      {streamError ? (
        <div className="text-muted text-sm text-center p-4">
          <p>Camera interrupted. Reconnecting…</p>
          <button
            onClick={() => {
              setRetryAttempt((attempt) => attempt + 1);
              setStreamError(false);
            }}
            className="mt-2 text-accent text-xs underline"
          >
            Reconnect now
          </button>
        </div>
      ) : (
        <img
          src={streamUrl}
          alt="Camera stream"
          className="w-full h-full object-contain"
          onError={() => setStreamError(true)}
        />
      )}
    </div>
  );
}

export const CameraWidgetDef: WidgetDef = {
  id: "camera",
  name: "Camera",
  category: "printer",
  allowedSizes: ["medium", "large", "wide", "full"],
  defaultSize: "medium",
  requiresPrinterBinding: true,
  component: CameraWidget,
};
