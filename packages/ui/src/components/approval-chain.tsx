import { cn } from "@acmis/ui/lib/utils"

/**
 * The approval chain, drawn as a chain.
 *
 * Used for mark sheets, curriculum versions, waivers and status changes — every
 * workflow in ACMIS that passes through several hands. It exists because the
 * commonest question staff ask about any of them is "where is this, and who is
 * it waiting for", and a status word alone does not answer the second half.
 *
 * Each completed step names who did it and when. That is not decoration: it is
 * the same information the audit trail holds, shown where the decision is being
 * made, which is what stops people opening the audit log to answer routine
 * questions.
 */

export interface ChainStep {
  key: string
  label: string
  /** Who completed it, if anyone has. */
  actor?: string | null
  at?: string | null
  state: "done" | "current" | "pending" | "returned" | "blocked"
  /** Why it is blocked or was returned. */
  note?: string | null
}

const STATE_STYLES: Record<ChainStep["state"], { dot: string; text: string; label: string }> = {
  done: { dot: "bg-success", text: "text-foreground", label: "Completed" },
  current: { dot: "bg-module ring-module/30 ring-4", text: "text-foreground font-medium", label: "In progress" },
  pending: { dot: "bg-muted-foreground/30", text: "text-muted-foreground", label: "Not started" },
  returned: { dot: "bg-warning", text: "text-warning-foreground", label: "Returned" },
  blocked: { dot: "bg-destructive", text: "text-destructive", label: "Blocked" },
}

export function ApprovalChain({
  steps,
  className,
}: {
  steps: ChainStep[]
  className?: string
}) {
  return (
    <ol className={cn("space-y-0", className)}>
      {steps.map((step, index) => {
        const style = STATE_STYLES[step.state]
        const isLast = index === steps.length - 1
        return (
          <li key={step.key} className="relative flex gap-3 pb-5 last:pb-0">
            {!isLast ? (
              <span
                aria-hidden
                className={cn(
                  "absolute top-3 left-[5px] h-full w-[2px]",
                  step.state === "done" ? "bg-success/40" : "bg-border",
                )}
              />
            ) : null}
            <span
              aria-hidden
              className={cn("relative mt-1.5 size-2.5 shrink-0 rounded-full", style.dot)}
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className={cn("text-sm", style.text)}>{step.label}</span>
                {/* The state as a word, not just a colour. */}
                <span className="text-muted-foreground text-[11px]">{style.label}</span>
              </div>
              {step.actor || step.at ? (
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {[step.actor, step.at].filter(Boolean).join(" · ")}
                </p>
              ) : null}
              {step.note ? (
                <p
                  className={cn(
                    "mt-1 text-xs leading-relaxed",
                    step.state === "returned" || step.state === "blocked"
                      ? "text-warning-foreground"
                      : "text-muted-foreground",
                  )}
                >
                  {step.note}
                </p>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** The mark sheet chain, from a sheet's timestamps. */
export function markSheetChain(sheet: {
  status: string
  submitted_at: string | null
  moderated_at: string | null
  board_approved_at: string | null
  faculty_approved_at: string | null
  senate_approved_at: string | null
  published_at: string | null
  return_comments: string | null
}): ChainStep[] {
  const order = [
    "draft",
    "submitted",
    "moderated",
    "board_approved",
    "faculty_approved",
    "senate_approved",
    "published",
  ]
  const position = order.indexOf(sheet.status)

  const step = (
    key: string,
    label: string,
    at: string | null,
    index: number,
  ): ChainStep => ({
    key,
    label,
    at: at ? new Date(at).toLocaleString() : null,
    state:
      sheet.status === "returned" && index === 1
        ? "returned"
        : at
          ? "done"
          : position === index - 1
            ? "current"
            : "pending",
    note: sheet.status === "returned" && index === 1 ? sheet.return_comments : null,
  })

  return [
    { key: "entry", label: "Marks entered", state: "done" as const },
    step("submitted", "Submitted by the examiner", sheet.submitted_at, 1),
    step("moderated", "Moderated", sheet.moderated_at, 2),
    step("board", "Department board of examiners", sheet.board_approved_at, 3),
    step("faculty", "Faculty board", sheet.faculty_approved_at, 4),
    step("senate", "Senate", sheet.senate_approved_at, 5),
    step("published", "Released to students", sheet.published_at, 6),
  ]
}
