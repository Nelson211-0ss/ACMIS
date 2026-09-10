"use client"

import { useActionState } from "react"
import { useFormStatus } from "react-dom"

import type { ActionResult } from "./actions"

/**
 * A one-button form that reports what the API said.
 *
 * Both of registration's actions are a single irreversible-ish step with a
 * rule behind them, so the shape is the same for each: press, wait, and read
 * either the confirmation or the rule that refused it.
 */
export function ActionForm({
  action,
  label,
  hidden,
  hint,
  destructive = false,
}: {
  action: (previous: ActionResult | null, formData: FormData) => Promise<ActionResult>
  label: string
  hidden: Record<string, string>
  hint?: string
  destructive?: boolean
}) {
  const [state, formAction] = useActionState(action, null)

  return (
    <form action={formAction} className="space-y-2">
      {Object.entries(hidden).map(([name, value]) => (
        <input key={name} type="hidden" name={name} value={value} />
      ))}
      <Submit label={label} destructive={destructive} />
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
      {state?.ok ? (
        <p className="text-success text-sm" role="status">
          {state.ok}
        </p>
      ) : null}
      {state?.error ? (
        <p className="text-destructive text-sm" role="alert">
          {state.error}
        </p>
      ) : null}
    </form>
  )
}

function Submit({ label, destructive }: { label: string; destructive: boolean }) {
  const { pending } = useFormStatus()
  return (
    <button
      type="submit"
      disabled={pending}
      className={
        destructive
          ? "bg-destructive text-destructive-foreground hover:bg-destructive/90 min-h-11 rounded-md px-4 py-2.5 text-sm font-medium disabled:opacity-60"
          : "bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 rounded-md px-4 py-2.5 text-sm font-medium disabled:opacity-60"
      }
    >
      {pending ? "Working…" : label}
    </button>
  )
}
