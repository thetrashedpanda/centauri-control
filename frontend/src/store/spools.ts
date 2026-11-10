import { create } from "zustand";
import type { SpoolData } from "@/types/spool";

interface SpoolsState {
  spools: SpoolData[];
  setSpools: (spools: SpoolData[]) => void;
  getSpoolForPrinter: (printerId: string) => SpoolData | undefined;
}

export const useSpoolsStore = create<SpoolsState>((set, get) => ({
  spools: [],

  setSpools: (spools) => set({ spools }),

  getSpoolForPrinter: (printerId) =>
    get().spools.find((s) => s.location === printerId),
}));
