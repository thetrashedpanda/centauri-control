import { useState } from "react";
import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { usePrinter } from "@/store/printers";
import { sendAction } from "@/ws/useWebSocket";
import { isActivelyPrinting, isPaused } from "@/types/printer";

const SPEED_PRESETS = [
  { label: "Ludicrous", pct: 150 },
  { label: "Sport",     pct: 125 },
  { label: "Balanced",  pct: 100 },
  { label: "Silent",    pct: 50  },
] as const;

type FanKey = "ModelFan" | "AuxiliaryFan" | "BoxFan";

function Btn({
  label, onClick, variant = "default", disabled = false,
}: {
  label: string; onClick: () => void;
  variant?: "default" | "danger" | "accent"; disabled?: boolean;
}) {
  const cls = {
    default: "bg-surface2 hover:bg-border text-fg",
    danger:  "bg-red-800 hover:bg-red-700 text-red-100",
    accent:  "bg-accent hover:bg-orange-600 text-white",
  }[variant];
  return (
    <button onClick={onClick} disabled={disabled}
      className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${cls}`}>
      {label}
    </button>
  );
}

function Toggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`relative shrink-0 w-9 h-5 rounded-full transition-colors ${on ? "bg-accent" : "bg-surface2 border border-border"}`}
    >
      <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${on ? "left-4" : "left-0.5"}`} />
    </button>
  );
}

function FanControl({
  label, speed, on, onToggle, onAdjust,
}: {
  label: string;
  speed: number;
  on: boolean;
  onToggle: () => void;
  onAdjust: (delta: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      {/* Row 1: icon + name + toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <img src="/assets/fan.png" alt="" className="w-4 h-4" />
          <span className="text-xs text-muted">{label}</span>
        </div>
        <Toggle on={on} onToggle={onToggle} />
      </div>
      {/* Row 2: − speed% + indented under the name */}
      <div className="flex items-center gap-2 pl-5">
        <button
          onClick={() => onAdjust(-10)}
          disabled={speed <= 0}
          className="w-6 h-5 rounded bg-surface2 hover:bg-border text-fg text-sm flex items-center justify-center disabled:opacity-30 leading-none"
        >−</button>
        <span className="flex-1 text-center text-xs text-fg tabular-nums">{speed}%</span>
        <button
          onClick={() => onAdjust(10)}
          disabled={speed >= 100}
          className="w-6 h-5 rounded bg-surface2 hover:bg-border text-fg text-sm flex items-center justify-center disabled:opacity-30 leading-none"
        >+</button>
      </div>
    </div>
  );
}

export function ControlsWidget({ printerId }: WidgetComponentProps) {
  const printer = usePrinter(printerId);
  const [speedPreset, setSpeedPreset] = useState(2);

  // Pending speed per fan — what will be sent when the fan is toggled on, or adjusted while off
  const [pending, setPending] = useState<Record<FanKey, number>>({
    ModelFan: 100, AuxiliaryFan: 100, BoxFan: 50,
  });

  if (!printer) return (
    <div className="h-full flex items-center justify-center text-muted text-sm">No printer selected</div>
  );
  if (!printer.connected) return (
    <div className="h-full flex items-center justify-center text-muted text-sm">Printer offline</div>
  );

  const pid      = printer.id;
  const printing = isActivelyPrinting(printer);
  const paused   = isPaused(printer);
  const lightOn  = !!(printer.status?.LightStatus as { SecondLight?: boolean | number } | undefined)?.SecondLight;

  const fanSpeeds = printer.status?.CurrentFanSpeed as Partial<Record<FanKey, number>> | undefined;
  const modelFan   = fanSpeeds?.ModelFan    ?? 0;
  const auxFan     = fanSpeeds?.AuxiliaryFan ?? 0;
  const chamberFan = fanSpeeds?.BoxFan       ?? 0;

  // Displayed speed: actual printer speed when on, pending speed when off
  const displaySpeed = (key: FanKey, actual: number): number =>
    actual > 0 ? actual : pending[key];

  function sendFan(key: FanKey, value: number) {
    sendAction({ action: "set_fans", printer_id: pid, [key]: Math.min(100, Math.max(0, value)) });
  }

  function handleToggle(key: FanKey, actual: number) {
    if (actual > 0) {
      setPending((p) => ({ ...p, [key]: actual })); // remember current speed
      sendFan(key, 0);
    } else {
      sendFan(key, pending[key]);
    }
  }

  function handleAdjust(key: FanKey, actual: number, delta: number) {
    const base = actual > 0 ? actual : pending[key];
    const next = Math.min(100, Math.max(0, base + delta));
    setPending((p) => ({ ...p, [key]: next }));
    if (actual > 0) sendFan(key, next); // only send live if fan is on
  }

  return (
    <div className="h-full p-3 flex flex-col gap-2.5 overflow-y-auto">
      <span className="text-xs font-medium text-muted uppercase tracking-wide">Controls</span>

      {/* Print actions */}
      <div className="flex gap-1.5">
        {printing && !paused && (
          <Btn label="Pause"  onClick={() => sendAction({ action: "pause",  printer_id: pid })} />
        )}
        {paused && (
          <Btn label="Resume" onClick={() => sendAction({ action: "resume", printer_id: pid })} variant="accent" />
        )}
        {(printing || paused) && (
          <Btn label="Stop"   onClick={() => sendAction({ action: "stop",   printer_id: pid })} variant="danger" />
        )}
        {printing && (
          <Btn label="Skip Preheat" onClick={() => sendAction({ action: "skip_preheat", printer_id: pid })} />
        )}
        {!printing && !paused && (
          <span className="text-xs text-muted italic self-center">Idle</span>
        )}
      </div>

      {/* Print speed */}
      <div className="border-t border-border pt-2 flex flex-col gap-1">
        <span className="text-xs text-muted">Print Speed</span>
        <select
          value={speedPreset}
          onChange={(e) => {
            const idx = Number(e.target.value);
            setSpeedPreset(idx);
            sendAction({ action: "set_speed", printer_id: pid, speed_pct: SPEED_PRESETS[idx].pct });
          }}
          className="w-full bg-surface2 border border-border rounded-lg px-2.5 py-1 text-xs text-fg focus:outline-none focus:border-accent"
        >
          {SPEED_PRESETS.map((p, i) => (
            <option key={p.label} value={i}>{p.label}</option>
          ))}
        </select>
      </div>

      {/* Chamber light */}
      <div className="border-t border-border pt-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <img src="/assets/light.png" alt="" className="w-4 h-4" />
          <span className="text-xs text-muted">Chamber Light</span>
        </div>
        <Toggle
          on={lightOn}
          onToggle={() => sendAction({ action: lightOn ? "light_off" : "light_on", printer_id: pid })}
        />
      </div>

      {/* Fans */}
      <div className="border-t border-border pt-2 flex flex-col gap-2.5">
        <FanControl
          label="Model Fan"
          on={modelFan > 0}
          speed={displaySpeed("ModelFan", modelFan)}
          onToggle={() => handleToggle("ModelFan", modelFan)}
          onAdjust={(d) => handleAdjust("ModelFan", modelFan, d)}
        />
        <FanControl
          label="Aux Fan"
          on={auxFan > 0}
          speed={displaySpeed("AuxiliaryFan", auxFan)}
          onToggle={() => handleToggle("AuxiliaryFan", auxFan)}
          onAdjust={(d) => handleAdjust("AuxiliaryFan", auxFan, d)}
        />
        <FanControl
          label="Chamber Fan"
          on={chamberFan > 0}
          speed={displaySpeed("BoxFan", chamberFan)}
          onToggle={() => handleToggle("BoxFan", chamberFan)}
          onAdjust={(d) => handleAdjust("BoxFan", chamberFan, d)}
        />
      </div>
    </div>
  );
}

export const ControlsWidgetDef: WidgetDef = {
  id: "controls",
  name: "Printer Controls",
  category: "printer",
  allowedSizes: ["small", "medium", "wide"],
  defaultSize: "medium",
  requiresPrinterBinding: true,
  component: ControlsWidget,
};
