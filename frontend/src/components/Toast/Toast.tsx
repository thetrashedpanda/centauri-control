import { useUiStore } from "@/store/ui";
import type { Toast as ToastType } from "@/store/ui";

const VARIANT_STYLES: Record<ToastType["variant"], string> = {
  info:    "bg-surface border-border text-gray-200",
  success: "bg-green-900 border-green-700 text-green-100",
  error:   "bg-red-900 border-red-700 text-red-100",
  warning: "bg-yellow-900 border-yellow-700 text-yellow-100",
};

export function ToastContainer() {
  const toasts = useUiStore((s) => s.toasts);
  const remove = useUiStore((s) => s.removeToast);

  if (!toasts.length) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`border rounded-lg px-4 py-3 text-sm shadow-lg flex items-start gap-3 ${VARIANT_STYLES[t.variant]}`}
        >
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() => remove(t.id)}
            className="opacity-60 hover:opacity-100 text-lg leading-none mt-0.5"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
