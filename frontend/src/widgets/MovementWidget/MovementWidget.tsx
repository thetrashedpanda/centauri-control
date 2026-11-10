import { useState } from "react";
import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { usePrinter } from "@/store/printers";
import { sendAction } from "@/ws/useWebSocket";
import { getPrintStatus } from "@/types/printer";

const AXES = ["X", "Y", "Z"] as const;
const STEP_SIZES = [0.1, 1, 10, 100] as const;

export function MovementWidget({ printerId }: WidgetComponentProps) {
  const printer = usePrinter(printerId);
  const [stepSize, setStepSize] = useState<number>(1);

  if (!printer) return (
    <div className="h-full flex items-center justify-center text-muted text-sm">No printer selected</div>
  );

  const canMove = printer.connected && ["idle", "complete", "cancelled"].includes(getPrintStatus(printer));

  return (
    <div className="h-full p-3 flex flex-col gap-2 overflow-y-auto">
      <span className="text-xs font-medium text-muted uppercase tracking-wide">Movement</span>
      <label className="flex items-center justify-between gap-2 text-xs text-muted">
        Step size
        <select
          value={stepSize}
          onChange={(event) => setStepSize(Number(event.target.value))}
          disabled={!canMove}
          className="rounded bg-surface2 px-2 py-1 text-fg disabled:opacity-40"
        >
          {STEP_SIZES.map((step) => <option key={step} value={step}>{step} mm</option>)}
        </select>
      </label>
      <div className="grid grid-cols-[auto_1fr_1fr_1fr] items-center gap-1">
        <span />
        {AXES.map((axis) => (
          <span key={axis} className="text-center text-xs text-muted">{axis}</span>
        ))}
        <span className="text-xs text-muted">Jog −</span>
        {AXES.map((axis) => (
          <button
            key={axis}
            type="button"
            disabled={!canMove}
            aria-label={`Jog ${axis} negative ${stepSize} mm`}
            onClick={() => sendAction({
              action: "jog",
              printer_id: printer.id,
              axis,
              distance: -stepSize,
            })}
            className="rounded bg-surface2 py-1 text-xs text-fg hover:bg-border disabled:cursor-not-allowed disabled:opacity-40"
          >−</button>
        ))}
        <span className="text-xs text-muted">Jog +</span>
        {AXES.map((axis) => (
          <button
            key={axis}
            type="button"
            disabled={!canMove}
            aria-label={`Jog ${axis} positive ${stepSize} mm`}
            onClick={() => sendAction({
              action: "jog",
              printer_id: printer.id,
              axis,
              distance: stepSize,
            })}
            className="rounded bg-surface2 py-1 text-xs text-fg hover:bg-border disabled:cursor-not-allowed disabled:opacity-40"
          >+</button>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-1">
        {AXES.map((axis) => (
          <button
            key={axis}
            type="button"
            disabled={!canMove}
            onClick={() => sendAction({ action: "home", printer_id: printer.id, axis })}
            className="rounded bg-surface2 py-1.5 text-xs text-fg hover:bg-border disabled:cursor-not-allowed disabled:opacity-40"
          >Home {axis}</button>
        ))}
      </div>
      {!canMove && (
        <p className="text-xs text-yellow-400">
          {printer.connected ? "Movement is disabled while the printer is busy." : "Printer is currently offline."}
        </p>
      )}
    </div>
  );
}

export const MovementWidgetDef: WidgetDef = {
  id: "movement",
  name: "Movement",
  category: "printer",
  allowedSizes: ["small", "medium"],
  defaultSize: "small",
  requiresPrinterBinding: true,
  component: MovementWidget,
};
