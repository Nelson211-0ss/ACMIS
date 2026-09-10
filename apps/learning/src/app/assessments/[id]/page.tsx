import * as Icons from "lucide-react"
import Link from "next/link"
import { notFound } from "next/navigation"

import { ApiError } from "@acmis/api-client"
import type { OnlineAssessment } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { ApprovalChain, type ChainStep } from "@acmis/ui/components/approval-chain"
import { Meter } from "@acmis/ui/components/chart-frame"
import { NotPermitted, RuleRefused } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { dateTime, duration, humaniseStatus, number } from "@acmis/ui/lib/format"

import { LearningShell } from "@/components/shell"
import { APP } from "@/lib/config"

/**
 * One online assessment: its settings, its state, and the actions available.
 *
 * The lifecycle is the substance of this page. An assessment goes draft →
 * review → scheduled → open → closed → marked → released, and only then can
 * its scores be pushed into the mark sheet. Each step is a separate grant, and
 * the review step refuses the author — the person who wrote the questions is
 * the last one able to spot that one is ambiguous.
 */

export default async function AssessmentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<{ error?: string; rule?: string }>
}) {
  const { id } = await params
  const { error, rule } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const institution = await client.public.institution().catch(() => null)

  let envelope
  try {
    envelope = await client.learning.assessment(id)
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound()
    if (err instanceof ApiError && err.isForbidden) {
      return (
        <LearningShell user={user} institution={institution} currentPath="/assessments">
          <NotPermitted what="this assessment" />
        </LearningShell>
      )
    }
    throw err
  }

  const assessment = envelope.data
  const can = (action: string) =>
    envelope.capabilities.find((c) => c.action === action)?.allowed ?? false
  const chain = buildChain(assessment)
  const countsForCredit =
    assessment.kind !== "practice" && assessment.assessment_component_id !== null

  return (
    <LearningShell user={user} institution={institution} currentPath="/assessments">
      <PageHeader
        title={assessment.title}
        description={
          <>
            {humaniseStatus(assessment.kind)} ·{" "}
            {number(assessment.total_marks)} marks ·{" "}
            {assessment.duration_minutes
              ? duration(assessment.duration_minutes)
              : "no time limit"}
            {countsForCredit
              ? " · counts toward the course result"
              : " · does not count toward the course result"}
          </>
        }
        breadcrumbs={
          <nav className="text-muted-foreground text-xs" aria-label="Breadcrumb">
            <Link href="/assessments" className="hover:text-foreground underline">
              Tests &amp; quizzes
            </Link>
            <span aria-hidden> / </span>
            <span>{assessment.title}</span>
          </nav>
        }
        actions={
          <>
            <StatusBadge tone={toneForStatus(assessment.status)}>
              {humaniseStatus(assessment.status)}
            </StatusBadge>
            {/* Every button below is drawn from the server's own decision.
                A button that appears and then 403s is worse than no button. */}
            {can("online_assessment:submit_for_review") &&
            assessment.status === "draft" ? (
              <form action={submitForReview.bind(null, assessment.id)}>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-9 rounded-md px-3 text-sm font-medium"
                >
                  Submit for review
                </button>
              </form>
            ) : null}
            {can("online_assessment:open") && assessment.status === "scheduled" ? (
              <form action={openToCandidates.bind(null, assessment.id)}>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-9 rounded-md px-3 text-sm font-medium"
                >
                  Open to candidates
                </button>
              </form>
            ) : null}
            {can("online_assessment:release") &&
            assessment.pending_manual_marking === 0 &&
            ["closed", "marked"].includes(assessment.status) ? (
              <form action={releaseScores.bind(null, assessment.id)}>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-9 rounded-md px-3 text-sm font-medium"
                >
                  Release scores
                </button>
              </form>
            ) : null}
            {can("online_assessment:push_marks") && assessment.status === "released" ? (
              <form action={pushMarks.bind(null, assessment.id)}>
                <button
                  type="submit"
                  className="border-module text-module hover:bg-module/10 min-h-9 rounded-md border px-3 text-sm font-medium"
                >
                  Write to mark sheet
                </button>
              </form>
            ) : null}
          </>
        }
      />

      {error ? (
        <RuleRefused
          message={decodeURIComponent(error)}
          rule={rule ? decodeURIComponent(rule) : undefined}
        />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="bg-card space-y-4 rounded-lg border p-4 lg:col-span-2">
          <h2 className="text-base font-semibold">Progress</h2>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Figure label="Attempts started" value={number(assessment.attempt_count)} />
            <Figure label="Submitted" value={number(assessment.submitted_count)} />
            <Figure
              label="Awaiting marking"
              value={number(assessment.pending_manual_marking)}
              tone={assessment.pending_manual_marking > 0 ? "warning" : "muted"}
            />
          </div>

          {assessment.submitted_count > 0 ? (
            <div className="space-y-3 border-t pt-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Figure
                  label="Mean"
                  value={
                    assessment.mean_score !== null
                      ? `${assessment.mean_score.toFixed(1)} / ${number(assessment.total_marks)}`
                      : "—"
                  }
                />
                <Figure
                  label="Median"
                  value={
                    assessment.median_score !== null
                      ? assessment.median_score.toFixed(1)
                      : "—"
                  }
                />
                <Figure
                  label="Spread"
                  value={
                    assessment.standard_deviation !== null
                      ? `σ ${assessment.standard_deviation.toFixed(1)}`
                      : "—"
                  }
                />
              </div>
              <p className="text-muted-foreground text-xs leading-relaxed">
                A mean far below the pass mark, or a spread near zero, is a
                question about the paper before it is a question about the
                candidates. Item statistics per question are on the review tab —
                a question with high facility and near-zero discrimination is
                measuring nothing, and a negative discrimination almost always
                means the answer key is wrong.
              </p>
            </div>
          ) : null}

          {assessment.pending_manual_marking > 0 ? (
            <div className="border-t pt-4">
              <Meter
                label="Marking progress"
                value={Math.max(
                  0,
                  assessment.submitted_count - assessment.pending_manual_marking,
                )}
                max={assessment.submitted_count || 1}
                tone="warning"
                formatValue={(v) => number(v)}
              />
              <a
                href={`/assessments/${assessment.id}/marking`}
                className="bg-primary text-primary-foreground hover:bg-primary/90 mt-3 inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium"
              >
                <Icons.PenLine className="size-3.5" aria-hidden />
                Mark {number(assessment.pending_manual_marking)} answer
                {assessment.pending_manual_marking === 1 ? "" : "s"}
              </a>
              <p className="text-muted-foreground mt-2 text-xs">
                Grouped by question rather than by candidate — marking every
                script&rsquo;s question 3 together is both faster and more
                consistent.
              </p>
            </div>
          ) : null}
        </section>

        <section className="bg-card space-y-3 rounded-lg border p-4">
          <h2 className="text-base font-semibold">Lifecycle</h2>
          <ApprovalChain steps={chain} />
          <p className="text-muted-foreground border-t pt-3 text-xs leading-relaxed">
            Releasing scores and writing them into the academic record are
            separate acts. The push writes a component score onto a{" "}
            <em>draft</em> mark sheet and nothing more — moderation, the
            department board, the faculty board and Senate still govern every
            mark that reaches a transcript.
          </p>
        </section>
      </div>

      <section className="bg-card rounded-lg border p-4">
        <h2 className="text-base font-semibold">Settings</h2>
        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <Setting
            label="Behaviour"
            value={humaniseStatus(assessment.behaviour)}
            note={BEHAVIOUR_NOTES[assessment.behaviour]}
          />
          <Setting
            label="Attempts"
            value={`${assessment.max_attempts} · ${humaniseStatus(assessment.attempt_grading)} counts`}
            note={
              countsForCredit && assessment.max_attempts > 1
                ? "More than one attempt on an assessment that counts is unusual — the review step flags it."
                : undefined
            }
          />
          <Setting
            label="Question order"
            value={assessment.shuffle_questions ? "Shuffled within sections" : "Fixed"}
            note={
              assessment.shuffle_questions
                ? "Shuffling removes opportunistic copying between adjacent candidates. It is not security, and it is cheap."
                : undefined
            }
          />
          <Setting
            label="Score visibility"
            value={humaniseStatus(assessment.score_visibility)}
            note={
              assessment.score_visibility === "immediately" && countsForCredit
                ? "Showing scores immediately on an assessment that counts lets candidates compare answers before marking is complete."
                : undefined
            }
          />
          <Setting
            label="Opens"
            value={dateTime(assessment.opens_at, institution?.locale, institution?.timezone)}
          />
          <Setting
            label="Closes"
            value={dateTime(assessment.closes_at, institution?.locale, institution?.timezone)}
          />
        </dl>
      </section>
    </LearningShell>
  )
}

/**
 * The lifecycle transitions, as Server Actions.
 *
 * Each one lets `RuleViolation` through to the page as a readable message
 * rather than swallowing it: "the mark sheet has left draft, corrections go
 * through moderation" is the whole answer, and a generic failure toast throws
 * it away.
 */
async function runTransition(
  id: string,
  work: (client: Awaited<ReturnType<typeof acmis>>) => Promise<unknown>,
) {
  "use server"
  const { revalidatePath } = await import("next/cache")
  const { redirect } = await import("next/navigation")

  const client = await acmis(APP)
  try {
    await work(client)
  } catch (error) {
    if (error instanceof ApiError) {
      const params = new URLSearchParams({ error: error.message })
      const rule = error.details.rule
      if (typeof rule === "string") params.set("rule", rule)
      redirect(`/assessments/${id}?${params.toString()}`)
    }
    throw error
  }
  revalidatePath(`/assessments/${id}`)
}

async function submitForReview(id: string) {
  "use server"
  await runTransition(id, (client) => client.learning.submitForReview(id))
}

async function openToCandidates(id: string) {
  "use server"
  await runTransition(id, (client) => client.learning.open(id))
}

async function releaseScores(id: string) {
  "use server"
  await runTransition(id, (client) => client.learning.release(id))
}

async function pushMarks(id: string) {
  "use server"
  await runTransition(id, (client) => client.learning.pushMarks(id))
}

const BEHAVIOUR_NOTES: Record<string, string> = {
  deferred_feedback:
    "Answer everything, submit once, see nothing until after. The classic examination.",
  immediate_feedback: "One try per question, checked as you go. A revision quiz.",
  interactive_with_tries:
    "Several tries per question, each wrong try costing a fraction of the marks. Rewards working the answer out over guessing.",
  adaptive: "Like interactive, with no fixed try limit.",
  manual: "Nothing is auto-marked; every answer goes to a human.",
}

function buildChain(assessment: OnlineAssessment): ChainStep[] {
  const order = ["draft", "review", "scheduled", "open", "closed", "marked", "released"]
  const position = order.indexOf(assessment.status)
  const step = (key: string, label: string, index: number, note?: string): ChainStep => ({
    key,
    label,
    state:
      position > index ? "done" : position === index ? "current" : "pending",
    note,
  })

  return [
    step("draft", "Drafted", 0),
    step(
      "review",
      "Reviewed by a second examiner",
      1,
      assessment.review_comments ?? undefined,
    ),
    step("scheduled", "Scheduled", 2),
    step("open", "Open to candidates", 3),
    step("closed", "Closed", 4),
    step("marked", "Marking complete", 5),
    {
      key: "released",
      label: "Released to candidates",
      state: assessment.released_at ? "done" : position === 6 ? "current" : "pending",
      at: assessment.released_at ? dateTime(assessment.released_at) : null,
    },
    {
      key: "pushed",
      label: "Written to the mark sheet",
      state: assessment.pushed_to_mark_sheet_at ? "done" : "pending",
      at: assessment.pushed_to_mark_sheet_at
        ? dateTime(assessment.pushed_to_mark_sheet_at)
        : null,
      note: assessment.pushed_to_mark_sheet_at
        ? null
        : "Lands as a component score on a draft mark sheet, never as a final mark.",
    },
  ]
}

function Figure({
  label,
  value,
  tone = "muted",
}: {
  label: string
  value: string
  tone?: "muted" | "warning"
}) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      <p
        className={
          tone === "warning"
            ? "text-warning-foreground tabular mt-0.5 text-xl font-semibold"
            : "tabular mt-0.5 text-xl font-semibold"
        }
      >
        {value}
      </p>
    </div>
  )
}

function Setting({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note?: string
}) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5 font-medium">{value}</dd>
      {note ? (
        <p className="text-muted-foreground mt-1 text-xs leading-relaxed">{note}</p>
      ) : null}
    </div>
  )
}
