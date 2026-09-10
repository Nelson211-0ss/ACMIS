import type { ReactNode } from "react"

import { cn } from "@acmis/ui/lib/utils"

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
        <p className="text-muted-foreground mt-1.5 max-w-md text-sm leading-relaxed">
          {reason}
        </p>
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
          Your account does not have access to {what}. If you believe it should,
          ask {contact ?? "your system administrator"} to review your roles.
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
      {rule ? (
        <p className="text-muted-foreground mt-1 font-mono text-xs">Rule: {rule}</p>
      ) : null}
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
