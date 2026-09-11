import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { dateTime, humaniseStatus, number } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Tests & assignments" }

/**
 * A student's tests, past and present.
 *
 * The distinction the page works hardest to make clear is between a score
 * that is not yet visible and a score of zero. The API returns
 * `score_visible` for exactly this: a sealed result says "sealed", never a
 * dash that reads as nothing earned.
 */
export default async function AssessmentsPage({
  searchParams,
}: {
  searchParams: Promise<{ submitted?: string }>
}) {
  const { submitted } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, attempts] = await Promise.all([
    client.public.institution().catch(() => null),
    client.learning.myAttempts().catch(() => []),
  ])

  const live = attempts.filter((a) => a.status === "in_progress")
  const finished = attempts.filter((a) => a.status !== "in_progress")

  return (
    <PortalShell user={user} institution={institution} currentPath="/assessments">
      <PageHeader
        icon={<Icons.FileQuestion />}
        title="Tests &amp; assignments"
        description="Papers open to you, and everything you have sat. A score appears once your lecturer releases it — before that it is provisional and may still be moderated."
      />

      {submitted ? (
        <p
          role="status"
          className="border-success/40 bg-success/10 text-success rounded-lg border px-4 py-3 text-sm font-medium"
        >
          Your paper has been submitted. Nothing further is needed.
        </p>
      ) : null}

      {live.length > 0 ? (
        <section>
          <h2 className="text-lg font-semibold">In progress</h2>
          <ul className="mt-3 space-y-2">
            {live.map((attempt) => (
              <li
                key={attempt.id}
                className="border-module/50 bg-module/5 flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4"
              >
                <div className="min-w-0">
                  <p className="font-medium">{attempt.assessment_title}</p>
                  <p className="text-muted-foreground text-xs">
                    Attempt {attempt.attempt_number} · {number(attempt.total_marks)} marks
                    {attempt.expires_at
                      ? ` · closes ${dateTime(attempt.expires_at, institution?.locale, institution?.timezone)}`
                      : ""}
                  </p>
                </div>
                <a
                  href={`/sit/${attempt.id}`}
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 w-full shrink-0 rounded-md px-4 py-2.5 text-center text-sm font-semibold sm:w-auto"
                >
                  Resume paper
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <h2 className="text-lg font-semibold">Completed</h2>
        {finished.length === 0 ? (
          <div className="mt-3">
            <EmptyState
              title="You have not sat any tests yet"
              reason="Tests appear here when a lecturer opens one for a course you are registered for."
              icon={<Icons.FileQuestion className="size-8" />}
            />
          </div>
        ) : (
          <ul className="mt-3 space-y-2">
            {finished.map((attempt) => (
              <li
                key={attempt.id}
                className="bg-card shadow-card flex flex-wrap items-center justify-between gap-3 rounded-lg p-4"
              >
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{attempt.assessment_title}</p>
                  <p className="text-muted-foreground text-xs">
                    {humaniseStatus(attempt.assessment_kind)} · attempt {attempt.attempt_number}
                    {attempt.submitted_at
                      ? ` · submitted ${dateTime(attempt.submitted_at, institution?.locale, institution?.timezone)}`
                      : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <StatusBadge tone={toneForStatus(attempt.status)}>
                    {humaniseStatus(attempt.status)}
                  </StatusBadge>
                  {attempt.score_visible && attempt.total_score !== null ? (
                    <span className="tabular text-right">
                      <span className="text-lg font-semibold">
                        {attempt.total_score.toFixed(1)}
                      </span>
                      <span className="text-muted-foreground text-xs">
                        {" "}
                        / {number(attempt.total_marks)}
                      </span>
                    </span>
                  ) : (
                    <span
                      className="text-muted-foreground text-xs"
                      title="Your lecturer has not released this score yet. It may still be moderated."
                    >
                      Not released
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </PortalShell>
  )
}
