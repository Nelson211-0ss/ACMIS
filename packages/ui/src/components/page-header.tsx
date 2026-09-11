import type { ReactNode } from "react"

import { cn } from "@acmis/ui/lib/utils"

/**
 * The heading block at the top of every page.
 *
 * `description` is not decoration. These screens are operated by staff who
 * were trained once, months ago, and the one line explaining what a page does
 * — and what its consequences are — saves a support call. On the pages where
 * an action is irreversible it says so.
 *
 * ## The icon
 *
 * `icon` is the same glyph the sidebar uses for this destination, repeated at
 * the top of the page it leads to. That repetition is the whole point: staff
 * navigate by shape long before they read the label, and a page whose icon
 * matches the rail item they just clicked confirms they arrived where they
 * meant to. A *different* icon here would be worse than none.
 *
 * It is `aria-hidden` in effect — the title beside it already says what the
 * page is, so a screen reader announcing the glyph would be reading the same
 * thing twice. Callers pass a bare lucide element and this sizes it.
 */
export function PageHeader({
  title,
  description,
  breadcrumbs,
  actions,
  icon,
  eyebrow,
  className,
}: {
  title: string
  description?: ReactNode
  breadcrumbs?: ReactNode
  actions?: ReactNode
  /** The sidebar's glyph for this destination. See the note above. */
  icon?: ReactNode
  /** A short label above the title — the record's type, or the cycle it sits in. */
  eyebrow?: ReactNode
  className?: string
}) {
  return (
    <div className={cn("border-border/70 border-b pb-5", className)}>
      {breadcrumbs ? <div className="mb-2">{breadcrumbs}</div> : null}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {icon ? (
            <span
              aria-hidden
              className={cn(
                "bg-module/10 text-module grid size-9 shrink-0 place-items-center rounded-lg [&>svg]:size-[18px]",
                // Nudged down so the glyph's optical centre lines up with the
                // title's x-height rather than with its box.
                "mt-0.5",
              )}
            >
              {icon}
            </span>
          ) : null}
          <div className="min-w-0 space-y-1.5">
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            <h1 className="font-display text-balance text-2xl font-extrabold tracking-tight">
              {title}
            </h1>
            {description ? (
              <p className="text-muted-foreground max-w-2xl text-sm leading-relaxed">
                {description}
              </p>
            ) : null}
          </div>
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
    </div>
  )
}
