export type PrinterType = "cc1" | "cc2";

export type PrintStatusCode =
  | 0   // idle
  | 1   // homing
  | 2 | 3 | 4   // printing
  | 5   // pausing
  | 6   // paused
  | 7   // stopping
  | 8 | 14  // cancelled
  | 9   // complete
  | 10  // checking
  | 12  // recovering
  | 13  // printing (recovery)
  | 15 | 16 | 18 | 19 | 20 | 21;  // warming up / leveling

// PrintInfo.Status codes (from CarbonicSidecar / elegoo-homeassistant)
export const PRINT_STATUS: Record<number, string> = {
  0:  "idle",
  1:  "homing",
  2:  "printing",   // bed dropping
  3:  "printing",
  4:  "printing",   // lifting
  5:  "pausing",
  6:  "paused",
  7:  "stopping",
  8:  "cancelled",
  9:  "complete",
  10: "checking",
  12: "recovering",
  13: "printing",   // printing (recovery)
  14: "cancelled",
  15: "warming up",
  16: "warming up", // preheating
  18: "warming up",
  19: "warming up",
  20: "leveling",
  21: "warming up",
};

export interface PrintInfo {
  Status: number;
  CurrentLayer: number;
  TotalLayer: number;
  CurrentTicks: number;
  TotalTicks: number;
  PrintTime: number;       // seconds elapsed
  RemainTime: number;      // seconds remaining
  TotalExtrusion: number;  // mm
  Filename?: string;
  FileName?: string;       // CC2 variant spelling
  PrintSpeed?: number;     // percentage
}

export interface FanSpeeds {
  ModelFan?: number;
  AuxiliaryFan?: number;
  BoxFan?: number;
}

export interface PrinterStatus {
  PrintInfo?: PrintInfo;
  TempOfNozzle?: number;
  TempTargetNozzle?: number;
  TempOfHotbed?: number;
  TempTargetHotbed?: number;
  TempOfBox?: number;
  TempTargetBox?: number;
  LightStatus?: { SecondLight: boolean; RgbLight?: [number, number, number] };
  CurrentFanSpeed?: FanSpeeds;
  CurrentStatus?: number[];
  // Alternative field names used in some firmware versions
  NozzleTemp?: number;
  NozzleTempTarget?: number;
  BedTemp?: number;
  BedTempTarget?: number;
  ChamberTemp?: number;
  PrintSpeed?: number;
}

export interface PrinterAttrs {
  MainboardID?: string;
  Name?: string;
  FirmwareVersion?: string;
  MachineName?: string;
}

export interface PrinterData {
  id: string;
  ip: string;
  name: string;
  printer_type: PrinterType;
  mainboard_id: string;
  connected: boolean;
  status: PrinterStatus;
  attrs: PrinterAttrs;
  camera_url: string | null;
  thumbnail_url: string | null;
  filament_mm: number;
  filament_g: number;
}

// ─── Utility functions ────────────────────────────────────────────────────────

export function getPrintStatus(printer: PrinterData): string {
  if (!printer.connected) return "offline";
  const pi = printer.status?.PrintInfo;
  const code = pi?.Status;
  if (code === undefined || code === null) return "idle";
  // Special case: CurrentStatus[0] === 9 means homing (between prints)
  const machineCode = printer.status?.CurrentStatus?.[0];
  if (machineCode === 9 && code === 0) return "homing";
  return PRINT_STATUS[code] ?? "idle";
}

export function isActivelyPrinting(printer: PrinterData): boolean {
  const s = getPrintStatus(printer);
  return ["printing", "homing", "warming up", "leveling", "checking", "recovering"].includes(s);
}

export function isPaused(printer: PrinterData): boolean {
  const s = getPrintStatus(printer);
  return ["paused", "pausing"].includes(s);
}

export function isWarmingUp(printer: PrinterData): boolean {
  const s = getPrintStatus(printer);
  return ["warming up", "leveling", "checking"].includes(s);
}

export function getProgress(printer: PrinterData): number {
  const pi = printer.status?.PrintInfo;
  if (!pi) return 0;
  if ((pi.TotalLayer ?? 0) > 0)
    return Math.min(100, Math.round((pi.CurrentLayer / pi.TotalLayer) * 100));
  if ((pi.TotalTicks ?? 0) > 0)
    return Math.min(100, Math.round((pi.CurrentTicks / pi.TotalTicks) * 100));
  return 0;
}

export function getFilename(printer: PrinterData): string {
  return printer.status?.PrintInfo?.Filename || printer.status?.PrintInfo?.FileName || "";
}

export function formatDuration(seconds: number): string {
  if (!seconds || seconds < 0) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  return `${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
}

export function tempColor(
  current: number,
  target: number
): "cold" | "warming" | "ready" | "hot" {
  if (!current || current <= 0) return "cold";
  if (current > 150) return "hot";
  if (target > 0 && current >= target * 0.95) return "ready";
  if (current > 50) return "warming";
  return "cold";
}
