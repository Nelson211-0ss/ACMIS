import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame } from "@acmis/ui/components/chart-frame"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, number } from "@acmis/ui/lib/format"

import { CurriculumShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * The curriculum dashboard.
 *
 * Leads with accreditation expiry, which is the one thing on this screen that
 * can invalidate an award. Admitting onto a programme whose accreditation has
 * lapsed produces degrees the regulator does not recognise, and the date is
 * easy to miss because nothing else changes when it passes.
 */
export default async function CurriculumOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, programmes, courses, units] = await Promise.all([
    client.public.institution().catch(() => null),
    client.curriculum.programmes({ limit: 200, active_only: false }).catch(() => null),
    client.curriculum.courses({ limit: 1, with_total: true }).catch(() => null),
    client.reference.units().catch(() => []),
  ])

  const items = programmes?.items ?? []
  const byStatus = new Map<string, number>()
  for (const programme of items) {
    byStatus.set(programme.status, (byStatus.get(programme.status) ?? 0) + 1)
  }

  const soon = new Date()
  soon.setMonth(soon.getMonth() + 6)
  const expiring = items
    .filter(
      (p) =>
        p.accredited_until !== null && new Date(p.accredited_until) <= soon && p.is_active,
    )
    .sort((a, b) => (a.accredited_until ?? "").localeCompare(b.accredited_until ?? ""))

  const byLevel = new Map<string, number>()
  for (const programme of items) {
    byLevel.set(programme.award_level, (byLevel.get(programme.award_level) ?? 0) + 1)
  }

  return (
    <CurriculumShell user={user} institution={institution} currentPath="/">
      <PageHeader
        title="Curriculum"
        description="A programme is a stable identity; a curriculum version is its content, valid for the cohorts that entered while it was current. A student is attached to a version, which is what lets the 2024 cohort graduate under the 2024 rules."
      />

      {expiring.length > 0 ? (
        <section
          role="alert"
          className="border-destructive/40 bg-destructive/10 rounded-lg border p-4"
        >
          <h2 className="text-destructive flex items-center gap-2 text-sm font-semibold">
            <Icons.AlertTriangle className="size-4" aria-hidden />
            {expiring.length} programme{expiring.length === 1 ? "" : "s"} with
            accreditation expiring within six months
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Admitting onto a lapsed accreditation invalidates the award. Nothing
            else changes when the date passes, which is why it is the first thing
            on this page.
          </p>
          <ul className="mt-3 space-y-1.5">
            {expiring.map((programme) => (
              <li
                key={programme.id}
                className="flex flex-wrap items-baseline justify-between gap-2 text-sm"
              >
                <span>
                  <span className="font-mono text-xs">{programme.code}</span>{" "}
                  {programme.name}
                </span>
                <span className="text-destructive text-xs font-medium">
                  expires {date(programme.accredited_until, institution?.locale)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <StatRow>
        <StatTile
          label="Programmes"
          value={number(items.length)}
          emphasis
          icon={<Icons.BookOpen className="size-4" />}
          footnote={`${number(byStatus.get("approved") ?? 0)} Senate-approved`}
        />
        <StatTile
          label="Courses"
          value={number(courses?.meta.total ?? 0)}
          icon={<Icons.FileText className="size-4" />}
        />
        <StatTile
          label="Awaiting approval"
          value={number(
            (byStatus.get("submitted") ?? 0) + (byStatus.get("recommended") ?? 0),
          )}
          icon={<Icons.Stamp className="size-4" />}
          footnote="With a faculty board or Senate"
        />
        <StatTile
          label="Academic units"
          value={number(units.length)}
          icon={<Icons.Network className="size-4" />}
          footnote="Colleges, faculties, schools, departments"
        />
      </StatRow>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame
          title="Programmes by award level"
          subtitle={`All ${number(items.length)} programmes, whatever their approval status.`}
          series={[{ key: "programmes", label: "Programmes", slot: 1 }]}
          table={
            <table className="tabular w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                    Award level
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Programmes
                  </th>
                </tr>
              </thead>
              <tbody>
                {[...byLevel.entries()].map(([level, count]) => (
                  <tr key={level} className="border-b last:border-0">
                    <td className="py-1.5 pr-3">{humaniseStatus(level)}</td>
                    <td className="py-1.5 text-right">{number(count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          {byLevel.size > 0 ? (
            <BarRows
              rows={[...byLevel.entries()]
                .sort(([, a], [, b]) => b - a)
                .map(([level, count]) => ({
                  label: humaniseStatus(level),
                  value: count,
                }))}
              formatValue={(v) => number(v)}
            />
          ) : (
            <p className="text-muted-foreground py-6 text-center text-sm">
              No programmes yet.
            </p>
          )}
        </ChartFrame>

        <div className="bg-card rounded-lg border p-4">
          <h3 className="text-base font-semibold">Approval chain</h3>
          <p className="text-muted-foreground mt-1 text-sm">
            Drafted in the department, recommended by the faculty board,
            approved by Senate — three grants and three people. The submitter is
            refused at the approval step.
          </p>
          <ul className="mt-4 space-y-2">
            {(
              [
                ["draft", "Drafting in departments"],
                ["submitted", "With faculty boards"],
                ["recommended", "With Senate"],
                ["approved", "Approved"],
                ["returned", "Returned for revision"],
              ] as const
            ).map(([status, label]) => (
              <li
                key={status}
                className="flex items-center justify-between gap-2 border-b pb-2 last:border-0"
              >
                <span className="text-sm">{label}</span>
                <span className="flex items-center gap-2">
                  <span className="tabular text-sm font-medium">
                    {number(byStatus.get(status) ?? 0)}
                  </span>
                  <StatusBadge tone={toneForStatus(status)} dot={false}>
                    {humaniseStatus(status)}
                  </StatusBadge>
                </span>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-3 border-t pt-3 text-xs leading-relaxed">
            An approved version is frozen. Changing the credit weight of a
            course a cohort has already sat would retroactively change their
            CGPA, so a change is a new version with its own effective date —
            never an edit.
          </p>
        </div>
      </div>
    </CurriculumShell>
  )
}
