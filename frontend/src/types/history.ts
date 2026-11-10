export interface HistoryEntry {
  timestamp: string;    // ISO 8601
  printer_id: string;
  printer_name: string;
  filename: string;
  filament_mm: number;
  filament_g: number;
  print_time_s: number;
  completed: boolean;
}

// ─── Helper functions ─────────────────────────────────────────────────────────

/** Formats filament usage as e.g. "1.23m · 3.6g" */
export function formatFilamentUsage(entry: HistoryEntry): string {
  const m = (entry.filament_mm / 1000).toFixed(2);
  return `${m}m · ${entry.filament_g}g`;
}

/** Formats print duration as e.g. "2h 15m" or "45m 12s" */
export function formatPrintDuration(entry: HistoryEntry): string {
  const seconds = entry.print_time_s;
  if (!seconds || seconds < 0) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  return `${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
}
