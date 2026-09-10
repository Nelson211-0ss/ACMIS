import type { ReactNode } from "react"

import { cn } from "@acmis/ui/lib/utils"

/**
 * The heading block at the top of every page.
 *
 * `description` is not decoration. These screens are operated by staff who
 * were trained once, months ago, and the one line explaining what a page does
 * — and what its consequences are — saves a support call. On the pages where
 * an action is irreversible it says so.
 */
export function PageHeader({
  title,
  description,
  breadcrumbs,
  actions,
  className,
}: {
  title: string
  description?: ReactNode
  breadcrumbs?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div className={cn("border-border/70 border-b pb-5", className)}>
      {breadcrumbs ? <div className="mb-2">{breadcrumbs}</div> : null}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1.5">
          <h1 className="text-2xl font-semibold tracking-tight text-balance">
            {title}
          </h1>
          {description ? (
            <p className="text-muted-foreground max-w-2xl text-sm leading-relaxed">
              {description}
            </p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
    </div>
  )
}
