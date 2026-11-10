import type { PrinterData, PrinterType } from "./printer";
import type { SpoolData } from "./spool";
import type { HistoryEntry } from "./history";
import type { IntegrationStatus } from "./integration";

export interface FileEntry {
  name: string;
  type: 0 | 1;    // 0=folder, 1=file
  size?: number;
}

export interface DiscoveredPrinter {
  ip: string;
  name: string;
  mainboard_id: string;
  printer_type: PrinterType;
}

export type InboundMessage =
  | { type: "printer_update"; printer: PrinterData }
  | { type: "printer_removed"; printer_id: string }
  | { type: "integration_update"; status: IntegrationStatus }
  | { type: "discovered"; printer: DiscoveredPrinter }
  | { type: "info"; message: string }
  | { type: "error"; printer_id?: string; message: string }
  | { type: "history_entry"; entry: HistoryEntry }
  | { type: "spool_empty"; spool: SpoolData; printer_id: string }
  | { type: "spool_low"; spool: SpoolData; printer_id: string }
  | { type: "file_list"; printer_id: string; ack: number; files: FileEntry[] }
  | { type: "printer_history_list"; printer_id: string; history: string[] }
  | { type: "printer_history_detail"; printer_id: string; items: Record<string, unknown>[] };

export type OutboundAction =
  | { action: "list_printers" }
  | { action: "discover" }
  | { action: "add_printer"; ip: string; name?: string; printer_type: PrinterType; access_code?: string }
  | { action: "remove_printer"; printer_id: string }
  | { action: "update_printer"; printer_id: string; name?: string; access_code?: string }
  | { action: "pause" | "resume" | "stop" | "status"; printer_id: string }
  | { action: "light_on" | "light_off"; printer_id: string }
  | { action: "camera_on" | "camera_off"; printer_id: string }
  | { action: "stop_feed" | "skip_preheat"; printer_id: string }
  | { action: "timelapse_on" | "timelapse_off"; printer_id: string }
  | { action: "list_files"; printer_id: string; url: string }
  | { action: "delete_files"; printer_id: string; files: string[] }
  | { action: "start_print"; printer_id: string; filename: string; start_layer?: number }
  | { action: "set_speed"; printer_id: string; speed_pct: number }
  | { action: "set_fans"; printer_id: string; ModelFan?: number; AuxiliaryFan?: number; BoxFan?: number }
  | { action: "jog"; printer_id: string; axis: "X" | "Y" | "Z"; distance: number }
  | { action: "home"; printer_id: string; axis: "X" | "Y" | "Z" }
  | { action: "printer_history"; printer_id: string }
  | { action: "history_detail"; printer_id: string; ids: string[] }
  | { action: "set_printer_name"; printer_id: string; name: string };
