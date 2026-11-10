export type ThemeId = "dark" | "light" | "elegoo" | "prusa" | "nebula";

export interface ThemeOption {
  id: ThemeId;
  name: string;
  description: string;
  swatch: { bg: string; surface: string; accent: string };
}

export const THEME_OPTIONS: ThemeOption[] = [
  {
    id: "dark",
    name: "Dark",
    description: "The default CentauriControl theme.",
    swatch: { bg: "#0d0e12", surface: "#16181f", accent: "#ff6b2b" },
  },
  {
    id: "light",
    name: "Light",
    description: "A clean light theme for bright rooms.",
    swatch: { bg: "#f3f4f6", surface: "#ffffff", accent: "#ff6b2b" },
  },
  {
    id: "elegoo",
    name: "Elegoo Centauri",
    description: "Matches the Centauri Carbon's onboard display.",
    swatch: { bg: "#26282c", surface: "#2f3136", accent: "#1fa952" },
  },
  {
    id: "prusa",
    name: "Prusa Orange",
    description: "Inspired by PrusaSlicer's dark interface.",
    swatch: { bg: "#232327", surface: "#313136", accent: "#ff8000" },
  },
  {
    id: "nebula",
    name: "Nebula",
    description: "A deep-space violet theme, fittingly Centauri.",
    swatch: { bg: "#0a0b1a", surface: "#131629", accent: "#9d5cff" },
  },
];
