import type { ReactNode } from "react"

import { cn } from "@acmis/ui/lib/utils"

/**
 * The table every list view uses.
 *
 * Deliberately a plain table, not a virtualised grid. These lists are
 * server-paginated with keyset cursors, so the client never holds more than a
 * page — and a real `<table>` keeps text selection, ctrl-F, screen-reader row
 * and column announcements, and a sane print rendering, all of which registry
 * staff use constantly and all of which a div-based grid throws away.
 *
 * `tabular` on the wrapper puts figures in tabular numerals, so a column of
 * fee balances lines up at the decimal point.
 *
 * ## Why the phone layout is no longer opt-in
 *
 * `mobileCard` used to be a per-table choice, on the reasoning that most of
 * these are reference lists nobody reads on a phone. Thirteen apps later,
 * fourteen of seventeen tables had supplied one and three had not — and the
 * three included the student list, which is the most-opened list in the
 * system. Those three fell through to horizontal scroll, where the standing
 * column landed just past the right edge and every badge read "Probatio…".
 *
 * An opt-in that everyone opts into is a default with extra steps, and the
 * ones that miss out are missed by accident rather than by decision. So a card
 * layout is now always rendered below `sm`: `mobileCard` still overrides it
 * when a table wants a bespoke one, and `columns` generates a sensible one
 * when it does not. Horizontal scroll remains for `sm` and up, where a tablet
 * genuinely has the width for aligned columns.
 */

export interface Column<T> {
  key: string
  header: ReactNode
  /** Right-align numbers; the header aligns with them. */
  numeric?: boolean
  /**
   * Hidden below `sm` in the table layout, and demoted in the generated card.
   *
   * Use for columns a phone can do without.
   */
  secondary?: boolean
  width?: string
  render: (row: T) => ReactNode
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty,
  caption,
  onRowHref,
  dense = false,
  mobileCard,
  className,
}: {
  columns: Array<Column<T>>
  rows: T[]
  rowKey: (row: T) => string
  empty?: ReactNode
  /** Read by screen readers before the table. Say what the rows are. */
  caption?: string
  /** Makes the whole row a link without nesting anchors in every cell. */
  onRowHref?: (row: T) => string
  dense?: boolean
  /**
   * A bespoke card rendering for narrow screens.
   *
   * Optional. Supply it when a table has an obvious headline — an invoice
   * number and its amount — and the generated label/value stack would bury
   * it. Otherwise the generated card is used, so no table is left scrolling
   * sideways on a phone.
   */
  mobileCard?: (row: T) => ReactNode
  className?: string
}) {
  if (rows.length === 0 && empty) {
    return <>{empty}</>
  }

  // The first non-secondary column is the row's identity — the student number,
  // the invoice reference — and becomes the card's heading. The rest become
  // label/value pairs beneath it.
  const [head, ...rest] = columns.filter((c) => !c.secondary)
  const detail = [...rest, ...columns.filter((c) => c.secondary)]

  const renderCard =
    mobileCard ??
    ((row: T) => (
      <>
        {head ? <p className="text-sm font-semibold leading-tight">{head.render(row)}</p> : null}
        {detail.length ? (
          <dl className="mt-2 space-y-1">
            {detail.map((column) => (
              <div key={column.key} className="flex items-baseline justify-between gap-3">
                <dt className="text-muted-foreground shrink-0 text-[11px] uppercase tracking-wide">
                  {column.header}
                </dt>
                {/* `text-right` and `min-w-0`: a long programme name has to
                    wrap inside its own cell rather than push the label off
                    the card. */}
                <dd className="min-w-0 text-right text-xs font-medium">{column.render(row)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </>
    ))

  return (
    <>
      <ul className="space-y-2 sm:hidden">
        {rows.map((row) => {
          const href = onRowHref?.(row)
          const card = (
            <div
              className={cn(
                "bg-card tabular shadow-card rounded-lg p-3",
                href && "active:bg-muted/50 transition-colors",
              )}
            >
              {renderCard(row)}
            </div>
          )
          return (
            <li key={rowKey(row)}>
              {href ? (
                // The whole card is the target. A phone has no hover, so the
                // affordance has to be the size of the thing.
                <a href={href} className="block rounded-lg focus-visible:outline-none">
                  {card}
                </a>
              ) : (
                card
              )}
            </li>
          )
        })}
      </ul>

      <div className="hidden sm:block">
        <Table
          columns={columns}
          rows={rows}
          rowKey={rowKey}
          caption={caption}
          onRowHref={onRowHref}
          dense={dense}
          className={className}
        />
      </div>
    </>
  )
}

function Table<T>({
  columns,
  rows,
  rowKey,
  caption,
  onRowHref,
  dense,
  className,
}: {
  columns: Array<Column<T>>
  rows: T[]
  rowKey: (row: T) => string
  caption?: string
  onRowHref?: (row: T) => string
  dense?: boolean
  className?: string
}) {
  return (
    /*
     * ## Why this box has a height
     *
     * The header row below is `position: sticky` so that the column a clerk is
     * reading down stays named — on a 400-row fee ledger that is the
     * difference between a table and a wall of numbers. It had never once
     * stuck.
     *
     * The reason is this wrapper. It carried `overflow-x: auto` for wide
     * tables, and CSS says an `overflow-y: visible` beside a non-visible
     * `overflow-x` computes to `auto` — so the wrapper silently became a
     * scroll container on *both* axes, and a sticky element's offsets are
     * resolved against its nearest scrollport, not the viewport. The wrapper
     * never scrolled vertically (it is exactly as tall as its table), so
     * `top-14` had nothing to resolve against and the header simply scrolled
     * away with the page. Measured mid-scroll on the 60-row student list, the
     * header row sat 277px *above* the top of the viewport.
     *
     * Two ways out: stop the wrapper being a vertical scrollport, which cannot
     * be done while it scrolls horizontally, or let it be one and give it a
     * height so there is something to stick to. This is the second. Sticky is
     * then relative to this box, which is why the offset below is `top-0` and
     * not the header's height.
     *
     * The cap only engages on a long table — a short one never reaches it and
     * shows no scrollbar, so nothing changes for the majority of these
     * screens. And this branch is `hidden sm:block` (a phone gets the card
     * list above), so no phone ever meets a nested scroll region.
     */
    <div
      className={cn(
        "tabular max-h-[min(70dvh,46rem)] w-full overflow-auto overscroll-x-contain",
        className,
      )}
    >
      <table className="w-full border-collapse text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          {/* `bg-card` rather than transparent, or the rows show through as
              they pass under it. */}
          <tr className="border-border/70 bg-card sticky top-0 z-10 border-b">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                className={cn(
                  "text-muted-foreground px-3 py-2 text-left text-xs font-medium uppercase tracking-wide",
                  column.numeric && "text-right",
                  column.secondary && "hidden md:table-cell",
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const href = onRowHref?.(row)
            return (
              <tr
                key={rowKey(row)}
                className={cn(
                  "border-border/50 border-b last:border-0",
                  href && "hover:bg-muted/50 focus-within:bg-muted/50",
                )}
              >
                {columns.map((column, index) => (
                  <td
                    key={column.key}
                    className={cn(
                      dense ? "px-3 py-1.5" : "px-3 py-2.5",
                      "whitespace-nowrap",
                      column.numeric && "text-right",
                      column.secondary && "hidden md:table-cell",
                    )}
                  >
                    {href && index === 0 ? (
                      // One link per row, on the first cell, stretched across
                      // it — a link in every cell makes tabbing through a
                      // 50-row table take 300 keystrokes.
                      <a
                        href={href}
                        className="hover:text-module focus-visible:text-module font-medium"
                      >
                        {column.render(row)}
                      </a>
                    ) : (
                      column.render(row)
                    )}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Keyset pagination controls.
 *
 * Next and previous only, no page numbers — the API returns cursors, not
 * offsets, and inventing page numbers over a cursor-paginated set would be a
 * lie the moment a row is inserted. See `PageMeta` for why cursors.
 *
 * The controls are 44px tall on a phone. They were 26px, which is under every
 * published minimum and sits at the bottom of a list that is several thousand
 * pixels long on a phone — so the one control a user reaches after all that
 * scrolling was the hardest one to hit.
 */
export function Pagination({
  meta,
  onNext,
  onPrevious,
  className,
}: {
  meta: {
    has_more: boolean
    next_cursor: string | null
    previous_cursor: string | null
    total: number | null
    limit: number
  }
  onNext?: string
  onPrevious?: string
  className?: string
}) {
  const step = (label: string, href: string | undefined, enabled: boolean) => (
    <a
      href={href ?? "#"}
      aria-disabled={!enabled}
      className={cn(
        "inline-flex min-h-11 flex-1 items-center justify-center rounded-md border px-4 text-xs font-medium sm:min-h-9 sm:flex-none",
        enabled ? "hover:bg-muted" : "text-muted-foreground pointer-events-none opacity-50",
      )}
    >
      {label}
    </a>
  )

  return (
    <nav
      className={cn(
        "flex flex-col gap-2 pt-3 sm:flex-row sm:items-center sm:justify-between sm:gap-3",
        className,
      )}
      aria-label="Pagination"
    >
      <p className="text-muted-foreground text-xs">
        {meta.total !== null
          ? `${meta.total.toLocaleString()} record${meta.total === 1 ? "" : "s"}`
          : `Showing up to ${meta.limit}`}
      </p>
      <div className="flex items-center gap-2">
        {step("Previous", onPrevious, Boolean(meta.previous_cursor))}
        {step("Next", onNext, meta.has_more)}
      </div>
    </nav>
  )
}
