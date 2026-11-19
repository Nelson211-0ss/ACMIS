import { AlertTriangle } from "lucide-react"
import type { ReactNode } from "react"

import { RetryButton } from "@acmis/ui/components/retry-button"
import { cn } from "@acmis/ui/lib/utils"
import type { Unavailable } from "@acmis/ui/lib/unavailable"

/**
 * What a list shows when it has nothing.
 *
 * `reason` matters more than the illustration. "No applications" is
 * ambiguous — is the scheme empty, or is the filter wrong, or does this user
 * not have reach over any faculty? An empty state that says which saves the
 * support call.
 */
export function EmptyState({
  title,
  reason,
  action,
  icon,
  className,
}: {
  title: string
  reason?: ReactNode
  action?: ReactNode
  icon?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "border-border/70 flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-12 text-center",
        className,
      )}
    >
      {icon ? <div className="text-muted-foreground/50 mb-3">{icon}</div> : null}
      <p className="text-base font-semibold">{title}</p>
      {reason ? (
        <p className="text-muted-foreground mt-1.5 max-w-md text-sm leading-relaxed">{reason}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}

/**
 * Shown when the API refuses a read.
 *
 * Says nothing about why, because the API deliberately does not: a reason like
 * "you are not the assigned examiner for CSC1101" confirms facts about a
 * record the reader may not see. What it does give is the route forward — who
 * to ask — which is the only actionable thing anyway.
 */
export function NotPermitted({
  what = "this record",
  contact,
}: {
  what?: string
  contact?: string
}) {
  return (
    <EmptyState
      title="You do not have permission to view this"
      reason={
        <>
          Your account does not have access to {what}. If you believe it should, ask{" "}
          {contact ?? "your system administrator"} to review your roles.
        </>
      }
    />
  )
}

/**
 * Shown when an academic or financial rule refused an action.
 *
 * Distinct from a validation error, and shown differently: the payload was
 * fine, the institution's rules said no, and the fix is an approval or a
 * waiver rather than a corrected field. `waivableBy` names who can authorise
 * the exception, which the API supplies.
 */
export function RuleRefused({
  message,
  rule,
  waivableBy = [],
  details,
}: {
  message: string
  rule?: string
  waivableBy?: string[]
  details?: ReactNode
}) {
  return (
    <div className="border-warning/40 bg-warning/10 rounded-lg border p-4">
      <p className="text-warning-foreground text-sm font-medium">{message}</p>
      {rule ? <p className="text-muted-foreground mt-1 font-mono text-xs">Rule: {rule}</p> : null}
      {waivableBy.length > 0 ? (
        <p className="text-muted-foreground mt-2 text-xs">
          This can be authorised by someone holding{" "}
          {waivableBy.map((code, index) => (
            <span key={code}>
              {index > 0 ? " or " : ""}
              <code className="bg-muted rounded px-1 py-0.5 font-mono">{code}</code>
            </span>
          ))}
          .
        </p>
      ) : null}
      {details ? <div className="mt-3 text-xs">{details}</div> : null}
    </div>
  )
}

/**
 * Shown where a figure, a table or a chart should be, when the call for it
 * did not come back.
 *
 * ## Not the same component as `EmptyState`, on purpose
 *
 * They look similar and they mean opposite things. `EmptyState` is a fact
 * about the institution — there are no unmatched deposits — and it is good
 * news. This is a fact about the system, and it is the absence of news. The
 * two were worth keeping apart in the markup as well as in the copy, because
 * the moment one component renders both, somebody passes the wrong one and a
 * failure starts reading as "all clear".
 *
 * The reason line comes from the API client rather than from the call site, so
 * thirteen apps do not each invent their own wording for a timeout.
 *
 * `requestId` is rendered in the mono face and never translated. It exists to
 * be read down a phone line to somebody looking at a log.
 */
export function DataUnavailable({
  unavailable,
  what = "this",
  className,
}: {
  unavailable: Unavailable
  /** Names the surface: "this chart", "the invoice list". */
  what?: string
  className?: string
}) {
  return (
    <div
      className={cn(
        "border-border/80 flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center",
        className,
      )}
    >
      <AlertTriangle className="text-warning-foreground dark:text-warning size-5" aria-hidden />
      <p className="text-sm font-semibold">
        {what.charAt(0).toUpperCase() + what.slice(1)} could not be loaded
      </p>
      <p className="text-muted-foreground max-w-md text-xs leading-relaxed">
        {unavailable.reason} The figures may be perfectly in order — this screen simply does not
        know.
      </p>
      {unavailable.retryable === false ? null : <RetryButton className="mt-1" />}
      {unavailable.requestId ? (
        <p className="text-muted-foreground/80 font-mono text-[11px]">
          ref {unavailable.requestId}
        </p>
      ) : null}
    </div>
  )
}
