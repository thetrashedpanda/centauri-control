import { create } from "zustand";
import type { WidgetInstance, LayoutItem, SavedLayout } from "@/types/widget";
import { api } from "@/api/client";

interface LayoutState {
  activeLayoutId: string;
  layouts: SavedLayout[];
  instances: WidgetInstance[];
  gridLayout: LayoutItem[];

  setLayouts: (data: { activeLayoutId: string; layouts: SavedLayout[] }) => void;
  setActiveLayout: (id: string) => void;
  setGridLayout: (layout: LayoutItem[]) => void;
  addWidget: (instance: WidgetInstance, gridItem: LayoutItem) => void;
  removeWidget: (instanceId: string) => void;
  updateWidgetConfig: (instanceId: string, config: Record<string, unknown>) => void;
  saveLayout: () => Promise<void>;
}

export const useLayoutStore = create<LayoutState>((set, get) => ({
  activeLayoutId: "default",
  layouts: [],
  instances: [],
  gridLayout: [],

  setLayouts: ({ activeLayoutId, layouts }) => {
    const active = layouts.find((l) => l.id === activeLayoutId);
    set({
      activeLayoutId,
      layouts,
      instances: active?.instances ?? [],
      gridLayout: active?.gridLayout ?? [],
    });
  },

  setActiveLayout: (id) => {
    const layout = get().layouts.find((l) => l.id === id);
    if (!layout) return;
    set({
      activeLayoutId: id,
      instances: layout.instances,
      gridLayout: layout.gridLayout,
    });
  },

  setGridLayout: (gridLayout) => set({ gridLayout }),

  addWidget: (instance, gridItem) =>
    set((s) => ({
      instances: [...s.instances, instance],
      gridLayout: [...s.gridLayout, gridItem],
    })),

  removeWidget: (instanceId) =>
    set((s) => ({
      instances: s.instances.filter((i) => i.instanceId !== instanceId),
      gridLayout: s.gridLayout.filter((g) => g.i !== instanceId),
    })),

  updateWidgetConfig: (instanceId, config) =>
    set((s) => ({
      instances: s.instances.map((i) =>
        i.instanceId === instanceId ? { ...i, config } : i
      ),
    })),

  saveLayout: async () => {
    const { activeLayoutId, layouts, instances, gridLayout } = get();
    const updatedLayout: SavedLayout = {
      id: activeLayoutId,
      name: layouts.find((l) => l.id === activeLayoutId)?.name ?? "Default",
      instances,
      gridLayout,
      updatedAt: new Date().toISOString(),
    };
    const updatedLayouts = layouts.map((l) =>
      l.id === activeLayoutId ? updatedLayout : l
    );
    if (!updatedLayouts.find((l) => l.id === activeLayoutId)) {
      updatedLayouts.push(updatedLayout);
    }
    await api.put("/api/layout", {
      version: 1,
      activeLayoutId,
      layouts: updatedLayouts,
    });
    set({ layouts: updatedLayouts });
  },
}));
