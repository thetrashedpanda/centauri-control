import { create } from "zustand";
import type { ThemeId } from "@/types/theme";

interface UiState {
  isEditMode: boolean;
  theme: ThemeId;
  toasts: Toast[];
  toggleEditMode: () => void;
  setTheme: (theme: ThemeId) => void;
  addToast: (message: string, variant?: Toast["variant"]) => void;
  removeToast: (id: string) => void;
}

export interface Toast {
  id: string;
  message: string;
  variant: "info" | "success" | "error" | "warning";
}

let _toastCounter = 0;

const THEME_STORAGE_KEY = "centauricontrol.theme";
const DEFAULT_THEME: ThemeId = "dark";
const VALID_THEMES: ThemeId[] = ["dark", "light", "elegoo", "prusa", "nebula"];

function loadStoredTheme(): ThemeId {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return VALID_THEMES.includes(stored as ThemeId) ? (stored as ThemeId) : DEFAULT_THEME;
}

function applyTheme(theme: ThemeId) {
  document.documentElement.setAttribute("data-theme", theme);
}

const initialTheme = loadStoredTheme();
applyTheme(initialTheme);

export const useUiStore = create<UiState>((set) => ({
  isEditMode: false,
  theme: initialTheme,
  toasts: [],

  toggleEditMode: () => set((s) => ({ isEditMode: !s.isEditMode })),

  setTheme: (theme) => {
    applyTheme(theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    set({ theme });
  },

  addToast: (message, variant = "info") => {
    const id = `toast-${++_toastCounter}`;
    set((s) => ({ toasts: [...s.toasts, { id, message, variant }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 5000);
  },

  removeToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
