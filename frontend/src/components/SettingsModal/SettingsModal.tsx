import { useEffect, useState } from "react";
import { Modal } from "@/components/Modal/Modal";
import { useUiStore } from "@/store/ui";
import { usePrinterList } from "@/store/printers";
import { useIntegrationsStore } from "@/store/integrations";
import { THEME_OPTIONS } from "@/types/theme";
import type {
  IntegrationCatalogResponse,
  IntegrationPrinterConfig,
} from "@/types/integration";
import { api } from "@/api/client";

interface Props {
  onClose: () => void;
}

type Tab = "general" | "integrations";

export function SettingsModal({ onClose }: Props) {
  const [tab, setTab] = useState<Tab>("general");
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  const [spoolmanStatus, setSpoolmanStatus] = useState<"idle" | "checking" | "ok" | "error">("idle");
  const printers = usePrinterList();
  const liveSensorStatus = useIntegrationsStore((s) => s.byPrinter);
  const [sensorConfigs, setSensorConfigs] = useState<Record<string, IntegrationPrinterConfig>>({});
  const [sensorLoadError, setSensorLoadError] = useState("");
  const [sensorActionError, setSensorActionError] = useState<Record<string, string>>({});
  const [savingPrinter, setSavingPrinter] = useState<string | null>(null);
  const [testingPrinter, setTestingPrinter] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});

  useEffect(() => {
    if (tab !== "integrations") return;
    let active = true;
    api.get<IntegrationCatalogResponse>("/api/integrations")
      .then((response) => {
        if (!active) return;
        const sensor = response.integrations.find((item) => item.id === "openfilamentsensor");
        setSensorConfigs(sensor?.printers ?? {});
        setSensorLoadError("");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSensorLoadError(error instanceof Error ? error.message : "Could not load integrations");
      });
    return () => {
      active = false;
    };
  }, [tab]);

  async function testSpoolman() {
    setSpoolmanStatus("checking");
    try {
      await api.get("/api/spoolman/spools");
      setSpoolmanStatus("ok");
    } catch {
      setSpoolmanStatus("error");
    }
  }

  function updateSensorConfig(printerId: string, updates: Partial<IntegrationPrinterConfig>) {
    setSensorConfigs((current) => ({
      ...current,
      [printerId]: {
        enabled: current[printerId]?.enabled ?? false,
        base_url: current[printerId]?.base_url ?? "",
        status: current[printerId]?.status ?? null,
        ...updates,
      },
    }));
    setSensorActionError((current) => ({ ...current, [printerId]: "" }));
    setTestResults((current) => ({ ...current, [printerId]: "" }));
  }

  async function saveSensorConfig(printerId: string) {
    const config = sensorConfigs[printerId] ?? { enabled: false, base_url: "", status: null };
    setSavingPrinter(printerId);
    setSensorActionError((current) => ({ ...current, [printerId]: "" }));
    try {
      const response = await api.put<IntegrationCatalogResponse>(
        "/api/integrations/openfilamentsensor",
        { printer_id: printerId, enabled: config.enabled, base_url: config.base_url },
      );
      const sensor = response.integrations.find((item) => item.id === "openfilamentsensor");
      setSensorConfigs(sensor?.printers ?? {});
    } catch (error: unknown) {
      setSensorActionError((current) => ({
        ...current,
        [printerId]: error instanceof Error ? error.message : "Could not save integration settings",
      }));
    } finally {
      setSavingPrinter(null);
    }
  }

  async function testSensorConnection(printerId: string) {
    const baseUrl = sensorConfigs[printerId]?.base_url ?? "";
    setTestingPrinter(printerId);
    setSensorActionError((current) => ({ ...current, [printerId]: "" }));
    setTestResults((current) => ({ ...current, [printerId]: "" }));
    try {
      const result = await api.post<{ ok: boolean; status: { schema_version: number } }>(
        "/api/integrations/openfilamentsensor/test",
        { base_url: baseUrl },
      );
      setTestResults((current) => ({
        ...current,
        [printerId]: `Connected (status API v${result.status.schema_version})`,
      }));
    } catch (error: unknown) {
      setSensorActionError((current) => ({
        ...current,
        [printerId]: error instanceof Error ? error.message : "Sensor connection test failed",
      }));
    } finally {
      setTestingPrinter(null);
    }
  }

  return (
    <Modal title="Settings" onClose={onClose} wide>
      <div className="flex gap-1 border-b border-border mb-5 -mt-1">
        {(["general", "integrations"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm capitalize border-b-2 -mb-px transition-colors ${
              tab === t
                ? "border-accent text-fg"
                : "border-transparent text-muted hover:text-fg"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "general" && (
        <div className="space-y-5">
          <section>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Theme</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {THEME_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  onClick={() => setTheme(opt.id)}
                  className={`text-left p-3 rounded-lg border transition-colors ${
                    theme === opt.id
                      ? "border-accent bg-surface2"
                      : "border-border bg-surface2/50 hover:border-muted"
                  }`}
                >
                  <div className="flex items-center gap-1.5 mb-2">
                    <span
                      className="w-3 h-3 rounded-full border border-border"
                      style={{ backgroundColor: opt.swatch.bg }}
                    />
                    <span
                      className="w-3 h-3 rounded-full border border-border"
                      style={{ backgroundColor: opt.swatch.surface }}
                    />
                    <span
                      className="w-3 h-3 rounded-full border border-border"
                      style={{ backgroundColor: opt.swatch.accent }}
                    />
                  </div>
                  <p className="text-sm text-fg font-medium">{opt.name}</p>
                  <p className="text-xs text-muted mt-0.5">{opt.description}</p>
                </button>
              ))}
            </div>
          </section>
        </div>
      )}

      {tab === "integrations" && (
        <div className="space-y-5">
          <section>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">Spoolman · Filament inventory</h3>
            <div className="flex items-center justify-between bg-surface2 border border-border rounded-lg px-3 py-3">
              <div>
                <p className="text-sm text-fg font-medium">Spoolman connection</p>
                <p className="text-xs text-muted mt-0.5">
                  {spoolmanStatus === "ok" && "Connected"}
                  {spoolmanStatus === "error" && "Spoolman not reachable"}
                  {spoolmanStatus === "checking" && "Checking Spoolman…"}
                  {spoolmanStatus === "idle" && "Connection status unknown"}
                </p>
              </div>
              <button
                onClick={() => void testSpoolman()}
                disabled={spoolmanStatus === "checking"}
                className="text-xs bg-surface2 hover:bg-border border border-border text-fg px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50 shrink-0"
              >
                Test Spoolman
              </button>
            </div>
          </section>
          <section>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">OpenFilament Sensor</h3>
            <p className="text-xs text-muted mb-3">
              Read-only runout and jam telemetry. Enter each sensor's address below and use its Test button. OpenFilament Sensor retains ownership of jam detection and printer pausing.
            </p>
            {sensorLoadError && (
              <p role="alert" className="text-xs text-red-400 mb-3">{sensorLoadError}</p>
            )}
            {printers.length === 0 ? (
              <p className="text-xs text-muted">Add a printer before configuring a sensor integration.</p>
            ) : (
              <div className="space-y-3">
                {printers.map((printer) => {
                  const config = sensorConfigs[printer.id] ?? {
                    enabled: false,
                    base_url: "",
                    status: null,
                  };
                  const status = liveSensorStatus[printer.id] ?? config.status;
                  return (
                    <div key={printer.id} className="bg-surface2 border border-border rounded-lg p-3 space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm text-fg font-medium truncate">{printer.name}</p>
                          <p className="text-xs text-muted truncate">{printer.ip}</p>
                        </div>
                        <label className="flex items-center gap-2 text-xs text-fg shrink-0">
                          <input
                            type="checkbox"
                            checked={config.enabled}
                            onChange={(event) => updateSensorConfig(printer.id, { enabled: event.target.checked })}
                          />
                          Enabled
                        </label>
                      </div>
                      <div>
                        <label className="block text-xs text-muted mb-1" htmlFor={`ofs-url-${printer.id}`}>
                          Sensor address
                        </label>
                        <input
                          id={`ofs-url-${printer.id}`}
                          type="url"
                          value={config.base_url}
                          onChange={(event) => updateSensorConfig(printer.id, { base_url: event.target.value })}
                          placeholder="http://192.168.1.50"
                          className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-fg focus:outline-none focus:border-accent"
                        />
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <p className={`text-xs ${
                          status?.connected ? "text-green-400" : status?.enabled ? "text-yellow-400" : "text-muted"
                        }`}>
                          {testResults[printer.id] ||
                            (status?.connected ? "Connected" :
                              status?.enabled ? status.error || "Waiting for sensor" : "Not configured")}
                        </p>
                        <div className="flex gap-2 shrink-0">
                          <button
                            onClick={() => void testSensorConnection(printer.id)}
                            disabled={testingPrinter === printer.id || !config.base_url.trim()}
                            className="text-xs bg-surface2 hover:bg-border border border-border text-fg px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                          >
                            {testingPrinter === printer.id ? "Testing…" : "Test"}
                          </button>
                          <button
                            onClick={() => void saveSensorConfig(printer.id)}
                            disabled={savingPrinter === printer.id}
                            className="text-xs bg-accent hover:bg-orange-600 text-white px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                          >
                            {savingPrinter === printer.id ? "Saving…" : "Save"}
                          </button>
                        </div>
                      </div>
                      {sensorActionError[printer.id] && (
                        <p role="alert" className="text-xs text-red-400">{sensorActionError[printer.id]}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      )}
    </Modal>
  );
}
