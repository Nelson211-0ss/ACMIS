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
 */

export interface Column<T> {
  key: string
  header: ReactNode
  /** Right-align numbers; the header aligns with them. */
  numeric?: boolean
  /** Hidden below `sm`. Use for columns a phone can do without. */
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
   * A card rendering for narrow screens.
   *
   * Horizontal scroll is the right default — it keeps the columns aligned and
   * comparable — but for the two or three tables staff genuinely read on a
   * phone, a stacked card is easier than swiping. Supplied per table rather
   * than guessed, because most of these are reference lists that nobody reads
   * on a phone and a card view for them would just be taller.
   */
  mobileCard?: (row: T) => ReactNode
  className?: string
}) {
  if (rows.length === 0 && empty) {
    return <>{empty}</>
  }

  if (mobileCard) {
    return (
      <>
        <ul className="space-y-2 sm:hidden">
          {rows.map((row) => {
            const href = onRowHref?.(row)
            const card = (
              <div className="bg-card rounded-lg border p-3">{mobileCard(row)}</div>
            )
            return (
              <li key={rowKey(row)}>
                {href ? (
                  <a href={href} className="block focus-visible:outline-none">
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

  return (
    <Table
      columns={columns}
      rows={rows}
      rowKey={rowKey}
      caption={caption}
      onRowHref={onRowHref}
      dense={dense}
      className={className}
    />
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
    <div className={cn("tabular w-full overflow-x-auto", className)}>
      <table className="w-full border-collapse text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr className="border-border/70 border-b">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                className={cn(
                  "text-muted-foreground px-3 py-2 text-left text-xs font-medium tracking-wide uppercase",
                  column.numeric && "text-right",
                  column.secondary && "hidden sm:table-cell",
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
                      column.secondary && "hidden sm:table-cell",
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
 */
export function Pagination({
  meta,
  onNext,
  onPrevious,
  className,
}: {
  meta: { has_more: boolean; next_cursor: string | null; previous_cursor: string | null; total: number | null; limit: number }
  onNext?: string
  onPrevious?: string
  className?: string
}) {
  return (
    <nav
      className={cn("flex items-center justify-between gap-3 pt-3", className)}
      aria-label="Pagination"
    >
      <p className="text-muted-foreground text-xs">
        {meta.total !== null
          ? `${meta.total.toLocaleString()} record${meta.total === 1 ? "" : "s"}`
          : `Showing up to ${meta.limit}`}
      </p>
      <div className="flex items-center gap-2">
        <a
          href={onPrevious ?? "#"}
          aria-disabled={!meta.previous_cursor}
          className={cn(
            "rounded-md border px-3 py-1.5 text-xs font-medium",
            meta.previous_cursor
              ? "hover:bg-muted"
              : "text-muted-foreground pointer-events-none opacity-50",
          )}
        >
          Previous
        </a>
        <a
          href={onNext ?? "#"}
          aria-disabled={!meta.has_more}
          className={cn(
            "rounded-md border px-3 py-1.5 text-xs font-medium",
            meta.has_more
              ? "hover:bg-muted"
              : "text-muted-foreground pointer-events-none opacity-50",
          )}
        >
          Next
        </a>
      </div>
    </nav>
  )
}
