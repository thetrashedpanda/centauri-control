import { useState, useEffect } from "react";
import { Modal } from "@/components/Modal/Modal";
import { usePrintersStore } from "@/store/printers";
import { useShallow } from "zustand/shallow";
import { sendAction } from "@/ws/useWebSocket";
import type { PrinterType } from "@/types/printer";

interface Props {
  onClose: () => void;
}

export function ManagePrintersModal({ onClose }: Props) {
  const printers = usePrintersStore(useShallow((s) => Object.values(s.printers)));
  const discovered = usePrintersStore(useShallow((s) => s.discovered));
  const clearDiscovered = usePrintersStore((s) => s.clearDiscovered);

  const [discovering, setDiscovering] = useState(false);
  const [ip, setIp] = useState("");
  const [name, setName] = useState("");
  const [printerType, setPrinterType] = useState<PrinterType>("cc1");
  const [accessCode, setAccessCode] = useState("");

  useEffect(() => {
    clearDiscovered();
    return () => clearDiscovered();
  }, [clearDiscovered]);

  function handleDiscover() {
    clearDiscovered();
    setDiscovering(true);
    sendAction({ action: "discover" });
    setTimeout(() => setDiscovering(false), 5000);
  }

  function handleAdd(overrides?: { ip: string; name: string; printer_type: PrinterType; access_code?: string }) {
    const payload = overrides ?? {
      ip: ip.trim(),
      name: name.trim() || undefined,
      printer_type: printerType,
      access_code: accessCode.trim() || undefined,
    };
    if (!payload.ip) return;
    sendAction({ action: "add_printer", ...payload });
    setIp("");
    setName("");
    setAccessCode("");
  }

  function handleRemove(printer_id: string) {
    sendAction({ action: "remove_printer", printer_id });
  }

  return (
    <Modal title="Manage Printers" onClose={onClose} wide>
      <div className="space-y-5">

        {/* Existing printers */}
        <section>
          <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">Saved Printers</h3>
          {printers.length === 0 ? (
            <p className="text-xs text-muted italic">No printers added yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {printers.map((p) => (
                <li key={p.id} className="flex items-center justify-between bg-surface2 border border-border rounded-lg px-3 py-2">
                  <div>
                    <span className="text-sm text-fg font-medium">{p.name}</span>
                    <span className="text-xs text-muted ml-2">{p.ip} · {p.printer_type.toUpperCase()}</span>
                  </div>
                  <button
                    onClick={() => handleRemove(p.id)}
                    className="text-xs text-red-400 hover:text-red-300 transition-colors ml-4"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Discovery */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider">Network Discovery</h3>
            <button
              onClick={handleDiscover}
              disabled={discovering}
              className="text-xs bg-surface2 hover:bg-border border border-border text-fg px-3 py-1 rounded-lg transition-colors disabled:opacity-50"
            >
              {discovering ? "Scanning…" : "Discover"}
            </button>
          </div>
          {discovered.length === 0 ? (
            <p className="text-xs text-muted italic">
              {discovering ? "Scanning network (up to 5 seconds)…" : "Click Discover to scan for printers."}
            </p>
          ) : (
            <ul className="space-y-1.5">
              {discovered.map((p) => (
                <li key={p.ip} className="flex items-center justify-between bg-surface2 border border-border rounded-lg px-3 py-2">
                  <div>
                    <span className="text-sm text-fg font-medium">{p.name}</span>
                    <span className="text-xs text-muted ml-2">{p.ip} · {p.printer_type.toUpperCase()}</span>
                  </div>
                  <button
                    onClick={() => handleAdd({ ip: p.ip, name: p.name, printer_type: p.printer_type })}
                    className="text-xs bg-accent hover:bg-orange-600 text-white px-3 py-1 rounded-lg transition-colors ml-4"
                  >
                    Add
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Manual add */}
        <section>
          <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">Add Manually</h3>
          <div className="grid grid-cols-2 gap-2">
            <input
              value={ip}
              onChange={(e) => setIp(e.target.value)}
              placeholder="IP address *"
              className="col-span-2 bg-surface2 border border-border rounded-lg px-3 py-2 text-sm text-fg placeholder:text-muted focus:outline-none focus:border-accent"
            />
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Name (optional)"
              className="bg-surface2 border border-border rounded-lg px-3 py-2 text-sm text-fg placeholder:text-muted focus:outline-none focus:border-accent"
            />
            <select
              value={printerType}
              onChange={(e) => setPrinterType(e.target.value as PrinterType)}
              className="bg-surface2 border border-border rounded-lg px-3 py-2 text-sm text-fg focus:outline-none focus:border-accent"
            >
              <option value="cc1">CC1 (SDCP/WS)</option>
              <option value="cc2">CC2 (MQTT)</option>
            </select>
            <input
              value={accessCode}
              onChange={(e) => setAccessCode(e.target.value)}
              placeholder="Access code (CC1 only)"
              className="col-span-2 bg-surface2 border border-border rounded-lg px-3 py-2 text-sm text-fg placeholder:text-muted focus:outline-none focus:border-accent"
            />
          </div>
          <button
            onClick={() => handleAdd()}
            disabled={!ip.trim()}
            className="mt-2 w-full bg-accent hover:bg-orange-600 disabled:opacity-40 text-white text-sm py-2 rounded-lg transition-colors"
          >
            Add Printer
          </button>
        </section>

      </div>
    </Modal>
  );
}
