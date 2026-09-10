import type { ReactNode } from "react"

import { cn } from "@acmis/ui/lib/utils"

/**
 * A single figure with its label.
 *
 * The form heuristic says: when the data's job is one headline number, a chart
 * is the wrong answer and a tile is the right one. Most of what a registrar
 * needs on a dashboard is exactly this — 12,431 enrolled, 84 mark sheets
 * outstanding — and drawing a bar chart of one value is decoration.
 *
 * `delta` is a change, not a trend line. It carries a direction word as well
 * as an arrow and a colour, because "up 12%" is good for enrolment and bad for
 * outstanding fees, and the tile has to be told which.
 */
export function StatTile({
  label,
  value,
  unit,
  delta,
  deltaLabel,
  deltaIsGood,
  footnote,
  icon,
  emphasis = false,
  className,
}: {
  label: string
  value: ReactNode
  unit?: string
  /** Signed percentage or absolute change. */
  delta?: number | null
  deltaLabel?: string
  /**
   * Whether an increase is good. Explicit because it differs per metric and
   * getting it wrong paints a problem green.
   */
  deltaIsGood?: boolean
  footnote?: ReactNode
  icon?: ReactNode
  /** Draws the module accent edge. One tile per dashboard at most. */
  emphasis?: boolean
  className?: string
}) {
  const hasDelta = delta !== null && delta !== undefined && delta !== 0
  const rising = (delta ?? 0) > 0
  // `deltaIsGood` defaults to "rising is good"; the caller says otherwise for
  // metrics like arrears where rising is the problem.
  const good = deltaIsGood === undefined ? rising : rising === deltaIsGood

  return (
    <div
      className={cn(
        "bg-card relative overflow-hidden rounded-lg border p-4",
        emphasis && "border-module/40",
        className,
      )}
    >
      {emphasis ? (
        <span aria-hidden className="bg-module absolute inset-y-0 left-0 w-[3px]" />
      ) : null}
      <div className="flex items-start justify-between gap-3">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          {label}
        </p>
        {icon ? <span className="text-muted-foreground/70 shrink-0">{icon}</span> : null}
      </div>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {/* Steps down on a narrow tile: a seven-figure amount at 3xl
            overflows a half-width tile on a 360px screen. */}
        <span className="tabular min-w-0 text-2xl leading-none font-semibold break-words sm:text-3xl">
          {value}
        </span>
        {unit ? (
          <span className="text-muted-foreground text-sm font-medium">{unit}</span>
        ) : null}
        {hasDelta ? (
          <span
            className={cn(
              "inline-flex items-center gap-1 text-xs font-medium",
              good ? "text-success" : "text-destructive",
            )}
          >
            {/* An arrow *and* a word: the colour is a reinforcement, never the
                only signal. */}
            <span aria-hidden>{rising ? "▲" : "▼"}</span>
            {Math.abs(delta ?? 0)}
            {deltaLabel ? <span className="sr-only">{deltaLabel}</span> : null}
          </span>
        ) : null}
      </div>
      {footnote ? (
        <p className="text-muted-foreground mt-2 text-xs leading-relaxed">{footnote}</p>
      ) : null}
    </div>
  )
}

/** A row of tiles. Two-up on a phone, because staff do use these on phones. */
export function StatRow({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 lg:grid-cols-4", className)}>
      {children}
    </div>
  )
}
