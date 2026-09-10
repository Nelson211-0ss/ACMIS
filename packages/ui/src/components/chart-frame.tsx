import type { ReactNode } from "react"

import { cn } from "@acmis/ui/lib/utils"

// Deliberately **not** a client component. Nothing here needs the browser —
// every chart is markup over numbers the server already has — and marking it
// `"use client"` had a consequence that was invisible until a page tried it:
// a `formatValue` function cannot cross a server/client boundary, so every
// dashboard passing one threw "Functions cannot be passed directly to Client
// Components" at request time. Rendering on the server also means the charts
// arrive in the HTML, which is the point for a registry clerk on a slow link.

/**
 * The frame every chart in ACMIS sits in: title, subtitle, legend, and a table
 * view behind a toggle.
 *
 * The table is not optional. Three of the six accessibility requirements are
 * satisfied by it alone — a reader who cannot distinguish two series, a
 * screen-reader user, and anyone printing a report all need the numbers — and
 * a chart component that makes the table an afterthought means it never gets
 * built.
 *
 * The legend is always present for two or more series, so identity is never
 * carried by colour alone.
 */

export interface Series {
  key: string
  label: string
  /** A `--chart-N` slot. Assigned in order, never cycled. */
  slot: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8
}

export function ChartFrame({
  title,
  subtitle,
  series,
  children,
  table,
  footnote,
  className,
}: {
  title: string
  subtitle?: string
  /** Omit for a single series — the title names it, so a legend box is noise. */
  series?: Series[]
  children: ReactNode
  /** The same data as rows. Rendered in a `<details>`, always available. */
  table?: ReactNode
  footnote?: ReactNode
  className?: string
}) {
  const showLegend = (series?.length ?? 0) >= 2

  return (
    <figure className={cn("bg-card rounded-lg border p-4", className)}>
      <figcaption className="mb-3 space-y-1">
        <h3 className="text-base leading-tight font-semibold">{title}</h3>
        {subtitle ? (
          <p className="text-muted-foreground text-xs leading-relaxed">{subtitle}</p>
        ) : null}
      </figcaption>

      {showLegend ? (
        <ul className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {series!.map((entry) => (
            <li key={entry.key} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className="size-2.5 shrink-0 rounded-[2px]"
                style={{ background: `var(--chart-${entry.slot})` }}
              />
              {/* Text stays in ink, never the series colour — the swatch
                  beside it carries the identity. */}
              <span className="text-muted-foreground text-xs">{entry.label}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {/* Wide content scrolls inside the figure, never the page. */}
      <div className="min-w-0 overflow-x-auto">{children}</div>

      {footnote ? (
        <p className="text-muted-foreground mt-3 text-xs leading-relaxed">{footnote}</p>
      ) : null}

      {table ? (
        <details className="mt-3">
          <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-xs font-medium">
            View as a table
          </summary>
          <div className="mt-2 overflow-x-auto">{table}</div>
        </details>
      ) : null}
    </figure>
  )
}

/**
 * A horizontal bar chart in plain HTML.
 *
 * No charting library for this shape: a labelled magnitude comparison is a
 * flex row and a width percentage, and pulling in a canvas renderer for it
 * costs 40kB and loses the text selection, the print rendering and the
 * keyboard focus that come free here.
 *
 * Follows the mark spec: rounded data-end anchored to the baseline, a 2px
 * surface gap between adjacent fills, direct labels on the value rather than a
 * separate axis.
 */
export function BarRows({
  rows,
  slot = 1,
  formatValue = (v) => String(v),
  max,
}: {
  rows: Array<{ label: string; value: number; hint?: string }>
  slot?: Series["slot"]
  formatValue?: (value: number) => string
  max?: number
}) {
  const ceiling = max ?? Math.max(1, ...rows.map((r) => r.value))

  return (
    <div className="space-y-2">
      {rows.map((row) => {
        const share = Math.max(0, Math.min(1, row.value / ceiling))
        return (
          // A 10rem label column leaves 6rem for the bar on a 360px screen,
          // so below `sm` the label sits above the bar instead of beside it.
          <div
            key={row.label}
            className="group grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-0.5 sm:grid-cols-[8rem_1fr_auto] lg:grid-cols-[10rem_1fr_auto]"
          >
            <span
              className="text-muted-foreground col-span-2 truncate text-xs sm:col-span-1"
              title={row.label}
            >
              {row.label}
            </span>
            <span className="bg-muted/60 relative h-5 overflow-hidden rounded-sm">
              <span
                className="absolute inset-y-0 left-0 rounded-r-[4px] transition-[width] duration-300"
                style={{
                  width: `${share * 100}%`,
                  background: `var(--chart-${slot})`,
                }}
                title={row.hint ?? `${row.label}: ${formatValue(row.value)}`}
              />
            </span>
            <span className="tabular text-xs font-medium">{formatValue(row.value)}</span>
          </div>
        )
      })}
    </div>
  )
}

/**
 * A stacked proportion bar — a grade distribution, a fee split.
 *
 * A 2px surface gap between segments, per the mark spec: without it two
 * adjacent fills of similar lightness read as one, which is exactly the case a
 * grade distribution produces.
 */
export function StackedBar({
  segments,
  formatValue = (v) => String(v),
}: {
  segments: Array<{ label: string; value: number; slot: Series["slot"] }>
  formatValue?: (value: number) => string
}) {
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1

  return (
    <div className="space-y-2">
      <div className="bg-muted/50 flex h-6 overflow-hidden rounded-sm">
        {segments.map((segment, index) => {
          const share = segment.value / total
          if (share <= 0) return null
          return (
            <span
              key={segment.label}
              className="h-full"
              style={{
                width: `${share * 100}%`,
                background: `var(--chart-${segment.slot})`,
                // The gap is the surface showing through, not a border — a
                // border would darken at the join in dark mode.
                marginLeft: index === 0 ? 0 : 2,
              }}
              title={`${segment.label}: ${formatValue(segment.value)}`}
            />
          )
        })}
      </div>
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {segments
          .filter((s) => s.value > 0)
          .map((segment) => (
            <li key={segment.label} className="flex items-center gap-1.5 text-xs">
              <span
                aria-hidden
                className="size-2.5 rounded-[2px]"
                style={{ background: `var(--chart-${segment.slot})` }}
              />
              <span className="text-muted-foreground">{segment.label}</span>
              <span className="tabular font-medium">{formatValue(segment.value)}</span>
            </li>
          ))}
      </ul>
    </div>
  )
}

/**
 * A meter for a single bounded proportion — fees paid, credits earned,
 * marks entered.
 *
 * `threshold` draws the line that matters: the fee percentage required before
 * registration, say. A meter without it tells a student they have paid 55% and
 * not that they need 60%.
 */
export function Meter({
  value,
  max,
  label,
  threshold,
  thresholdLabel,
  tone = "module",
  formatValue = (v) => String(v),
}: {
  value: number
  max: number
  label?: string
  threshold?: number
  thresholdLabel?: string
  tone?: "module" | "success" | "warning" | "destructive"
  formatValue?: (value: number) => string
}) {
  const share = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0
  const thresholdShare =
    threshold !== undefined && max > 0 ? Math.max(0, Math.min(1, threshold / max)) : null
  const fill = {
    module: "var(--module)",
    success: "var(--success)",
    warning: "var(--warning)",
    destructive: "var(--destructive)",
  }[tone]

  return (
    <div className="space-y-1.5">
      {label ? (
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground text-xs">{label}</span>
          <span className="tabular text-xs font-medium">
            {formatValue(value)} <span className="text-muted-foreground">of {formatValue(max)}</span>
          </span>
        </div>
      ) : null}
      <div
        className="bg-muted relative h-2.5 overflow-hidden rounded-full"
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
      >
        <span
          className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-300"
          style={{ width: `${share * 100}%`, background: fill }}
        />
        {thresholdShare !== null ? (
          <span
            aria-hidden
            className="bg-foreground/70 absolute inset-y-[-2px] w-[2px]"
            style={{ left: `${thresholdShare * 100}%` }}
            title={thresholdLabel}
          />
        ) : null}
      </div>
      {thresholdLabel ? (
        <p className="text-muted-foreground text-[11px]">{thresholdLabel}</p>
      ) : null}
    </div>
  )
}
