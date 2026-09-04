import { cn } from "@/lib/cn";

/**
 * Progress meter. Solid gold fill on a sunken track — gold because progress
 * through an application is an achievement, and because it is the one place
 * the flag's colour earns a large area.
 */
export function Progress({
  value,
  label,
  className,
}: {
  /** 0–100. */
  value: number;
  label: string;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className={cn("min-w-0", className)}>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="text-[12.5px] font-medium text-ink-soft">{label}</span>
        <span className="nums text-[12.5px] font-semibold text-ink">{clamped}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="h-1.5 w-full overflow-hidden rounded-full bg-sunken"
      >
        <div
          className="h-full rounded-full bg-gold-500 transition-[width] duration-200"
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}

/**
 * A GPA on the 4.0 scale, drawn as a segmented bar. Segments rather than a
 * continuous fill so the reader can count where they sit without a gradient.
 */
export function GpaMeter({ value }: { value: number }) {
  const segments = 8; // half-point steps
  const filled = Math.round((value / 4) * segments);
  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-[3px]" aria-hidden>
        {Array.from({ length: segments }, (_, i) => (
          <span
            key={i}
            className={cn(
              "h-4 w-1.5 rounded-sm",
              i < filled
                ? value >= 3.0
                  ? "bg-green-600"
                  : value >= 2.0
                    ? "bg-gold-500"
                    : "bg-red-600"
                : "bg-line-strong",
            )}
          />
        ))}
      </div>
      <span className="nums text-sm font-semibold text-ink">{value.toFixed(2)}</span>
      <span className="text-[12px] text-muted">/ 4.00</span>
    </div>
  );
}
