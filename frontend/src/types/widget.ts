import type React from "react";

export type WidgetSizeName = "compact" | "small" | "medium" | "large" | "wide" | "full";

export interface WidgetSizeDef {
  readonly name: WidgetSizeName;
  readonly w: number;   // grid columns out of 12
  readonly h: number;   // grid rows (1 row ≈ 120px)
}

// Grid is 24 cols × 60px rows (half-step resolution: was 12 cols × 120px).
// All w/h values are doubled vs. the old 12-col grid to maintain the same
// visual footprint while allowing half-step resizing in both axes.
export const WIDGET_SIZES: Record<WidgetSizeName, WidgetSizeDef> = {
  compact: { name: "compact", w: 6,  h: 4 },
  small:   { name: "small",   w: 6,  h: 6 },
  medium:  { name: "medium",  w: 12, h: 6 },
  large:   { name: "large",   w: 12, h: 8 },
  wide:    { name: "wide",    w: 18, h: 6 },
  full:    { name: "full",    w: 24, h: 8 },
} as const;

export interface WidgetComponentProps<TConfig = Record<string, unknown>> {
  instanceId: string;
  printerId: string | null;
  config: TConfig;
  size: WidgetSizeName;
  isEditMode: boolean;
}

export interface WidgetDef<TConfig = Record<string, unknown>> {
  readonly id: string;
  readonly name: string;
  readonly category: "printer" | "spools" | "history" | "system";
  readonly allowedSizes: readonly WidgetSizeName[];
  readonly defaultSize: WidgetSizeName;
  readonly requiresPrinterBinding: boolean;
  readonly configSchema?: Record<string, unknown>;   // JSON Schema draft-7
  readonly component: React.ComponentType<WidgetComponentProps<TConfig>>;
  readonly icon?: React.ComponentType<{ className?: string }>;
}

export interface WidgetInstance<TConfig = Record<string, unknown>> {
  instanceId: string;   // UUID v4
  widgetId: string;
  printerId: string | null;
  config: TConfig;
  size: WidgetSizeName;
}

export interface LayoutItem {
  i: string;   // matches WidgetInstance.instanceId
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface SavedLayout {
  id: string;
  name: string;
  instances: WidgetInstance[];
  gridLayout: LayoutItem[];   // parallel array keyed by instanceId
  updatedAt: string;          // ISO 8601
}

export interface LayoutsFile {
  version: 1;
  activeLayoutId: string;
  layouts: SavedLayout[];
}
