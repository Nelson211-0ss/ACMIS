import * as Icons from "lucide-react"
import type { ReactNode } from "react"

import { cn } from "@acmis/ui/lib/utils"

/**
 * A status pill.
 *
 * Two rules, both from the design system:
 *
 * **Never colour alone.** Every variant carries a text label, and the five
 * that mean something carry a glyph whose *silhouette* differs — a tick, a
 * clock, a cross, an `i`, a seal — not six dots in six colours. A reader with
 * a colour-vision deficiency, or holding a printed mark sheet, gets the state
 * from the shape.
 *
 * **Semantic colours mean what they say.** `success` is a fee cleared or a
 * result approved; `warning` is an action still owed; `danger` is a record
 * leaving the system. A dashboard that paints half its badges green because
 * green is pretty teaches staff to ignore the colour.
 */

export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger" | "gold"

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

/**
 * A distinct glyph per tone.
 *
 * The docblock above has always promised "a dot with a distinct shape", and
 * the dot has always been the same circle in six colours — so on a printed
 * mark sheet, or to a reader with a colour-vision deficiency, the mark carried
 * nothing the label did not already say, and six identical dots down a column
 * read as a list of bullets rather than as six different states.
 *
 * These are six genuinely different silhouettes: a tick, a clock, a cross, an
 * `i`, a seal, and — for neutral — no glyph at all, because "nothing is
 * happening here" is best drawn as the absence of a mark. Neutral keeps the
 * plain dot so the badge does not change width when a record moves out of a
 * meaningful state.
 */
const GLYPHS: Partial<Record<StatusTone, Icons.LucideIcon>> = {
  info: Icons.Info,
  success: Icons.CheckCircle2,
  warning: Icons.Clock3,
  danger: Icons.XCircle,
  gold: Icons.Award,
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
  const Glyph = GLYPHS[tone]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        TONES[tone],
        className,
      )}
    >
      {dot ? (
        Glyph ? (
          <Glyph aria-hidden className="size-3 shrink-0" strokeWidth={2.25} />
        ) : (
          <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", DOTS[tone])} />
        )
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
      "active",
      "approved",
      "released",
      "published",
      "settled",
      "paid",
      "admitted",
      "enrolled",
      "senate_approved",
      "graduated",
      "cleared",
      "marked",
      "succeeded",
      "open",
      "verified",
      "balanced",
    ].includes(value)
  ) {
    return "success"
  }
  if (
    [
      "submitted",
      "under_review",
      "review",
      "pending",
      "awaiting_fee",
      "part_paid",
      "probation",
      "moderated",
      "board_approved",
      "faculty_approved",
      "in_progress",
      "scheduled",
      "requested",
      "second_marking",
      "reconciliation_required",
      "unmatched",
      "on_leave",
      "waitlisted",
      "returned",
      "supervisor_approved",
    ].includes(value)
  ) {
    return "warning"
  }
  if (
    [
      "rejected",
      "failed",
      "reversed",
      "suspended",
      "discontinued",
      "withdrawn",
      "revoked",
      "voided",
      "expired",
      "denied",
      "overdue",
      "abandoned",
      "deceased",
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
