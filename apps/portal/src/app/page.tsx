import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { Meter } from "@acmis/ui/components/chart-frame"
import { PageHeader } from "@acmis/ui/components/page-header"
import { date, dateTime, humaniseStatus, money, number } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * A student's landing page.
 *
 * Ordered by what actually blocks them: a hold or a fee threshold stops
 * registration, registration stops examination, and everything else is
 * information. A dashboard that leads with a welcome message and buries the
 * blocker is the reason students queue at the registry.
 */
export default async function PortalHome() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester, record, statement, attempts] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
    client.students.myRecord().catch(() => null),
    client.finance.myStatement().catch(() => null),
    client.learning.myAttempts().catch(() => []),
  ])

  const student = record?.data
  const primary = student?.programmes.find((p) => p.is_primary)
  const holds = (student?.holds ?? []).filter((h) => !h.cleared_at)
  const live = attempts.filter((a) => a.status === "in_progress")

  return (
    <PortalShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.Home />}
        title={`Hello, ${student?.given_names?.split(" ")[0] ?? user.display_name}`}
        description={
          semester
            ? `${semester.name}${
                semester.registration_closes_on
                  ? ` · registration closes ${date(semester.registration_closes_on, institution?.locale)}`
                  : ""
              }`
            : undefined
        }
      />

      {/* An examination in progress outranks everything else on the page. */}
      {live.length > 0 ? (
        <section className="border-module/50 bg-module/5 rounded-lg border p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Icons.Timer className="text-module size-4" aria-hidden />
            You have {live.length} paper{live.length === 1 ? "" : "s"} in progress
          </h2>
          <ul className="mt-3 space-y-2">
            {live.map((attempt) => (
              <li
                key={attempt.id}
                className="bg-card shadow-card flex flex-wrap items-center justify-between gap-3 rounded-md p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{attempt.assessment_title}</p>
                  {attempt.expires_at ? (
                    <p className="text-muted-foreground text-xs">
                      Closes{" "}
                      {dateTime(attempt.expires_at, institution?.locale, institution?.timezone)}
                    </p>
                  ) : null}
                </div>
                <a
                  href={`/sit/${attempt.id}`}
                  className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 shrink-0 rounded-md px-4 py-2.5 text-sm font-semibold"
                >
                  Resume
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {holds.length > 0 ? (
        <section className="border-warning/40 bg-warning/10 rounded-lg border p-4">
          <h2 className="text-warning-foreground flex items-center gap-2 text-sm font-semibold">
            <Icons.Lock className="size-4" aria-hidden />
            {holds.length} hold{holds.length === 1 ? "" : "s"} on your record
          </h2>
          <ul className="mt-2 space-y-1.5">
            {holds.map((hold, index) => (
              <li key={index} className="text-sm">
                <span className="font-medium capitalize">{hold.kind.replace(/_/g, " ")}</span>
                {" — "}
                {hold.reason}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-2 text-xs">
            Each hold is cleared by the office that placed it. Visit that office rather than the
            registry.
          </p>
        </section>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {primary ? (
          <section className="bg-card shadow-card space-y-3 rounded-lg p-4">
            <h2 className="text-base font-semibold">Your programme</h2>
            <div className="flex items-baseline gap-2">
              <span className="tabular text-3xl font-semibold">
                {primary.cgpa !== null ? primary.cgpa.toFixed(2) : "—"}
              </span>
              <span className="text-muted-foreground text-sm">CGPA</span>
            </div>
            <Meter
              label="Credit units earned"
              value={primary.credits_earned}
              max={primary.credits_required || 1}
              formatValue={(v) => number(v)}
            />
            <dl className="space-y-1.5 border-t pt-2 text-xs">
              <Row
                label="Year"
                value={`${primary.current_year_of_study}, semester ${primary.current_semester_number}`}
              />
              <Row label="Standing" value={humaniseStatus(primary.progression_status)} />
              {primary.outstanding_retakes > 0 ? (
                <Row label="Retakes outstanding" value={String(primary.outstanding_retakes)} />
              ) : null}
            </dl>
          </section>
        ) : null}

        {statement ? (
          <section className="bg-card shadow-card space-y-3 rounded-lg p-4">
            <h2 className="text-base font-semibold">Your fees</h2>
            <div className="flex items-baseline gap-2">
              <span
                className={
                  statement.balance_minor > 0
                    ? "text-destructive tabular text-2xl font-semibold"
                    : "text-success tabular text-2xl font-semibold"
                }
              >
                {money(statement.balance_minor, statement.currency, institution?.locale)}
              </span>
              <span className="text-muted-foreground text-xs">
                {statement.balance_minor > 0 ? "outstanding" : "cleared"}
              </span>
            </div>
            <dl className="space-y-1.5 text-xs">
              <Row
                label="Invoiced"
                value={money(
                  statement.total_invoiced_minor,
                  statement.currency,
                  institution?.locale,
                )}
              />
              <Row
                label="Paid"
                value={money(statement.total_paid_minor, statement.currency, institution?.locale)}
              />
            </dl>
            <a href="/fees" className="text-module inline-block pt-1 text-xs font-medium underline">
              See your statement
            </a>
          </section>
        ) : null}

        <section className="bg-card shadow-card space-y-3 rounded-lg p-4">
          <h2 className="text-base font-semibold">Recent tests</h2>
          {attempts.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              Nothing yet. Tests appear here once your lecturers open them.
            </p>
          ) : (
            <ul className="space-y-2">
              {attempts.slice(0, 4).map((attempt) => (
                <li key={attempt.id} className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm">{attempt.assessment_title}</p>
                    <p className="text-muted-foreground text-xs">
                      {humaniseStatus(attempt.status)}
                    </p>
                  </div>
                  <span className="tabular shrink-0 text-sm font-medium">
                    {attempt.score_visible && attempt.percentage !== null
                      ? `${attempt.percentage.toFixed(0)}%`
                      : // A sealed score and a null score are different
                        // facts, and the label says which.
                        "sealed"}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <a
            href="/assessments"
            className="text-module inline-block pt-1 text-xs font-medium underline"
          >
            All tests &amp; assignments
          </a>
        </section>
      </div>
    </PortalShell>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="tabular font-medium">{value}</dd>
    </div>
  )
}
