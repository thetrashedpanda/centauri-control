import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { usePrinter } from "@/store/printers";
import { useSpoolsStore } from "@/store/spools";
import { spoolRemainingPercent } from "@/types/spool";
import { ProgressBar } from "@/components/ProgressBar/ProgressBar";

export function SpoolWidget({ printerId }: WidgetComponentProps) {
  const printer = usePrinter(printerId);
  const getSpool = useSpoolsStore((s) => s.getSpoolForPrinter);
  const spool = printerId ? getSpool(printerId) : undefined;

  if (!printer) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        No printer selected
      </div>
    );
  }

  if (!spool) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        No spool assigned
      </div>
    );
  }

  const pct = spoolRemainingPercent(spool);
  const remaining = Math.round(spool.remaining_weight);
  const total = Math.round(spool.initial_weight);
  const color = `#${spool.filament.color_hex}`;

  return (
    <div className="h-full p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div
          className="w-4 h-4 rounded-full border border-border shrink-0"
          style={{ backgroundColor: color }}
        />
        <span className="font-medium text-fg text-sm truncate">
          {spool.filament.vendor.name} {spool.filament.name}
        </span>
      </div>
      <span className="text-xs text-muted">{spool.filament.material}</span>
      <div className="flex items-baseline justify-between">
        <span className="text-2xl font-bold text-fg tabular-nums">{pct}%</span>
        <span className="text-xs text-muted">{remaining}g / {total}g</span>
      </div>
      <ProgressBar
        value={pct}
        colorClass={pct < 10 ? "bg-red-500" : pct < 25 ? "bg-yellow-500" : "bg-accent"}
      />
    </div>
  );
}

export const SpoolWidgetDef: WidgetDef = {
  id: "spool",
  name: "Active Spool",
  category: "spools",
  allowedSizes: ["small", "medium"],
  defaultSize: "small",
  requiresPrinterBinding: true,
  component: SpoolWidget,
};
