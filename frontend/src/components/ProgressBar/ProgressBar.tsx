interface Props {
  value: number;   // 0–100
  className?: string;
  colorClass?: string;
}

export function ProgressBar({
  value,
  className = "",
  colorClass = "bg-accent",
}: Props) {
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div className={`w-full bg-surface2 rounded-full overflow-hidden h-2 ${className}`}>
      <div
        className={`h-full rounded-full transition-all duration-500 ${colorClass}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
