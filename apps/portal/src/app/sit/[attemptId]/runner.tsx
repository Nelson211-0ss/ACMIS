"use client"

import * as Icons from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import type { PresentedQuestion } from "@acmis/api-client"
import { countdown } from "@acmis/ui/lib/format"
import { cn } from "@acmis/ui/lib/utils"

/**
 * The examination runner.
 *
 * The hardest screen in the system, and the constraints are all about the
 * environment it runs in: a shared computer lab or a phone, on a connection
 * that drops, in a room where a student has one chance.
 *
 * What that means concretely:
 *
 * - **Answers save as they are given**, debounced, with the save state
 *   visible. Not on submit. A power cut in the third hour must not cost a
 *   candidate their paper.
 * - **A queue that survives being offline.** A failed save is retried, and the
 *   banner tells the candidate their work is not yet safe. Silence here is the
 *   cruelest possible failure.
 * - **The server's clock is the clock.** The countdown renders from
 *   `expiresAt`, sent by the server; the local clock is never trusted, and the
 *   display drifting is fine while the deadline being wrong is not.
 * - **One question per screen on a phone**, the full list on a desktop. A
 *   45-question paper on a 360px screen with a fixed sidebar navigator is
 *   unusable.
 * - **Integrity events are reported, never enforced.** A focus loss in a place
 *   with poor connectivity and a candidate opening another tab are
 *   indistinguishable from here; an invigilator weighs them.
 */

type Answer = Record<string, unknown>

interface SaveState {
  status: "saved" | "saving" | "queued" | "failed"
  at: number | null
  pending: number
}

export function ExamRunner({
  attemptId,
  assessmentTitle,
  totalMarks,
  expiresAt,
  questions: initialQuestions,
  allowBacktracking,
  onePerPage,
  monitorFocus,
}: {
  attemptId: string
  assessmentTitle: string
  totalMarks: number
  /** ISO instant from the server. The only deadline that counts. */
  expiresAt: string | null
  questions: PresentedQuestion[]
  /**
   * Part of the contract the page passes, and deliberately not read here.
   *
   * This runner implements `deferred_feedback`: nothing is revealed during
   * the sitting. The other behaviours — immediate feedback, interactive with
   * tries — change what the *marker* does and when a score becomes visible,
   * both of which happen server-side after submission. Showing feedback
   * mid-paper would need the answer key in the browser, which is the one
   * disclosure that invalidates a cohort's sitting.
   */
  behaviour: string
  allowBacktracking: boolean
  onePerPage: boolean
  monitorFocus: boolean
}) {
  const [answers, setAnswers] = useState<Record<string, Answer>>(() =>
    Object.fromEntries(initialQuestions.map((q) => [q.question_id, q.answer ?? {}])),
  )
  const [flagged, setFlagged] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(initialQuestions.map((q) => [q.question_id, q.flagged])),
  )
  const [save, setSave] = useState<SaveState>({ status: "saved", at: null, pending: 0 })
  const [index, setIndex] = useState(0)
  const [confirming, setConfirming] = useState(false)
  const [remaining, setRemaining] = useState<number | null>(null)

  // A pending queue keyed by question, so two edits to the same question
  // collapse into one request rather than racing each other to the server.
  const queue = useRef<Map<string, { answer: Answer; flagged: boolean }>>(new Map())
  const flushing = useRef(false)

  const questions = initialQuestions
  const current = questions[index]

  const flush = useCallback(async () => {
    if (flushing.current || queue.current.size === 0) return
    flushing.current = true
    setSave((s) => ({ ...s, status: "saving" }))

    const batch = [...queue.current.entries()]
    let failed = 0
    for (const [questionId, payload] of batch) {
      try {
        const response = await fetch(`/api/attempts/${attemptId}/answers`, {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            question_id: questionId,
            answer: payload.answer,
            flagged: payload.flagged,
          }),
        })
        if (!response.ok) throw new Error(String(response.status))
        queue.current.delete(questionId)
      } catch {
        failed += 1
      }
    }

    flushing.current = false
    setSave({
      status: failed > 0 ? "failed" : queue.current.size > 0 ? "queued" : "saved",
      at: failed > 0 ? null : Date.now(),
      pending: queue.current.size,
    })
  }, [attemptId])

  // Debounced flush. 800ms is short enough that a dropped connection loses at
  // most one keystroke's worth, and long enough that typing an essay does not
  // produce a request per character.
  useEffect(() => {
    const timer = setTimeout(() => void flush(), 800)
    return () => clearTimeout(timer)
  }, [answers, flagged, flush])

  // A slow retry for anything the debounce could not deliver, so a candidate
  // who goes offline for a minute recovers without touching anything.
  useEffect(() => {
    const timer = setInterval(() => {
      if (queue.current.size > 0) void flush()
    }, 10_000)
    return () => clearInterval(timer)
  }, [flush])

  useEffect(() => {
    if (!expiresAt) return
    const deadline = new Date(expiresAt).getTime()
    const tick = () => setRemaining(Math.max(0, Math.round((deadline - Date.now()) / 1000)))
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [expiresAt])

  // Auto-submit when the clock runs out. The server expires the attempt
  // regardless; submitting here means the candidate sees a confirmation
  // rather than a silent lockout, and their saved answers are marked either
  // way.
  useEffect(() => {
    if (remaining !== null && remaining <= 0) {
      void flush().then(() => {
        document
          .getElementById("acmis-submit-form")
          ?.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }))
      })
    }
  }, [remaining, flush])

  useEffect(() => {
    if (!monitorFocus) return
    const report = (kind: string) => {
      void fetch(`/api/attempts/${attemptId}/integrity`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ kind }),
        keepalive: true,
      }).catch(() => undefined)
    }
    const onBlur = () => report("focus_loss")
    const onOffline = () => report("offline")
    const onOnline = () => report("reconnect")
    window.addEventListener("blur", onBlur)
    window.addEventListener("offline", onOffline)
    window.addEventListener("online", onOnline)
    return () => {
      window.removeEventListener("blur", onBlur)
      window.removeEventListener("offline", onOffline)
      window.removeEventListener("online", onOnline)
    }
  }, [attemptId, monitorFocus])

  // Warn on navigating away with unsaved work. Only when there genuinely is
  // some — a spurious "are you sure" on every exit trains people to click
  // through it.
  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (queue.current.size > 0) event.preventDefault()
    }
    window.addEventListener("beforeunload", onBeforeUnload)
    return () => window.removeEventListener("beforeunload", onBeforeUnload)
  }, [])

  const setAnswer = (questionId: string, answer: Answer) => {
    setAnswers((previous) => ({ ...previous, [questionId]: answer }))
    queue.current.set(questionId, { answer, flagged: flagged[questionId] ?? false })
    setSave((s) => ({ ...s, status: "queued", pending: queue.current.size }))
  }

  const toggleFlag = (questionId: string) => {
    const next = !flagged[questionId]
    setFlagged((previous) => ({ ...previous, [questionId]: next }))
    queue.current.set(questionId, { answer: answers[questionId] ?? {}, flagged: next })
    setSave((s) => ({ ...s, status: "queued", pending: queue.current.size }))
  }

  const answeredCount = useMemo(
    () =>
      questions.filter((q) => {
        const value = answers[q.question_id]
        if (!value) return false
        return Object.values(value).some((v) =>
          Array.isArray(v) ? v.length > 0 : v !== null && v !== undefined && v !== "",
        )
      }).length,
    [answers, questions],
  )

  const lowTime = remaining !== null && remaining <= 300

  return (
    <div className="min-h-dvh pb-32 sm:pb-24">
      {/* The bar carries the two things a candidate looks at constantly: the
          clock and whether their work is safe. Sticky, because scrolling a
          45-question paper must never hide either. */}
      <header className="bg-background/95 sticky top-0 z-30 border-b backdrop-blur">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2.5 sm:px-4">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{assessmentTitle}</p>
            <p className="text-muted-foreground text-xs">
              {answeredCount} of {questions.length} answered · {totalMarks} marks
            </p>
          </div>

          {remaining !== null ? (
            <div
              className={cn(
                "tabular rounded-md px-2.5 py-1 text-right font-mono text-base font-semibold sm:text-lg",
                lowTime ? "bg-destructive/10 text-destructive" : "bg-muted text-foreground",
              )}
              role="timer"
              aria-live={lowTime ? "polite" : "off"}
              aria-label="Time remaining"
            >
              {countdown(remaining)}
              <span className="text-muted-foreground block text-[10px] font-normal">remaining</span>
            </div>
          ) : null}

          <SaveIndicator state={save} onRetry={() => void flush()} />
        </div>
      </header>

      {save.status === "failed" ? (
        <p
          role="alert"
          className="bg-destructive text-destructive-foreground px-3 py-2 text-center text-sm font-medium"
        >
          {save.pending} answer{save.pending === 1 ? "" : "s"} not yet saved. Stay on this page — it
          keeps retrying. Do not close the browser.
        </p>
      ) : null}

      <main className="mx-auto max-w-4xl px-3 py-5 sm:px-4">
        {/* One question at a time below `md`, always when the paper says so.
            A navigator sidebar on a 360px screen leaves no room for the
            question. */}
        <div className={cn(onePerPage ? "" : "md:hidden")}>
          {current ? (
            <QuestionCard
              question={current}
              answer={answers[current.question_id] ?? {}}
              flagged={flagged[current.question_id] ?? false}
              onAnswer={(value) => setAnswer(current.question_id, value)}
              onFlag={() => toggleFlag(current.question_id)}
              position={index + 1}
              total={questions.length}
            />
          ) : null}
        </div>

        {!onePerPage ? (
          <div className="hidden space-y-4 md:block">
            {questions.map((question, position) => (
              <QuestionCard
                key={question.question_id}
                question={question}
                answer={answers[question.question_id] ?? {}}
                flagged={flagged[question.question_id] ?? false}
                onAnswer={(value) => setAnswer(question.question_id, value)}
                onFlag={() => toggleFlag(question.question_id)}
                position={position + 1}
                total={questions.length}
              />
            ))}
          </div>
        ) : null}
      </main>

      {/* Fixed footer: paging on a phone, submit everywhere. Clears the home
          indicator on a notched device. */}
      <footer
        className="bg-background/95 fixed inset-x-0 bottom-0 z-30 border-t backdrop-blur"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="mx-auto flex max-w-4xl items-center gap-2 px-3 py-2.5 sm:px-4">
          <div className={cn("flex flex-1 items-center gap-2", onePerPage ? "" : "md:hidden")}>
            <button
              type="button"
              onClick={() => setIndex((i) => Math.max(0, i - 1))}
              disabled={index === 0 || !allowBacktracking}
              className="hover:bg-muted min-h-11 min-w-11 rounded-md border px-3 text-sm font-medium disabled:opacity-40"
              aria-label="Previous question"
            >
              <Icons.ChevronLeft className="size-4" aria-hidden />
            </button>
            <span className="text-muted-foreground tabular text-xs">
              {index + 1} / {questions.length}
            </span>
            <button
              type="button"
              onClick={() => setIndex((i) => Math.min(questions.length - 1, i + 1))}
              disabled={index >= questions.length - 1}
              className="hover:bg-muted min-h-11 min-w-11 rounded-md border px-3 text-sm font-medium disabled:opacity-40"
              aria-label="Next question"
            >
              <Icons.ChevronRight className="size-4" aria-hidden />
            </button>
          </div>

          <div className="hidden flex-1 md:block">
            {!onePerPage ? (
              <p className="text-muted-foreground text-xs">
                {questions.length - answeredCount > 0
                  ? `${questions.length - answeredCount} question${questions.length - answeredCount === 1 ? "" : "s"} unanswered`
                  : "Every question answered"}
              </p>
            ) : null}
          </div>

          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 rounded-md px-4 text-sm font-semibold"
          >
            Submit
          </button>
        </div>
      </footer>

      {confirming ? (
        <SubmitDialog
          attemptId={attemptId}
          answered={answeredCount}
          total={questions.length}
          unsaved={save.pending}
          onCancel={() => setConfirming(false)}
          onBeforeSubmit={flush}
        />
      ) : null}
    </div>
  )
}

function SaveIndicator({ state, onRetry }: { state: SaveState; onRetry: () => void }) {
  const label = {
    saved: "Saved",
    saving: "Saving…",
    queued: "Saving…",
    failed: "Not saved",
  }[state.status]

  return (
    <button
      type="button"
      onClick={onRetry}
      // `aria-live` so a screen-reader user hears the state change; this is
      // the one piece of feedback a candidate must not miss.
      aria-live="polite"
      className={cn(
        "flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium",
        state.status === "failed"
          ? "bg-destructive/10 text-destructive"
          : state.status === "saved"
            ? "text-success"
            : "text-muted-foreground",
      )}
    >
      {state.status === "failed" ? (
        <Icons.AlertTriangle className="size-3.5" aria-hidden />
      ) : state.status === "saved" ? (
        <Icons.Check className="size-3.5" aria-hidden />
      ) : (
        <Icons.Loader2 className="size-3.5 animate-spin" aria-hidden />
      )}
      <span>{label}</span>
    </button>
  )
}

function SubmitDialog({
  attemptId,
  answered,
  total,
  unsaved,
  onCancel,
  onBeforeSubmit,
}: {
  attemptId: string
  answered: number
  total: number
  unsaved: number
  onCancel: () => void
  onBeforeSubmit: () => Promise<void>
}) {
  const [submitting, setSubmitting] = useState(false)
  const unanswered = total - answered

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="submit-title"
      className="fixed inset-0 z-40 grid place-items-end sm:place-items-center"
    >
      <button
        type="button"
        aria-label="Cancel"
        onClick={onCancel}
        className="bg-foreground/50 absolute inset-0"
      />
      {/* A sheet on a phone, a dialog on a desktop. */}
      <div className="bg-card shadow-card relative w-full max-w-md rounded-t-xl p-5 sm:rounded-xl">
        <h2 id="submit-title" className="text-lg font-semibold">
          Submit this paper?
        </h2>
        <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
          You have answered {answered} of {total} questions.
          {unanswered > 0 ? (
            <>
              {" "}
              <strong className="text-warning-foreground">
                {unanswered} question{unanswered === 1 ? "" : "s"} unanswered
              </strong>{" "}
              — an unanswered question scores zero.
            </>
          ) : null}
        </p>
        {unsaved > 0 ? (
          <p className="border-warning/40 bg-warning/10 text-warning-foreground mt-3 rounded-md border px-3 py-2 text-sm">
            {unsaved} answer{unsaved === 1 ? "" : "s"} not yet saved. Submitting will try to save{" "}
            {unsaved === 1 ? "it" : "them"} first.
          </p>
        ) : null}
        <p className="text-muted-foreground mt-3 text-xs">
          Once submitted, a paper cannot be reopened or changed.
        </p>

        <form
          id="acmis-submit-form"
          action={`/api/attempts/${attemptId}/submit`}
          method="post"
          onSubmit={(event) => {
            if (submitting) return
            event.preventDefault()
            setSubmitting(true)
            void onBeforeSubmit().then(() => {
              ;(event.target as HTMLFormElement).submit()
            })
          }}
          className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"
        >
          <button
            type="button"
            onClick={onCancel}
            className="hover:bg-muted min-h-11 rounded-md border px-4 text-sm font-medium"
          >
            Keep working
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 rounded-md px-4 text-sm font-semibold disabled:opacity-60"
          >
            {submitting ? "Submitting…" : "Submit paper"}
          </button>
        </form>
      </div>
    </div>
  )
}

/** One question, with the input its kind needs. */
function QuestionCard({
  question,
  answer,
  flagged,
  onAnswer,
  onFlag,
  position,
  total,
}: {
  question: PresentedQuestion
  answer: Answer
  flagged: boolean
  onAnswer: (answer: Answer) => void
  onFlag: () => void
  position: number
  total: number
}) {
  return (
    <section className="bg-card shadow-card rounded-lg p-4 sm:p-5">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-muted-foreground text-xs">
            Question {position} of {total}
            {question.section ? ` · ${question.section}` : ""} · {question.marks} mark
            {question.marks === 1 ? "" : "s"}
          </p>
        </div>
        <button
          type="button"
          onClick={onFlag}
          aria-pressed={flagged}
          aria-label={flagged ? "Remove flag" : "Flag for review"}
          className={cn(
            "grid size-11 shrink-0 place-items-center rounded-md border",
            flagged ? "border-warning bg-warning/15 text-warning-foreground" : "hover:bg-muted",
          )}
        >
          <Icons.Flag className="size-4" aria-hidden />
        </button>
      </header>

      {/* `text-pretty` so a long stem does not leave one word on the last
          line, and `break-words` so an unbroken formula cannot overflow. */}
      <p className="mb-4 text-pretty break-words text-[15px] leading-relaxed">{question.stem}</p>

      <QuestionInput question={question} answer={answer} onAnswer={onAnswer} />
    </section>
  )
}

function QuestionInput({
  question,
  answer,
  onAnswer,
}: {
  question: PresentedQuestion
  answer: Answer
  onAnswer: (answer: Answer) => void
}) {
  const selected = (answer.option_labels as string[] | undefined) ?? []

  switch (question.kind) {
    case "multiple_choice":
    case "true_false":
      return (
        <ul className="space-y-2">
          {question.options.map((option) => {
            const checked = selected.includes(option.label)
            return (
              <li key={option.label}>
                {/* The whole row is the target — a 16px radio is not a thumb
                    target, and this is sat on phones. */}
                <label
                  className={cn(
                    "flex min-h-11 cursor-pointer items-start gap-3 rounded-md border p-3 text-sm",
                    checked ? "border-module bg-module/5" : "hover:bg-muted/60",
                  )}
                >
                  <input
                    type="radio"
                    name={question.question_id}
                    checked={checked}
                    onChange={() => onAnswer({ option_labels: [option.label] })}
                    className="mt-0.5 size-4 shrink-0"
                  />
                  <span className="min-w-0">
                    <span className="text-muted-foreground mr-1.5 font-mono text-xs">
                      {option.label}
                    </span>
                    <span className="break-words">{option.body}</span>
                  </span>
                </label>
              </li>
            )
          })}
        </ul>
      )

    case "multiple_response":
      return (
        <>
          <p className="text-muted-foreground mb-2 text-xs">
            Select all that apply. Partial credit is given, and an incorrect selection cancels a
            correct one.
          </p>
          <ul className="space-y-2">
            {question.options.map((option) => {
              const checked = selected.includes(option.label)
              return (
                <li key={option.label}>
                  <label
                    className={cn(
                      "flex min-h-11 cursor-pointer items-start gap-3 rounded-md border p-3 text-sm",
                      checked ? "border-module bg-module/5" : "hover:bg-muted/60",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        onAnswer({
                          option_labels: checked
                            ? selected.filter((l) => l !== option.label)
                            : [...selected, option.label],
                        })
                      }
                      className="mt-0.5 size-4 shrink-0"
                    />
                    <span className="min-w-0">
                      <span className="text-muted-foreground mr-1.5 font-mono text-xs">
                        {option.label}
                      </span>
                      <span className="break-words">{option.body}</span>
                    </span>
                  </label>
                </li>
              )
            })}
          </ul>
        </>
      )

    case "numeric":
    case "calculated":
      return (
        <div className="space-y-1.5">
          <label htmlFor={`n-${question.question_id}`} className="text-sm font-medium">
            Your answer
          </label>
          <input
            id={`n-${question.question_id}`}
            // `decimal` rather than `numeric`: the numeric keypad on iOS has
            // no decimal point, which makes 9.81 impossible to type.
            inputMode="decimal"
            defaultValue={String(answer.value ?? "")}
            onChange={(event) => onAnswer({ value: event.target.value })}
            className="border-input bg-background min-h-11 w-full max-w-xs rounded-md border px-3 text-base"
            placeholder="e.g. 9.81"
          />
          <p className="text-muted-foreground text-xs">A small rounding difference is accepted.</p>
        </div>
      )

    case "short_answer":
      return (
        <div className="space-y-1.5">
          <label htmlFor={`s-${question.question_id}`} className="text-sm font-medium">
            Your answer
          </label>
          <input
            id={`s-${question.question_id}`}
            defaultValue={String(answer.text ?? "")}
            onChange={(event) => onAnswer({ text: event.target.value })}
            // `text-base`, not `text-sm`: iOS zooms the whole page in on a
            // focused input below 16px, and the page never zooms back out.
            className="border-input bg-background min-h-11 w-full rounded-md border px-3 text-base"
          />
        </div>
      )

    case "essay":
      return (
        <div className="space-y-1.5">
          <label htmlFor={`e-${question.question_id}`} className="text-sm font-medium">
            Your answer
          </label>
          <textarea
            id={`e-${question.question_id}`}
            defaultValue={String(answer.text ?? "")}
            onChange={(event) => onAnswer({ text: event.target.value })}
            rows={10}
            className="border-input bg-background w-full resize-y rounded-md border p-3 text-base leading-relaxed"
          />
          <p className="text-muted-foreground text-xs">
            Saved as you type. This answer is marked by a person, so your score appears once marking
            is complete.
          </p>
        </div>
      )

    case "ordering":
      return (
        <OrderingInput
          options={question.options}
          value={(answer.order as string[] | undefined) ?? question.options.map((o) => o.label)}
          onChange={(order) => onAnswer({ order })}
        />
      )

    default:
      return (
        <div className="space-y-1.5">
          <label htmlFor={`d-${question.question_id}`} className="text-sm font-medium">
            Your answer
          </label>
          <textarea
            id={`d-${question.question_id}`}
            defaultValue={String(answer.text ?? "")}
            onChange={(event) => onAnswer({ text: event.target.value })}
            rows={5}
            className="border-input bg-background w-full rounded-md border p-3 text-base"
          />
        </div>
      )
  }
}

/**
 * Ordering, with buttons rather than drag-and-drop.
 *
 * Drag-and-drop is worse here on every axis that matters: it is unusable with
 * a keyboard, awkward on a touch screen inside a scrolling page, and
 * invisible to a screen reader. Two buttons per row work everywhere.
 */
function OrderingInput({
  options,
  value,
  onChange,
}: {
  options: Array<{ label: string; body: string }>
  value: string[]
  onChange: (order: string[]) => void
}) {
  const byLabel = new Map(options.map((o) => [o.label, o.body]))
  const move = (from: number, to: number) => {
    if (to < 0 || to >= value.length) return
    const next = [...value]
    const [item] = next.splice(from, 1)
    if (item !== undefined) next.splice(to, 0, item)
    onChange(next)
  }

  return (
    <ol className="space-y-2">
      {value.map((label, position) => (
        <li key={label} className="flex items-center gap-2 rounded-md border p-2">
          <span className="text-muted-foreground tabular w-6 shrink-0 text-center text-xs">
            {position + 1}
          </span>
          <span className="min-w-0 flex-1 break-words text-sm">{byLabel.get(label) ?? label}</span>
          <span className="flex shrink-0 gap-1">
            <button
              type="button"
              onClick={() => move(position, position - 1)}
              disabled={position === 0}
              aria-label={`Move "${byLabel.get(label) ?? label}" up`}
              className="hover:bg-muted grid size-11 place-items-center rounded-md border disabled:opacity-30"
            >
              <Icons.ChevronUp className="size-4" aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => move(position, position + 1)}
              disabled={position === value.length - 1}
              aria-label={`Move "${byLabel.get(label) ?? label}" down`}
              className="hover:bg-muted grid size-11 place-items-center rounded-md border disabled:opacity-30"
            >
              <Icons.ChevronDown className="size-4" aria-hidden />
            </button>
          </span>
        </li>
      ))}
    </ol>
  )
}
