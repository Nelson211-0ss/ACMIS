"use client"

import { useActionState } from "react"
import { useFormStatus } from "react-dom"

import type { ActionResult } from "./actions"

/**
 * A single-button form over one library action.
 *
 * Inline rather than in a dialog: renewing a book and joining a queue are
 * both reversible and low-stakes, and a confirmation step on a reversible
 * action teaches people to click through confirmations.
 */
export function LibraryButton({
  action,
  label,
  hidden,
  subtle = false,
}: {
  action: (previous: ActionResult | null, formData: FormData) => Promise<ActionResult>
  label: string
  hidden: Record<string, string>
  subtle?: boolean
}) {
  const [state, formAction] = useActionState(action, null)

  return (
    <form action={formAction} className="inline-flex flex-col items-start gap-1">
      {Object.entries(hidden).map(([name, value]) => (
        <input key={name} type="hidden" name={name} value={value} />
      ))}
      <Submit label={label} subtle={subtle} />
      {state?.ok ? (
        <span className="text-success text-xs" role="status">
          {state.ok}
        </span>
      ) : null}
      {state?.error ? (
        <span className="text-destructive text-xs" role="alert">
          {state.error}
        </span>
      ) : null}
    </form>
  )
}

function Submit({ label, subtle }: { label: string; subtle: boolean }) {
  const { pending } = useFormStatus()
  return (
    <button
      type="submit"
      disabled={pending}
      className={
        subtle
          ? "text-muted-foreground hover:text-foreground min-h-9 text-xs underline disabled:opacity-60"
          : "border-input hover:bg-accent min-h-9 rounded-md border px-3 py-1.5 text-xs font-medium disabled:opacity-60"
      }
    >
      {pending ? "Working…" : label}
    </button>
  )
}
