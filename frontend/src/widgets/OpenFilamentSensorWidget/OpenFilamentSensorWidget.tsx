import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { useOpenFilamentSensor } from "@/store/integrations";

function percentage(value: number): string {
  return `${Math.max(0, Math.min(100, Math.round(value)))}%`;
}

export function OpenFilamentSensorWidget({ printerId }: WidgetComponentProps) {
  const status = useOpenFilamentSensor(printerId);

  if (!printerId) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        Select a printer for this sensor
      </div>
    );
  }

  if (!status?.enabled) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 text-center p-4">
        <p className="text-sm text-fg font-medium">OpenFilament Sensor not configured</p>
        <p className="text-xs text-muted">Add and configure it in Settings → Integrations.</p>
      </div>
    );
  }

  if (!status.connected || !status.data) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 text-center p-4">
        <p className="text-sm text-yellow-400">Sensor unavailable</p>
        <p className="text-xs text-muted">{status.error ?? "Waiting for sensor status"}</p>
        {status.last_seen && (
          <p className="text-xs text-muted">Last contact: {new Date(status.last_seen).toLocaleTimeString()}</p>
        )}
      </div>
    );
  }

  const filament = status.data.filament;
  const condition = filament.runout
    ? { label: "Runout", color: "text-red-400" }
    : filament.hard_jam_percent >= 100 || filament.soft_jam_percent >= 100
    ? { label: "Jam detected", color: "text-red-400" }
    : filament.grace_active
    ? { label: "Detection grace period", color: "text-yellow-400" }
    : { label: "Monitoring", color: "text-green-400" };

  return (
    <div className="h-full p-4 flex flex-col gap-3 overflow-y-auto">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-fg">OpenFilament Sensor</span>
        <span className={`text-xs font-medium ${condition.color}`}>{condition.label}</span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-surface2 p-3">
          <p className="text-xs text-muted">Hard jam</p>
          <p className="text-xl font-semibold text-fg tabular-nums">{percentage(filament.hard_jam_percent)}</p>
        </div>
        <div className="rounded-lg bg-surface2 p-3">
          <p className="text-xs text-muted">Soft jam</p>
          <p className="text-xl font-semibold text-fg tabular-nums">{percentage(filament.soft_jam_percent)}</p>
        </div>
      </div>

      <div className="text-xs text-muted space-y-1">
        <p>Runout: <span className={filament.runout ? "text-red-400" : "text-fg"}>{filament.runout ? "detected" : "clear"}</span></p>
        <p>Motion pulses: <span className="text-fg tabular-nums">{filament.movement_pulses}</span></p>
        <p>Flow telemetry: <span className="text-fg">{filament.telemetry_available ? "available" : "unavailable"}</span></p>
      </div>

      <p className="text-[11px] text-muted mt-auto border-t border-border pt-2">
        Jam detection and printer pausing are controlled by OpenFilament Sensor.
      </p>
    </div>
  );
}

export const OpenFilamentSensorWidgetDef: WidgetDef = {
  id: "openfilament-sensor",
  name: "OpenFilament Sensor",
  category: "printer",
  allowedSizes: ["small", "medium", "wide"],
  defaultSize: "small",
  requiresPrinterBinding: true,
  component: OpenFilamentSensorWidget,
};
