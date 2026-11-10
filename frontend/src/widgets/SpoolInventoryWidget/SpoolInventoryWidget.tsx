import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { useSpoolsStore } from "@/store/spools";
import { spoolRemainingPercent, isSpoolLow, isSpoolEmpty } from "@/types/spool";

export function SpoolInventoryWidget(_props: WidgetComponentProps) {
  const spools = useSpoolsStore((s) => s.spools);

  if (!spools.length) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        No spools in Spoolman
      </div>
    );
  }

  return (
    <div className="h-full p-4 flex flex-col gap-2 overflow-y-auto">
      <span className="text-xs font-medium text-muted uppercase tracking-wide mb-1">
        Spool Inventory
      </span>
      {spools.map((spool) => {
        const pct = spoolRemainingPercent(spool);
        const low = isSpoolLow(spool);
        const empty = isSpoolEmpty(spool);
        const barColor = empty
          ? "bg-red-500"
          : low
          ? "bg-yellow-500"
          : "bg-green-600";

        return (
          <div key={spool.id} className="flex items-center gap-3 py-1">
            <div
              className="w-3 h-3 rounded-full border border-border shrink-0"
              style={{ backgroundColor: `#${spool.filament.color_hex}` }}
            />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-fg truncate">
                {spool.filament.vendor.name} {spool.filament.name}
                <span className="text-muted ml-1">{spool.filament.material}</span>
              </p>
              <div className="mt-1 h-1.5 bg-surface2 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${barColor}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
            <span
              className={`text-xs tabular-nums shrink-0 ${
                empty ? "text-red-400" : low ? "text-yellow-400" : "text-muted"
              }`}
            >
              {pct}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

export const SpoolInventoryWidgetDef: WidgetDef = {
  id: "spool-inventory",
  name: "Spool Inventory",
  category: "spools",
  allowedSizes: ["medium", "large", "wide"],
  defaultSize: "medium",
  requiresPrinterBinding: false,
  component: SpoolInventoryWidget,
};
