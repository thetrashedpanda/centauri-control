import type { PrinterData } from "@/types/printer";
import { getPrintStatus } from "@/types/printer";

const STATUS_COLORS: Record<string, string> = {
  offline:    "bg-gray-700 text-gray-400",
  idle:       "bg-gray-600 text-gray-200",
  printing:   "bg-green-700 text-green-100",
  pausing:    "bg-yellow-700 text-yellow-100",
  paused:     "bg-yellow-600 text-yellow-100",
  stopping:   "bg-red-700 text-red-100",
  cancelled:  "bg-red-700 text-red-200",
  complete:   "bg-blue-700 text-blue-100",
  "warming up": "bg-orange-700 text-orange-100",
  leveling:   "bg-orange-600 text-orange-100",
  homing:     "bg-orange-600 text-orange-100",
  checking:   "bg-orange-600 text-orange-100",
  recovering: "bg-orange-600 text-orange-100",
  error:      "bg-red-800 text-red-200",
};

interface Props {
  printer: PrinterData;
  className?: string;
}

export function StatusBadge({ printer, className = "" }: Props) {
  const status = getPrintStatus(printer);
  const colors = STATUS_COLORS[status] ?? "bg-gray-700 text-gray-400";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${colors} ${className}`}
    >
      {status}
    </span>
  );
}
