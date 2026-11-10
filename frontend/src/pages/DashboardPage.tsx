import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dashboard } from "@/dashboard/Dashboard";
import { useWebSocket } from "@/ws/useWebSocket";
import { useUiStore } from "@/store/ui";
import { useLayoutStore } from "@/store/layout";
import { usePrinterList } from "@/store/printers";
import { ToastContainer } from "@/components/Toast/Toast";
import { Modal } from "@/components/Modal/Modal";
import { ManagePrintersModal } from "@/components/ManagePrintersModal/ManagePrintersModal";
import { SettingsModal } from "@/components/SettingsModal/SettingsModal";
import { WIDGET_REGISTRY } from "@/widgets/registry";
import { WIDGET_SIZES } from "@/types/widget";
import type { WidgetInstance, LayoutItem } from "@/types/widget";
import { api } from "@/api/client";

function genId() {
  return Math.random().toString(36).slice(2, 10);
}

export function DashboardPage() {
  useWebSocket();
  const navigate = useNavigate();
  const isEditMode = useUiStore((s) => s.isEditMode);
  const toggleEditMode = useUiStore((s) => s.toggleEditMode);
  const setLayouts = useLayoutStore((s) => s.setLayouts);
  const addWidget = useLayoutStore((s) => s.addWidget);
  const printers = usePrinterList();
  const [showAddWidget, setShowAddWidget] = useState(false);
  const [showManagePrinters, setShowManagePrinters] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [addPrinterId, setAddPrinterId] = useState<string | null>(null);

  // Load layout on mount
  useEffect(() => {
    api
      .get<{ version: number; activeLayoutId: string; layouts: import("@/types/widget").SavedLayout[] }>("/api/layout")
      .then((data) => setLayouts({ activeLayoutId: data.activeLayoutId, layouts: data.layouts }))
      .catch(() => {});
  }, [setLayouts]);

  async function handleLogout() {
    await api.post("/api/auth/logout", {}).catch(() => {});
    navigate("/login");
  }

  function handleAddWidget(widgetId: string) {
    const def = WIDGET_REGISTRY[widgetId];
    if (!def) return;
    const instanceId = genId();
    const sizeDef = WIDGET_SIZES[def.defaultSize];
    const instance: WidgetInstance = {
      instanceId,
      widgetId,
      printerId: def.requiresPrinterBinding ? (addPrinterId ?? printers[0]?.id ?? null) : null,
      config: {},
      size: def.defaultSize,
    };
    const gridItem: LayoutItem = { i: instanceId, x: 0, y: Infinity, w: sizeDef.w, h: sizeDef.h };
    addWidget(instance, gridItem);
    setShowAddWidget(false);
  }

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      {/* Header */}
      <header className="border-b border-border bg-surface px-6 py-3 flex items-center justify-between shrink-0">
        <h1 className="text-fg font-bold text-lg">CentauriControl v2</h1>
        <div className="flex items-center gap-3">
          {isEditMode && (
            <button
              onClick={() => setShowAddWidget(true)}
              className="text-sm bg-accent hover:bg-orange-600 text-white px-3 py-1.5 rounded-lg transition-colors"
            >
              + Add Widget
            </button>
          )}
          <button
            onClick={() => setShowManagePrinters(true)}
            className="text-sm bg-surface2 hover:bg-border text-fg px-3 py-1.5 rounded-lg transition-colors"
          >
            Printers
          </button>
          <button
            onClick={toggleEditMode}
            className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${
              isEditMode
                ? "bg-green-700 hover:bg-green-600 text-white"
                : "bg-surface2 hover:bg-border text-fg"
            }`}
          >
            {isEditMode ? "Done" : "Edit"}
          </button>
          <button
            onClick={() => setShowSettings(true)}
            className="text-sm bg-surface2 hover:bg-border text-fg px-3 py-1.5 rounded-lg transition-colors"
          >
            Settings
          </button>
          <button
            onClick={handleLogout}
            className="text-sm text-muted hover:text-fg transition-colors"
          >
            Logout
          </button>
        </div>
      </header>

      {/* Grid */}
      <main className="flex-1 p-6 overflow-auto">
        {isEditMode && (
          <p className="text-xs text-muted mb-3">
            Drag widget headers to move them; drag the highlighted bottom-right corner to resize.
          </p>
        )}
        <Dashboard />
      </main>

      {/* Toasts */}
      <ToastContainer />

      {showManagePrinters && (
        <ManagePrintersModal onClose={() => setShowManagePrinters(false)} />
      )}

      {showSettings && (
        <SettingsModal onClose={() => setShowSettings(false)} />
      )}

      {/* Add Widget modal */}
      {showAddWidget && (
        <Modal title="Add Widget" onClose={() => setShowAddWidget(false)}>
          <div className="space-y-4">
            {printers.length > 0 && (
              <div>
                <label className="block text-xs text-muted mb-1.5">Bind to printer</label>
                <select
                  value={addPrinterId ?? ""}
                  onChange={(e) => setAddPrinterId(e.target.value || null)}
                  className="w-full bg-surface2 border border-border rounded-lg px-3 py-2 text-sm text-fg focus:outline-none focus:border-accent"
                >
                  <option value="">None</option>
                  {printers.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}
            <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto">
              {Object.values(WIDGET_REGISTRY).map((def) => (
                <button
                  key={def.id}
                  onClick={() => handleAddWidget(def.id)}
                  className="text-left p-3 bg-surface2 hover:bg-border border border-border rounded-lg transition-colors"
                >
                  <p className="text-sm text-fg font-medium">{def.name}</p>
                  <p className="text-xs text-muted capitalize">{def.category}</p>
                </button>
              ))}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
