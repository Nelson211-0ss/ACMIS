import type { ReactNode } from "react"

import { cn } from "@acmis/ui/lib/utils"

/**
 * A status pill.
 *
 * Two rules, both from the design system:
 *
 * **Never colour alone.** Every variant carries a text label, and the ones
 * that matter carry a dot with a distinct shape-in-context as well. A reader
 * with colour-vision deficiency, or looking at a printed mark sheet, gets the
 * same information.
 *
 * **Semantic colours mean what they say.** `success` is a fee cleared or a
 * result approved; `warning` is an action still owed; `danger` is a record
 * leaving the system. A dashboard that paints half its badges green because
 * green is pretty teaches staff to ignore the colour.
 */

export type StatusTone =
  | "neutral"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "gold"

const TONES: Record<StatusTone, string> = {
  neutral: "bg-muted text-muted-foreground ring-border",
  info: "bg-info/10 text-info ring-info/25",
  success: "bg-success/10 text-success ring-success/25",
  warning: "bg-warning/15 text-warning-foreground ring-warning/35",
  danger: "bg-destructive/10 text-destructive ring-destructive/25",
  gold: "bg-gold/15 text-gold-foreground ring-gold/35",
}

const DOTS: Record<StatusTone, string> = {
  neutral: "bg-muted-foreground/60",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-destructive",
  gold: "bg-gold",
}

export function StatusBadge({
  tone = "neutral",
  children,
  dot = true,
  className,
}: {
  tone?: StatusTone
  children: ReactNode
  dot?: boolean
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {dot ? (
        <span
          aria-hidden
          className={cn("size-1.5 shrink-0 rounded-full", DOTS[tone])}
        />
      ) : null}
      {children}
    </span>
  )
}

/**
 * The tone for a domain status.
 *
 * Centralised so "submitted" looks the same in the admissions list and on the
 * application page. The mapping is opinionated on purpose: a status that means
 * work is owed is a warning, not a neutral.
 */
export function toneForStatus(status: string | null | undefined): StatusTone {
  if (!status) return "neutral"
  const value = status.toLowerCase()

  if (
    [
      "active", "approved", "released", "published", "settled", "paid",
      "admitted", "enrolled", "senate_approved", "graduated", "cleared",
      "marked", "succeeded", "open", "verified", "balanced",
    ].includes(value)
  ) {
    return "success"
  }
  if (
    [
      "submitted", "under_review", "review", "pending", "awaiting_fee",
      "part_paid", "probation", "moderated", "board_approved",
      "faculty_approved", "in_progress", "scheduled", "requested",
      "second_marking", "reconciliation_required", "unmatched", "on_leave",
      "waitlisted", "returned", "supervisor_approved",
    ].includes(value)
  ) {
    return "warning"
  }
  if (
    [
      "rejected", "failed", "reversed", "suspended", "discontinued",
      "withdrawn", "revoked", "voided", "expired", "denied", "overdue",
      "abandoned", "deceased",
    ].includes(value)
  ) {
    return "danger"
  }
  if (["conferred", "completed", "graduation"].includes(value)) return "gold"
  if (["draft", "closed", "archived", "retired", "superseded"].includes(value)) {
    return "neutral"
  }
  return "info"
}
