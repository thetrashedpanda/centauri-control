import { create } from "zustand";
import { useShallow } from "zustand/shallow";
import type { PrinterData } from "@/types/printer";
import type { DiscoveredPrinter } from "@/types/ws-messages";

interface PrintersState {
  printers: Record<string, PrinterData>;
  discovered: DiscoveredPrinter[];
  upsertPrinter: (printer: PrinterData) => void;
  removePrinter: (id: string) => void;
  addDiscovered: (printer: DiscoveredPrinter) => void;
  clearDiscovered: () => void;
}

export const usePrintersStore = create<PrintersState>((set) => ({
  printers: {},
  discovered: [],

  upsertPrinter: (printer) =>
    set((state) => ({
      printers: { ...state.printers, [printer.id]: printer },
    })),

  removePrinter: (id) =>
    set((state) => {
      const next = { ...state.printers };
      delete next[id];
      return { printers: next };
    }),

  addDiscovered: (printer) =>
    set((state) => ({
      discovered: state.discovered.some((p) => p.ip === printer.ip)
        ? state.discovered
        : [...state.discovered, printer],
    })),

  clearDiscovered: () => set({ discovered: [] }),
}));

export function usePrinter(id: string | null): PrinterData | undefined {
  return usePrintersStore((s) => (id ? s.printers[id] : undefined));
}

export function usePrinterList(): PrinterData[] {
  return usePrintersStore(useShallow((s) => Object.values(s.printers)));
}
