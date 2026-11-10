import { useState } from "react";
import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { usePrinter } from "@/store/printers";
import { StatusBadge } from "@/components/StatusBadge/StatusBadge";
import { ProgressBar } from "@/components/ProgressBar/ProgressBar";
import { getProgress, getFilename, formatDuration } from "@/types/printer";

export function PrinterStatusWidget({ printerId }: WidgetComponentProps) {
  const printer = usePrinter(printerId);
  const [thumbError, setThumbError] = useState(false);

  if (!printer) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        No printer selected
      </div>
    );
  }

  const pi = printer.status?.PrintInfo;
  const filename = getFilename(printer);
  const pct = getProgress(printer);
  const hasThumbnail = !!printer.thumbnail_url && !thumbError;

  return (
    <div className="h-full p-4 flex flex-col gap-3 overflow-hidden">
      {/* Header: name + status */}
      <div className="flex items-center justify-between shrink-0">
        <span className="font-semibold text-fg truncate">{printer.name}</span>
        <StatusBadge printer={printer} />
      </div>

      {/* Thumbnail + progress side-by-side when thumbnail is available */}
      <div className="flex gap-3 flex-1 min-h-0">
        {hasThumbnail && (
          <div className="shrink-0 w-24 h-24 rounded-lg overflow-hidden bg-surface2 border border-border">
            <img
              src={printer.thumbnail_url!}
              alt="Print preview"
              className="w-full h-full object-contain"
              onError={() => setThumbError(true)}
            />
          </div>
        )}

        <div className="flex-1 flex flex-col gap-2 min-w-0">
          {filename && (
            <p className="text-xs text-fg truncate" title={filename}>{filename}</p>
          )}

          {/* Progress */}
          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-bold text-fg tabular-nums">{pct}%</span>
            {pi?.CurrentLayer != null && (pi.TotalLayer ?? 0) > 0 && (
              <span className="text-xs text-muted">
                Layer {pi.CurrentLayer} / {pi.TotalLayer}
              </span>
            )}
          </div>
          <ProgressBar value={pct} />

          {/* Times */}
          <div className="flex justify-between text-xs text-muted">
            {pi?.PrintTime != null && pi.PrintTime > 0 && (
              <span>
                Elapsed:{" "}
                <span className="text-fg">{formatDuration(pi.PrintTime)}</span>
              </span>
            )}
            {pi?.RemainTime != null && pi.RemainTime > 0 && (
              <span>
                Left:{" "}
                <span className="text-fg">{formatDuration(pi.RemainTime)}</span>
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Footer meta */}
      <div className="text-xs text-muted space-y-0.5 shrink-0 border-t border-border pt-2">
        <div>
          <span className="text-gray-500">IP:</span>{" "}
          <span className="text-gray-300">{printer.ip}</span>
          {printer.attrs.FirmwareVersion && (
            <span className="ml-3">
              <span className="text-gray-500">FW:</span>{" "}
              <span className="text-gray-300">{printer.attrs.FirmwareVersion as string}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export const PrinterStatusWidgetDef: WidgetDef = {
  id: "printer-status",
  name: "Print Status",
  category: "printer",
  allowedSizes: ["small", "medium", "wide"],
  defaultSize: "medium",
  requiresPrinterBinding: true,
  component: PrinterStatusWidget,
};
