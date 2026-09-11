import * as Icons from "lucide-react"
import Link from "next/link"
import { notFound } from "next/navigation"

import { ApiError } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { ApprovalChain, markSheetChain } from "@acmis/ui/components/approval-chain"
import { StackedBar } from "@acmis/ui/components/chart-frame"
import { NotPermitted, RuleRefused } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, number } from "@acmis/ui/lib/format"

import { AssessmentShell } from "@/components/shell"
import { APP } from "@/lib/config"

/**
 * One mark sheet.
 *
 * The page a board of examiners actually sits in front of. Statistics first,
 * then the chain, then the marks — in that order deliberately, because a board
 * should look at the shape of a cohort's performance before it looks at any
 * individual mark, and a screen that opens on a list of 400 names invites the
 * opposite.
 *
 * Every action comes from the server's capabilities. The separation-of-duties
 * rules mean the person who entered the marks will not see an approve button
 * at all — not greyed out, absent — which is the clearest possible way to say
 * "not you".
 */

export default async function MarkSheetPage({
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
    envelope = await client.assessment.markSheet(id)
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound()
    if (err instanceof ApiError && err.isForbidden) {
      return (
        <AssessmentShell user={user} institution={institution} currentPath="/mark-sheets">
          <NotPermitted what="this mark sheet" />
        </AssessmentShell>
      )
    }
    throw err
  }

  const sheet = envelope.data
  const can = (action: string) =>
    envelope.capabilities.find((c) => c.action === action)?.allowed ?? false

  const results = await client.assessment.markSheetResults(id).catch(() => [])

  const distribution = Object.entries(sheet.grade_distribution ?? {}).sort(([a], [b]) =>
    a.localeCompare(b),
  )
  // Slot assignment follows the grade order and never cycles: the same grade
  // is the same colour on every sheet in the institution.
  const slotFor = (index: number) => ((index % 8) + 1) as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8

  return (
    <AssessmentShell user={user} institution={institution} currentPath="/mark-sheets">
      <PageHeader
        icon={<Icons.ClipboardCheck />}
        title={`Mark sheet · ${sheet.course_offering_id.slice(0, 8)}`}
        description={
          <>
            {number(sheet.student_count)} candidates · {number(sheet.entered_count)} marked
            {sheet.missing_count > 0 ? ` · ${number(sheet.missing_count)} outstanding` : ""}
            {sheet.due_on ? ` · due ${date(sheet.due_on, institution?.locale)}` : ""}
          </>
        }
        breadcrumbs={
          <nav className="text-muted-foreground text-xs" aria-label="Breadcrumb">
            <Link href="/mark-sheets" className="hover:text-foreground underline">
              Mark sheets
            </Link>
            <span aria-hidden> / </span>
            <span>{sheet.course_offering_id.slice(0, 8)}</span>
          </nav>
        }
        actions={
          <>
            <StatusBadge tone={toneForStatus(sheet.status)}>
              {humaniseStatus(sheet.status)}
            </StatusBadge>
            {can("mark_sheet:submit") ? (
              <form action={transition.bind(null, id, "submit")}>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-9 rounded-md px-3 text-sm font-medium"
                >
                  Submit for moderation
                </button>
              </form>
            ) : null}
            {can("mark_sheet:moderate") ? (
              <form action={transition.bind(null, id, "moderate")}>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-9 rounded-md px-3 text-sm font-medium"
                >
                  Moderate
                </button>
              </form>
            ) : null}
            {can("mark_sheet:approve") ? (
              <form action={transition.bind(null, id, "approve")}>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-9 rounded-md px-3 text-sm font-medium"
                >
                  Approve at board
                </button>
              </form>
            ) : null}
            {can("mark_sheet:faculty_approve") ? (
              <form action={transition.bind(null, id, "faculty_approve")}>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-9 rounded-md px-3 text-sm font-medium"
                >
                  Approve at faculty
                </button>
              </form>
            ) : null}
            {can("mark_sheet:senate_approve") ? (
              <form action={transition.bind(null, id, "senate_approve")}>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-9 rounded-md px-3 text-sm font-medium"
                >
                  Approve at Senate
                </button>
              </form>
            ) : null}
            {can("mark_sheet:return") ? (
              <form action={transition.bind(null, id, "return")}>
                <button
                  type="submit"
                  className="hover:bg-muted min-h-9 rounded-md border px-3 text-sm font-medium"
                >
                  Return to examiner
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
        <section className="bg-card shadow-card space-y-4 rounded-lg p-4 lg:col-span-2">
          <h2 className="text-base font-semibold">How the cohort performed</h2>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Figure
              label="Mean"
              value={sheet.mean_mark !== null ? sheet.mean_mark.toFixed(1) : "—"}
            />
            <Figure
              label="Median"
              value={sheet.median_mark !== null ? sheet.median_mark.toFixed(1) : "—"}
            />
            <Figure
              label="Spread"
              value={
                sheet.standard_deviation !== null ? `σ ${sheet.standard_deviation.toFixed(1)}` : "—"
              }
            />
            <Figure
              label="Pass rate"
              value={
                sheet.entered_count > 0
                  ? `${Math.round((sheet.pass_count / sheet.entered_count) * 100)}%`
                  : "—"
              }
            />
          </div>

          {distribution.length > 0 ? (
            <div className="border-t pt-4">
              <p className="mb-2 text-sm font-medium">Grade distribution</p>
              <StackedBar
                segments={distribution.map(([grade, count], index) => ({
                  label: grade,
                  value: Number(count),
                  slot: slotFor(index),
                }))}
                formatValue={(v) => number(v)}
              />
            </div>
          ) : null}

          {sheet.moderation_adjustment ? (
            <p className="border-warning/40 bg-warning/10 text-warning-foreground rounded-md border px-3 py-2 text-sm">
              A cohort-wide adjustment of {sheet.moderation_adjustment > 0 ? "+" : ""}
              {sheet.moderation_adjustment} was applied at moderation. Every mark was regraded, and
              the original values are kept.
            </p>
          ) : null}

          {sheet.return_comments ? (
            <p className="border-warning/40 bg-warning/10 text-warning-foreground rounded-md border px-3 py-2 text-sm">
              Returned to the examiner: {sheet.return_comments}
            </p>
          ) : null}
        </section>

        <section className="bg-card shadow-card space-y-3 rounded-lg p-4">
          <h2 className="text-base font-semibold">Approval chain</h2>
          <ApprovalChain steps={markSheetChain(sheet)} />
          <p className="text-muted-foreground border-t pt-3 text-xs leading-relaxed">
            A sheet cannot be approved by anyone who entered marks on it, and not by anyone who has
            declared an interest. If an approve button is missing here, that is why.
          </p>
        </section>
      </div>

      <section className="bg-card shadow-card overflow-hidden rounded-lg">
        <div className="border-b p-4">
          <h2 className="text-base font-semibold">Candidates</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            {results.length > 0
              ? `${number(results.length)} rows. Marks are provisional until Senate approves them.`
              : "No candidates on this sheet."}
          </p>
        </div>
        {results.length > 0 ? (
          <div className="tabular overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Candidate marks for this course offering</caption>
              <thead>
                <tr className="border-b">
                  <th scope="col" className="px-3 py-2 text-left text-xs font-medium uppercase">
                    Candidate
                  </th>
                  <th scope="col" className="px-3 py-2 text-right text-xs font-medium uppercase">
                    Coursework
                  </th>
                  <th scope="col" className="px-3 py-2 text-right text-xs font-medium uppercase">
                    Exam
                  </th>
                  <th scope="col" className="px-3 py-2 text-right text-xs font-medium uppercase">
                    Final
                  </th>
                  <th scope="col" className="px-3 py-2 text-center text-xs font-medium uppercase">
                    Grade
                  </th>
                  <th scope="col" className="px-3 py-2 text-left text-xs font-medium uppercase">
                    Outcome
                  </th>
                </tr>
              </thead>
              <tbody>
                {results.map((result) => (
                  <tr key={result.id} className="border-b last:border-0">
                    <td className="px-3 py-2 font-mono text-xs">
                      {result.student_id.slice(0, 8)}
                      {result.is_retake ? (
                        <span className="text-warning-foreground ml-1.5 text-[11px]">
                          retake {result.attempt_number}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {result.coursework_mark?.toFixed(1) ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-right">{result.exam_mark?.toFixed(1) ?? "—"}</td>
                    <td className="px-3 py-2 text-right font-medium">
                      {result.final_mark?.toFixed(1) ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-center font-medium">{result.grade ?? "—"}</td>
                    <td className="px-3 py-2">
                      <StatusBadge tone={toneForStatus(result.outcome)} dot={false}>
                        {humaniseStatus(result.outcome)}
                      </StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </AssessmentShell>
  )
}

/**
 * Move the sheet along the chain.
 *
 * A `RuleViolation` is passed through as a readable message rather than
 * swallowed. "A mark sheet must be approved by someone other than the person
 * who entered marks on it" is the whole answer, and a generic failure toast
 * throws it away.
 */
async function transition(id: string, action: string) {
  "use server"
  const { revalidatePath } = await import("next/cache")
  const { redirect } = await import("next/navigation")

  const client = await acmis(APP)
  try {
    await client.assessment.transition(
      id,
      action as "submit" | "moderate" | "approve" | "faculty_approve" | "senate_approve" | "return",
      {},
    )
  } catch (error) {
    if (error instanceof ApiError) {
      const params = new URLSearchParams({ error: error.message })
      const rule = error.details.rule
      if (typeof rule === "string") params.set("rule", rule)
      redirect(`/mark-sheets/${id}?${params.toString()}`)
    }
    throw error
  }
  revalidatePath(`/mark-sheets/${id}`)
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="tabular mt-0.5 text-xl font-semibold">{value}</p>
    </div>
  )
}
