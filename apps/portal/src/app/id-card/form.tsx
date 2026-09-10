"use client"

import { useActionState } from "react"
import { useFormStatus } from "react-dom"

import { type ActionResult, reportLost } from "./actions"

/**
 * The lost-card form.
 *
 * Stolen is a separate checkbox rather than a separate button because it
 * changes what happens next — a stolen card needs a police reference before a
 * replacement is issued — and burying that in a button label loses it.
 */
export function ReportLostForm({ cardId }: { cardId: string }) {
  const [state, formAction] = useActionState<ActionResult | null, FormData>(
    reportLost,
    null,
  )

  return (
    <form action={formAction} className="space-y-3">
      <input type="hidden" name="card_id" value={cardId} />
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          name="stolen"
          className="border-input size-4 rounded border"
        />
        It was stolen, not mislaid
      </label>
      <Submit />
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

function Submit() {
  const { pending } = useFormStatus()
  return (
    <button
      type="submit"
      disabled={pending}
      className="bg-destructive text-destructive-foreground hover:bg-destructive/90 min-h-11 rounded-md px-4 py-2.5 text-sm font-medium disabled:opacity-60"
    >
      {pending ? "Reporting…" : "Report this card lost"}
    </button>
  )
}
