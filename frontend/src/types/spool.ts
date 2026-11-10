export interface VendorData {
  id: number;
  name: string;
}

export interface FilamentData {
  id: number;
  name: string;
  material: string;
  color_hex: string;
  density: number;
  diameter: number;
  vendor: VendorData;
}

export interface SpoolData {
  id: number;
  initial_weight: number;
  remaining_weight: number;
  location: string | null;
  filament: FilamentData;
}

// ─── Helper functions ─────────────────────────────────────────────────────────

/** Returns the printer ID (location) this spool is assigned to, or null if unassigned. */
export function spoolAssignedTo(spool: SpoolData): string | null {
  return spool.location || null;
}

/** Returns remaining weight as a percentage of initial weight (0-100). */
export function spoolRemainingPercent(spool: SpoolData): number {
  const total = Math.round(spool.initial_weight ?? 1000);
  if (total <= 0) return 0;
  const remaining = Math.round(spool.remaining_weight ?? 0);
  return Math.round((remaining / total) * 100);
}

/** Returns true if the spool has less than 1% of its initial weight remaining. */
export function isSpoolEmpty(spool: SpoolData): boolean {
  return spoolRemainingPercent(spool) < 1;
}

/** Returns true if the spool has less than 10% of its initial weight remaining. */
export function isSpoolLow(spool: SpoolData): boolean {
  return spoolRemainingPercent(spool) < 10;
}
