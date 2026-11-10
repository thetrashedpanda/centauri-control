import { create } from "zustand";
import type { IntegrationStatus } from "@/types/integration";

interface IntegrationsState {
  byPrinter: Record<string, IntegrationStatus>;
  upsertStatus: (status: IntegrationStatus) => void;
  removePrinter: (printerId: string) => void;
}

export const useIntegrationsStore = create<IntegrationsState>((set) => ({
  byPrinter: {},
  upsertStatus: (status) =>
    set((state) => ({
      byPrinter: { ...state.byPrinter, [status.printer_id]: status },
    })),
  removePrinter: (printerId) =>
    set((state) => {
      const byPrinter = { ...state.byPrinter };
      delete byPrinter[printerId];
      return { byPrinter };
    }),
}));

export function useOpenFilamentSensor(printerId: string | null): IntegrationStatus | undefined {
  return useIntegrationsStore((state) => (
    printerId ? state.byPrinter[printerId] : undefined
  ));
}
