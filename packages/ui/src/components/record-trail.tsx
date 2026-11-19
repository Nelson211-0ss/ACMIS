import { ChevronRight } from "lucide-react"
import Link from "next/link"

import { cn } from "@acmis/ui/lib/utils"

/**
 * The trail above a record's title.
 *
 * ## Why this exists when eight pages already had one
 *
 * They each had their own. Eight `<nav aria-label="Breadcrumb">` blocks,
 * hand-written, with the same two links and a `/` between them — and with
 * the attribute order, the hover treatment and the wording all drifting
 * apart, because nothing was holding them together. The package's own
 * `breadcrumb.tsx` was imported by none of them.
 *
 * That is not a wayfinding bug, it is a system bug, and it shows up the first
 * time somebody wants to change how a trail behaves: today that means eight
 * edits and a near-certainty that one is missed.
 *
 * ## The details it now gets right everywhere
 *
 * A **chevron, not a slash**. A slash is a character in the content — call
 * numbers and programme codes contain them — so a reader has to work out
 * which slashes are structure. A chevron cannot be mistaken for data.
 *
 * The last crumb **truncates rather than wraps**. It is the longest (a book
 * title, a person's full name) and the least useful to read in full, because
 * the page title underneath says the same thing at four times the size.
 *
 * It is **not underlined by default**. Eight pages underlined every crumb,
 * which on a record page put three underlined strings directly above a title
 * — the trail read as the loudest thing on the screen, and it is the
 * quietest. Underline arrives on hover, where it answers "can I click this".
 */

export interface TrailCrumb {
  label: string
  href: string
}

export function RecordTrail({
  items,
  current,
  className,
}: {
  /** The ancestors, nearest last. The module is already in the rail. */
  items: TrailCrumb[]
  /**
   * This record, as a reader would name it: a student number, an invoice
   * reference, a title. Rendered as text, never a link — a link to the page
   * you are on is a dead control.
   */
  current?: string
  className?: string
}) {
  return (
    <nav aria-label="Breadcrumb" className={cn("text-muted-foreground min-w-0 text-xs", className)}>
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-0.5">
        {items.map((item) => (
          <li key={item.href} className="flex shrink-0 items-center gap-1">
            <Link href={item.href} className="hover:text-foreground hover:underline">
              {item.label}
            </Link>
            <ChevronRight className="size-3 shrink-0 opacity-60" aria-hidden />
          </li>
        ))}
        {current ? (
          <li className="min-w-0">
            {/* `aria-current="page"` and not a link: this is where you are. */}
            <span aria-current="page" className="text-foreground block truncate font-medium">
              {current}
            </span>
          </li>
        ) : null}
      </ol>
    </nav>
  )
}
