"use client"

import * as Icons from "lucide-react"
import { useActionState, useEffect, useRef } from "react"

import { issueLoan, receiveLoan, type DeskResult } from "./actions"

/**
 * The desk forms.
 *
 * Client components for one reason: a scanner-driven counter must not
 * navigate. The barcode field keeps focus and clears itself after each scan,
 * so an assistant can work through a trolley without touching the mouse — and
 * the outcome of the last scan stays on screen while they do.
 */

function Outcome({ result }: { result: DeskResult | null }) {
  if (!result) return null
  if (result.ok) {
    return (
      <p
        role="status"
        className="rounded-md border border-emerald-600/30 bg-emerald-600/10 px-3 py-2 text-sm text-emerald-800 dark:text-emerald-300"
      >
        {result.ok}
      </p>
    )
  }
  const outstanding = result.details?.outstanding_minor
  const limit = result.details?.limit_minor
  return (
    <p
      role="alert"
      className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm"
    >
      {result.error}
      {typeof outstanding === "number" && typeof limit === "number" ? (
        <span className="mt-1 block text-xs">
          {(outstanding / 100).toLocaleString()} outstanding; borrowing stops at{" "}
          {(limit / 100).toLocaleString()}.
        </span>
      ) : null}
    </p>
  )
}

export function IssueForm() {
  const [result, action, pending] = useActionState(issueLoan, null)
  const barcode = useRef<HTMLInputElement>(null)

  useEffect(() => {
    // After every scan, whatever the outcome: the next book is already in the
    // assistant's hand.
    if (result) barcode.current?.focus()
  }, [result])

  return (
    <form action={action} className="bg-card shadow-card space-y-4 rounded-lg p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Icons.ScanLine className="size-4" aria-hidden />
        Issue
      </h2>

      <Outcome result={result} />

      <div className="space-y-1.5">
        <label htmlFor="issue-barcode" className="text-sm font-medium">
          Book barcode
        </label>
        <input
          ref={barcode}
          id="issue-barcode"
          name="barcode"
          autoComplete="off"
          autoFocus
          required
          key={result?.ok ?? "empty"}
          className="border-input bg-background w-full rounded-md border px-3 py-2 font-mono text-base"
          placeholder="KIT004501"
        />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="issue-member" className="text-sm font-medium">
          Membership number
        </label>
        <input
          id="issue-member"
          name="membership_number"
          autoComplete="off"
          required
          className="border-input bg-background w-full rounded-md border px-3 py-2 font-mono text-base"
          placeholder="LIB/24U0001BSC"
        />
      </div>
      <button
        type="submit"
        disabled={pending}
        className="bg-primary text-primary-foreground h-11 w-full rounded-md text-sm font-medium disabled:opacity-60"
      >
        {pending ? "Issuing…" : "Issue"}
      </button>
      <p className="text-muted-foreground text-xs">
        The loan period comes from the reader&rsquo;s category and the copy&rsquo;s class — a
        postgraduate borrowing normal stock gets longer than an undergraduate borrowing a short
        loan.
      </p>
    </form>
  )
}

export function ReturnForm() {
  const [result, action, pending] = useActionState(receiveLoan, null)
  const barcode = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (result) barcode.current?.focus()
  }, [result])

  return (
    <form action={action} className="bg-card shadow-card space-y-4 rounded-lg p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Icons.Undo2 className="size-4" aria-hidden />
        Return
      </h2>

      <Outcome result={result} />

      <div className="space-y-1.5">
        <label htmlFor="return-barcode" className="text-sm font-medium">
          Book barcode
        </label>
        <input
          ref={barcode}
          id="return-barcode"
          name="barcode"
          autoComplete="off"
          required
          key={result?.ok ?? "empty"}
          className="border-input bg-background w-full rounded-md border px-3 py-2 font-mono text-base"
        />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="condition" className="text-sm font-medium">
          Condition
        </label>
        <select
          id="condition"
          name="condition"
          className="border-input bg-background w-full rounded-md border px-3 py-2 text-base"
        >
          <option value="">Unchanged</option>
          {["good", "fair", "poor", "damaged"].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </div>
      <button
        type="submit"
        disabled={pending}
        className="border-input h-11 w-full rounded-md border text-sm font-medium disabled:opacity-60"
      >
        {pending ? "Taking back…" : "Take back"}
      </button>
      <p className="text-muted-foreground text-xs">
        A damage charge has to be justified against the condition the copy went out in, which is why
        this is recorded rather than remembered.
      </p>
    </form>
  )
}
