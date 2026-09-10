"use client"

import { useActionState } from "react"
import { useFormStatus } from "react-dom"

import type { CandidateRow, ElectionPositionRow } from "@acmis/api-client"

import { type CheckResult, type VoteResult, castBallot, checkReceipt } from "./actions"

/**
 * The ballot paper.
 *
 * Radios where one may be chosen and checkboxes where several may be, because
 * the control has to make the rule obvious before the voter presses anything.
 * Candidates appear in the order drawn by lot, which is why they are not
 * sorted here: the top of a ballot paper is worth votes, and alphabetical
 * ordering hands that to whoever is called Abaho.
 */
export function BallotPaper({
  electionId,
  positions,
  candidates,
}: {
  electionId: string
  positions: ElectionPositionRow[]
  candidates: CandidateRow[]
}) {
  const [state, formAction] = useActionState<VoteResult | null, FormData>(
    castBallot,
    null,
  )

  if (state?.receipts) {
    return <Receipts receipts={state.receipts} castAt={state.castAt} positions={positions} />
  }

  return (
    <form action={formAction} className="space-y-6">
      <input type="hidden" name="election_id" value={electionId} />
      <input
        type="hidden"
        name="position_ids"
        value={positions.map((position) => position.id).join(",")}
      />

      {positions.map((position) => {
        const standing = candidates
          .filter((candidate) => candidate.position_id === position.id)
          .sort((a, b) => a.ballot_order - b.ballot_order)
        const multiple = position.max_choices > 1

        return (
          <fieldset key={position.id} className="bg-card rounded-lg border p-4">
            <legend className="px-1 text-sm font-semibold">
              {position.is_referendum ? position.question : position.title}
            </legend>
            <p className="text-muted-foreground text-xs">
              {position.description ? `${position.description} · ` : ""}
              {multiple
                ? `Choose up to ${position.max_choices} of ${standing.length}`
                : "Choose one"}
              {position.seats > 1 ? ` · ${position.seats} seats` : ""}
              {position.reserved_for ? ` · reserved for ${position.reserved_for}` : ""}
            </p>

            {standing.length === 0 ? (
              <p className="text-muted-foreground mt-3 text-sm">
                No candidate was validly nominated for this position. It will be
                filled by by-election.
              </p>
            ) : (
              <ul className="mt-3 space-y-2">
                {standing.map((candidate) => (
                  <li key={candidate.id}>
                    <label className="hover:bg-accent/50 flex min-h-11 cursor-pointer items-start gap-3 rounded-md border p-3">
                      <input
                        type={multiple ? "checkbox" : "radio"}
                        name={`position:${position.id}`}
                        value={candidate.id}
                        className="mt-0.5 size-4 shrink-0"
                      />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium">
                          {candidate.ballot_order}. {candidate.ballot_name}
                        </span>
                        {candidate.slogan ? (
                          <span className="text-muted-foreground block text-xs italic">
                            “{candidate.slogan}”
                          </span>
                        ) : null}
                        {candidate.manifesto ? (
                          <span className="text-muted-foreground mt-1 block text-xs">
                            {candidate.manifesto}
                          </span>
                        ) : null}
                      </span>
                    </label>
                  </li>
                ))}
                <li>
                  <label className="hover:bg-accent/50 flex min-h-11 cursor-pointer items-center gap-3 rounded-md border border-dashed p-3">
                    <input
                      type={multiple ? "checkbox" : "radio"}
                      name={`position:${position.id}`}
                      value="abstain"
                      className="size-4 shrink-0"
                      defaultChecked={!multiple}
                    />
                    <span className="text-muted-foreground text-sm">
                      Abstain on this position
                    </span>
                  </label>
                </li>
              </ul>
            )}
          </fieldset>
        )
      })}

      <div className="border-warning/40 bg-warning/10 space-y-3 rounded-lg border p-4">
        <p className="text-sm">
          Pressing this casts your ballot. It cannot be changed or withdrawn,
          and the receipts appear on the next screen <strong>once</strong> —
          nothing on the server holds a copy against your name, so write them
          down or screenshot them before you leave the page.
        </p>
        <Submit />
      </div>

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
      className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 rounded-md px-5 py-2.5 text-sm font-semibold disabled:opacity-60"
    >
      {pending ? "Casting…" : "Cast my ballot"}
    </button>
  )
}

function Receipts({
  receipts,
  castAt,
  positions,
}: {
  receipts: Record<string, string>
  castAt?: string
  positions: ElectionPositionRow[]
}) {
  const title = (id: string) =>
    positions.find((position) => position.id === id)?.title ?? "Position"

  return (
    <div className="border-success/40 bg-success/10 space-y-4 rounded-lg border p-4">
      <div>
        <h2 className="text-success text-sm font-semibold">Your ballot is cast</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          {castAt ? `Recorded ${new Date(castAt).toLocaleString("en-GB")}. ` : ""}
          These are your receipts. They are the only proof your ballot is in the
          count; they do not reveal what you chose, and they exist nowhere else
          against your name.
        </p>
      </div>
      <ul className="space-y-2">
        {Object.entries(receipts).map(([positionId, token]) => (
          <li key={positionId} className="bg-card rounded-md border p-3">
            <p className="text-muted-foreground text-xs">{title(positionId)}</p>
            <p className="mt-1 font-mono text-sm break-all select-all">{token}</p>
          </li>
        ))}
      </ul>
      <p className="text-muted-foreground text-xs">
        Copy them now. Reloading this page will not show them again.
      </p>
    </div>
  )
}

/** Check a receipt against the count. */
export function ReceiptChecker() {
  const [state, formAction] = useActionState<CheckResult | null, FormData>(
    checkReceipt,
    null,
  )

  return (
    <form action={formAction} className="space-y-2">
      <label className="block text-sm">
        <span className="font-medium">Receipt token</span>
        <input
          type="text"
          name="token"
          autoComplete="off"
          spellCheck={false}
          className="border-input bg-background mt-1 min-h-11 w-full rounded-md border px-3 py-2 font-mono text-base sm:text-sm"
          placeholder="Paste the token you were given"
        />
      </label>
      <CheckSubmit />
      {state?.message ? (
        <p className="text-success text-sm" role="status">
          {state.message}
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

function CheckSubmit() {
  const { pending } = useFormStatus()
  return (
    <button
      type="submit"
      disabled={pending}
      className="border-input hover:bg-accent min-h-11 rounded-md border px-4 py-2.5 text-sm font-medium disabled:opacity-60"
    >
      {pending ? "Checking…" : "Check my receipt"}
    </button>
  )
}
