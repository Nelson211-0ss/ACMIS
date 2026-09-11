import * as Icons from "lucide-react"
import Link from "next/link"

import { ApiError } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame } from "@acmis/ui/components/chart-frame"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { number } from "@acmis/ui/lib/format"

import { QualityShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Evaluation results" }

/**
 * One evaluation's results.
 *
 * Two ways this page shows nothing, and it distinguishes them, because they
 * mean opposite things: too few responses to report without identifying the
 * respondents, and results still sealed because the marks are not in. The
 * first is permanent for that run; the second is a date.
 */
export default async function EvaluationResultsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, threshold] = await Promise.all([
    client.public.institution().catch(() => null),
    client.quality.reportingThreshold().catch(() => ({
      minimum_responses: 5,
      reason: "",
    })),
  ])

  const canSeeComments = ["quality:admin", "people:manage_unit"].some((code) =>
    user.permissions.includes(code),
  )

  let results: Awaited<ReturnType<typeof client.quality.results>> | null = null
  let refusal: string | null = null
  try {
    results = await client.quality.results(id, { include_comments: canSeeComments })
  } catch (error) {
    if (error instanceof ApiError) {
      refusal = error.message
    } else {
      throw error
    }
  }

  const dimensions = Object.entries(results?.dimensions ?? {})
  const questions = Object.entries(results?.questions ?? {})

  return (
    <QualityShell user={user} institution={institution} currentPath="/evaluations">
      <PageHeader
        icon={<Icons.MessagesSquare />}
        title="Evaluation results"
        description="The aggregate, and never the individual returns. Comments are released on a stricter rule than the scores, because a comment can identify its author by content alone."
        breadcrumbs={
          <nav aria-label="Breadcrumb" className="text-muted-foreground text-xs">
            <Link href="/evaluations" className="hover:text-foreground underline">
              Course evaluations
            </Link>
            <span aria-hidden> / </span>
            <span>Results</span>
          </nav>
        }
      />

      {refusal ? (
        <EmptyState
          icon={<Icons.EyeOff />}
          title="Nothing to show"
          reason={
            <>
              {refusal}
              <span className="mt-2 block text-xs">
                {threshold.reason ||
                  `Below ${threshold.minimum_responses} responses a breakdown identifies the respondents.`}
              </span>
            </>
          }
        />
      ) : (
        <>
          <StatRow>
            <StatTile
              label="Responses"
              value={number(results?.responses ?? 0)}
              footnote={`of ${number(results?.invited ?? 0)} invited`}
              icon={<Icons.MessageSquare />}
            />
            <StatTile
              label="Response rate"
              value={
                results?.response_rate !== null && results?.response_rate !== undefined
                  ? `${results.response_rate.toFixed(0)}%`
                  : "—"
              }
              footnote="About a third is what an institution gets without chasing"
              icon={<Icons.Percent />}
            />
            <StatTile
              label="Overall"
              value={
                results?.overall !== null && results?.overall !== undefined
                  ? results.overall.toFixed(2)
                  : "—"
              }
              unit="/ 5"
              footnote="Mean across every scored question"
              icon={<Icons.Star />}
              emphasis
            />
            <StatTile
              label="Threshold"
              value={number(results?.reporting_threshold ?? threshold.minimum_responses)}
              footnote="Minimum responses before any breakdown"
              icon={<Icons.ShieldCheck />}
            />
          </StatRow>

          <div className="grid gap-6 lg:grid-cols-2">
            <ChartFrame
              title="By dimension"
              subtitle="Nobody acts on a single question's mean; the dimensions are what a department discusses."
            >
              <BarRows
                rows={dimensions.map(([name, value]) => ({ label: name, value }))}
                max={5}
                formatValue={(value) => value.toFixed(2)}
              />
            </ChartFrame>

            <ChartFrame
              title="By question"
              subtitle="The lowest one is where the conversation starts."
            >
              <BarRows
                rows={questions
                  .sort((a, b) => a[1] - b[1])
                  .map(([code, value]) => ({ label: code, value }))}
                max={5}
                slot={3}
                formatValue={(value) => value.toFixed(2)}
              />
            </ChartFrame>
          </div>

          {results?.comments && results.comments.length > 0 ? (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold">
                What the students wrote
                <span className="text-muted-foreground ml-2 text-xs font-normal">
                  Released to the department, never published
                </span>
              </h2>
              <ul className="space-y-2">
                {results.comments
                  .filter((comment): comment is string => Boolean(comment))
                  .map((comment, index) => (
                    <li key={index} className="bg-card shadow-card rounded-md px-3 py-2 text-sm">
                      {comment}
                    </li>
                  ))}
              </ul>
            </section>
          ) : null}
        </>
      )}
    </QualityShell>
  )
}
