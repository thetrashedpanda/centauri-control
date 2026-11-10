import { useState } from "react";
import type { WidgetDef, WidgetComponentProps } from "@/types/widget";
import { usePrinter } from "@/store/printers";
import { sendAction } from "@/ws/useWebSocket";
import type { FileEntry } from "@/types/ws-messages";

export function FileBrowserWidget({ printerId }: WidgetComponentProps) {
  const printer = usePrinter(printerId);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [currentUrl, setCurrentUrl] = useState("/");
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  if (!printer) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        No printer selected
      </div>
    );
  }

  if (!printer.connected) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm">
        Printer offline
      </div>
    );
  }

  function loadFiles(url: string) {
    setCurrentUrl(url);
    setLoaded(false);
    setFiles([]);
    sendAction({ action: "list_files", printer_id: printer!.id, url });
    // Files will arrive via WS message (file_list) - for now show loading
    setTimeout(() => setLoaded(true), 500);
  }

  function printFile(filename: string) {
    if (!printer) return;
    sendAction({ action: "start_print", printer_id: printer.id, filename });
  }

  return (
    <div className="h-full p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted uppercase tracking-wide">Files</span>
        <button
          onClick={() => loadFiles(currentUrl)}
          className="text-xs text-accent hover:underline"
        >
          {loaded || files.length > 0 ? "Refresh" : "Load"}
        </button>
      </div>
      <div className="text-xs text-muted truncate">{currentUrl}</div>
      <div className="flex-1 overflow-y-auto space-y-1">
        {files.map((f) => (
          <div
            key={f.name}
            onClick={() => f.type === 0 ? loadFiles(`${currentUrl}/${f.name}`) : setSelected(f.name)}
            className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors
              ${selected === f.name ? "bg-accent/20 border border-accent" : "hover:bg-surface2"}`}
          >
            <span className="text-muted">{f.type === 0 ? "📁" : "📄"}</span>
            <span className="text-xs text-fg truncate">{f.name}</span>
          </div>
        ))}
        {loaded && !files.length && (
          <p className="text-xs text-muted text-center py-4">No files found</p>
        )}
      </div>
      {selected && (
        <button
          onClick={() => { printFile(selected); setSelected(null); }}
          className="w-full py-2 bg-accent hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors"
        >
          Print {selected}
        </button>
      )}
    </div>
  );
}

export const FileBrowserWidgetDef: WidgetDef = {
  id: "file-browser",
  name: "File Browser",
  category: "printer",
  allowedSizes: ["medium", "large"],
  defaultSize: "medium",
  requiresPrinterBinding: true,
  component: FileBrowserWidget,
};
