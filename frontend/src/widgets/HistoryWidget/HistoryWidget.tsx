import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { api } from "@/api/client";
import { useState, useEffect } from "react";
import type { HistoryEntry } from "@/types/history";
import { formatFilamentUsage, formatPrintDuration } from "@/types/history";

export function HistoryWidget(_props: WidgetComponentProps) {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<HistoryEntry[]>("/api/history")
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="h-full p-4 flex flex-col gap-2">
      <span className="text-xs font-medium text-muted uppercase tracking-wide">
        Print History
      </span>
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-muted text-sm">
          Loading…
        </div>
      ) : !history.length ? (
        <div className="flex-1 flex items-center justify-center text-muted text-sm">
          No history yet
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-2">
          {[...history].reverse().map((entry, i) => (
            <div key={i} className="border border-border rounded-lg px-3 py-2 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-fg truncate">{entry.filename}</span>
                <span
                  className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${
                    entry.completed
                      ? "bg-green-900 text-green-300"
                      : "bg-red-900 text-red-300"
                  }`}
                >
                  {entry.completed ? "Done" : "Cancelled"}
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-muted">
                <span>{entry.printer_name}</span>
                <span>{formatPrintDuration(entry)}</span>
                <span>{formatFilamentUsage(entry)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export const HistoryWidgetDef: WidgetDef = {
  id: "history",
  name: "Print History",
  category: "history",
  allowedSizes: ["medium", "large", "wide", "full"],
  defaultSize: "large",
  requiresPrinterBinding: false,
  component: HistoryWidget,
};
