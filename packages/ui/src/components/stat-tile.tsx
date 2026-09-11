import Link from "next/link"
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
 *
 * ## The number must never wrap
 *
 * This tile previously sized the value with a fixed `text-2xl sm:text-3xl` and
 * allowed `break-words`. Two tiles up on a 390px phone gives each about 165px
 * of inner width, and "USh 35,730,200" does not fit — so it broke at the
 * thousands separator and the bursar's dashboard read
 *
 *     USh 35,730
 *     ,200
 *
 * which is not a smaller number, it is a different one. A figure split across
 * a line break is worse than a truncated figure, because truncation looks like
 * damage and this looks like data.
 *
 * The fix is a container query, not a media query: the value scales to *the
 * tile's* width, which is what actually constrains it. A tile in a four-up row
 * and the same tile in a two-up row are different widths at the same viewport,
 * so viewport breakpoints cannot express this. `whitespace-nowrap` then makes
 * a wrap impossible rather than merely unlikely, and the clamp floor is set at
 * the point where UGX's longest realistic figure still fits the narrowest tile
 * this system renders.
 *
 * `containerType` is set inline rather than with Tailwind's `@container`
 * because this file is consumed by thirteen apps whose Tailwind scan roots
 * differ, and a utility that fails to generate degrades silently into a
 * wrapped number — the exact bug being fixed.
 */

export interface StatTileProps {
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
  /**
   * A semantic state for the figure itself.
   *
   * Only for tiles where the number *is* the problem — money nobody has
   * matched, sheets past their deadline. `neutral` is the default and most
   * tiles should keep it: a dashboard that paints half its tiles amber teaches
   * staff that amber means nothing.
   */
  tone?: "neutral" | "success" | "warning" | "destructive"
  /**
   * Makes the whole tile a link to the queue it counts.
   *
   * A dashboard figure is almost always a question — "45 invoices past their
   * due date" is followed by "show me them" — and on a phone a 44px-tall text
   * link under the tile is a worse target than the tile itself.
   */
  href?: string
  className?: string
}

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
  tone = "neutral",
  href,
  className,
}: StatTileProps) {
  const hasDelta = delta !== null && delta !== undefined && delta !== 0
  const rising = (delta ?? 0) > 0
  // `deltaIsGood` defaults to "rising is good"; the caller says otherwise for
  // metrics like arrears where rising is the problem.
  const good = deltaIsGood === undefined ? rising : rising === deltaIsGood

  const toneText = {
    neutral: "text-foreground",
    success: "text-success",
    warning: "text-warning-foreground",
    destructive: "text-destructive",
  }[tone]

  const body = (
    <>
      {emphasis ? (
        <span aria-hidden className="bg-module absolute inset-y-0 left-0 w-[3px]" />
      ) : null}

      <div className="flex items-start justify-between gap-2">
        {/* `text-balance` keeps a two-word label from leaving one word alone
            on the second line, which is what made a row of tiles look ragged
            even when their heights matched. */}
        <p className="text-muted-foreground text-balance text-[11px] font-medium uppercase leading-tight tracking-wide">
          {label}
        </p>
        {icon ? (
          <span className="text-muted-foreground/60 shrink-0 [&>svg]:size-4">{icon}</span>
        ) : null}
      </div>

      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span
          className={cn("tabular whitespace-nowrap font-semibold leading-none", toneText)}
          // Scales to the tile, not the viewport. See the note above.
          style={{ fontSize: "clamp(1.125rem, 11cqi, 1.875rem)" }}
        >
          {value}
        </span>
        {unit ? <span className="text-muted-foreground text-xs font-medium">{unit}</span> : null}
        {hasDelta ? (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 text-xs font-medium",
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

      {/* `mt-auto` is what makes a row of tiles line up. Footnotes are one to
          four lines depending on the metric, and without this the short tiles
          floated their text against the tall tiles' third line. The footnote
          now sits on the floor of every tile in the row. */}
      {footnote ? (
        <p className="text-muted-foreground mt-auto pt-2 text-[11px] leading-snug">{footnote}</p>
      ) : null}
    </>
  )

  const shell = cn(
    "bg-card shadow-card relative flex h-full min-h-[5.5rem] flex-col overflow-hidden rounded-lg p-3 sm:p-3.5",
    // `emphasis` already draws the accent edge down the left of the tile. It
    // used to *also* tint the hairline, which on a row of four tiles read as
    // the emphasised one being a different kind of object rather than the
    // important one. The edge says it; a second signal is noise.
    href && "hover:shadow-card-hover transition-shadow",
    className,
  )

  // The container must be established on whichever element is the tile, or
  // `cqi` in the clamp above falls back to the *viewport* and a linked tile
  // sizes its number differently from the plain tile beside it.
  const container = { containerType: "inline-size" } as const

  if (href) {
    return (
      <Link href={href} className={shell} style={container}>
        {body}
        <span className="sr-only">— open</span>
      </Link>
    )
  }

  return (
    <div className={shell} style={container}>
      {body}
    </div>
  )
}

/**
 * A row of tiles. Two-up on a phone, because staff do use these on phones.
 *
 * `auto-rows-fr` is doing real work: a CSS grid sizes rows to their tallest
 * item but stretches nothing by default, so the previous version produced a
 * row of boxes with matching outlines and text floating at different heights.
 * With equal rows and `mt-auto` on the footnote, a row of four tiles reads as
 * one object.
 *
 * `columns` exists because four is right for a registrar's counts and wrong
 * for the two figures a student portal shows.
 */
export function StatRow({
  children,
  columns = 4,
  className,
}: {
  children: ReactNode
  columns?: 2 | 3 | 4
  className?: string
}) {
  return (
    <div
      className={cn(
        "grid auto-rows-fr grid-cols-2 gap-2.5 sm:gap-3",
        columns === 2 && "sm:grid-cols-2",
        columns === 3 && "sm:grid-cols-3",
        columns === 4 && "sm:grid-cols-2 lg:grid-cols-4",
        className,
      )}
    >
      {children}
    </div>
  )
}
