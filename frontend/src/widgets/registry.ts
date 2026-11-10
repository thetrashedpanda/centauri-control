import type { WidgetDef } from "@/types/widget";
import { PrinterStatusWidgetDef } from "./PrinterStatusWidget/PrinterStatusWidget";
import { CameraWidgetDef } from "./CameraWidget/CameraWidget";
import { TemperatureWidgetDef } from "./TemperatureWidget/TemperatureWidget";
import { ControlsWidgetDef } from "./ControlsWidget/ControlsWidget";
import { MovementWidgetDef } from "./MovementWidget/MovementWidget";
import { SpoolWidgetDef } from "./SpoolWidget/SpoolWidget";
import { SpoolInventoryWidgetDef } from "./SpoolInventoryWidget/SpoolInventoryWidget";
import { FileBrowserWidgetDef } from "./FileBrowserWidget/FileBrowserWidget";
import { HistoryWidgetDef } from "./HistoryWidget/HistoryWidget";
import { OpenFilamentSensorWidgetDef } from "./OpenFilamentSensorWidget/OpenFilamentSensorWidget";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const WIDGET_REGISTRY: Record<string, WidgetDef<any>> = {
  [PrinterStatusWidgetDef.id]:   PrinterStatusWidgetDef,   // "printer-status" — Print Status (progress + info)
  [CameraWidgetDef.id]:          CameraWidgetDef,
  [TemperatureWidgetDef.id]:     TemperatureWidgetDef,
  [ControlsWidgetDef.id]:        ControlsWidgetDef,        // "controls" — Printer Controls (actions + speed/fans)
  [MovementWidgetDef.id]:        MovementWidgetDef,        // "movement" — X/Y/Z jog + homing
  [SpoolWidgetDef.id]:           SpoolWidgetDef,
  [SpoolInventoryWidgetDef.id]:  SpoolInventoryWidgetDef,
  [FileBrowserWidgetDef.id]:     FileBrowserWidgetDef,
  [HistoryWidgetDef.id]:         HistoryWidgetDef,
  [OpenFilamentSensorWidgetDef.id]: OpenFilamentSensorWidgetDef,
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getWidgetDef(widgetId: string): WidgetDef<any> | undefined {
  // Handle old IDs that were merged into existing widgets
  if (widgetId === "progress") return WIDGET_REGISTRY["printer-status"];
  if (widgetId === "speed-fans") return WIDGET_REGISTRY["controls"];
  return WIDGET_REGISTRY[widgetId];
}
