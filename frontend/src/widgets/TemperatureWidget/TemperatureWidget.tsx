import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { usePrinter } from "@/store/printers";
import { tempColor } from "@/types/printer";


interface TempRowProps {
  label: string;
  current: number | undefined;
  target: number | undefined;
  icon: React.ReactNode;
}

function TempRow({ label, current, target, icon }: TempRowProps) {
  const c = current ?? 0;
  const t = target ?? 0;
  const color = {
    cold:    "text-blue-400",
    warming: "text-yellow-400",
    ready:   "text-green-400",
    hot:     "text-red-400",
  }[tempColor(c, t)];

  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="shrink-0 text-muted w-4 h-4 flex items-center justify-center">{icon}</span>
        <span className="text-xs text-muted truncate">{label}</span>
      </div>
      <span className={`text-sm font-mono font-semibold shrink-0 ${color}`}>
        {c.toFixed(1)}°
        {t > 0 && (
          <span className="text-muted font-normal text-xs"> / {t}°</span>
        )}
      </span>
    </div>
  );
}

export function TemperatureWidget({ printerId }: WidgetComponentProps) {
  const printer = usePrinter(printerId);

  if (!printer) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        No printer selected
      </div>
    );
  }

  const s = printer.status;

  return (
    <div className="h-full p-4 flex flex-col gap-2">
      <span className="text-xs font-medium text-muted uppercase tracking-wide">
        Temperatures
      </span>
      <div className="flex-1 flex flex-col justify-center gap-3">
        <TempRow
          label="Nozzle"
          current={s.TempOfNozzle ?? s.NozzleTemp}
          target={s.TempTargetNozzle ?? s.NozzleTempTarget}
          icon={<img src="/assets/nozzle-icon.png" alt="" className="w-4 h-4" />}
        />
        <TempRow
          label="Bed"
          current={s.TempOfHotbed ?? s.BedTemp}
          target={s.TempTargetHotbed ?? s.BedTempTarget}
          icon={<img src="/assets/hot-bed.png" alt="" className="w-4 h-4" />}
        />
        {(s.TempOfBox ?? s.ChamberTemp) != null && (
          <TempRow
            label="Chamber"
            current={s.TempOfBox ?? s.ChamberTemp}
            target={s.TempTargetBox}
            icon={<img src="/assets/box-icon.png" alt="" className="w-4 h-4" />}
          />
        )}
      </div>
    </div>
  );
}

export const TemperatureWidgetDef: WidgetDef = {
  id: "temperature",
  name: "Temperatures",
  category: "printer",
  allowedSizes: ["compact", "small", "medium"],
  defaultSize: "small",
  requiresPrinterBinding: true,
  component: TemperatureWidget,
};
