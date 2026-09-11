import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame, Meter } from "@acmis/ui/components/chart-frame"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { date, number, percent } from "@acmis/ui/lib/format"

import { StudentsShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * The registry's dashboard.
 *
 * Counts by status, because that is the number the registrar is asked for
 * daily and the one the statutory return needs. Note that "enrolled" and
 * "registered" are counted separately — a student can be enrolled for the
 * semester and blocked on a fee for course registration, and conflating the
 * two is how an institution reports a number it cannot defend.
 */
export default async function StudentsOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester, active, probation, onLeave, completed] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
    client.students.list({ status: "active", limit: 1, with_total: true }),
    client.students.list({ status: "probation", limit: 1, with_total: true }),
    client.students.list({ status: "on_leave", limit: 1, with_total: true }),
    client.students.list({ status: "completed", limit: 1, with_total: true }),
  ])

  const counts = {
    active: active.meta.total ?? 0,
    probation: probation.meta.total ?? 0,
    onLeave: onLeave.meta.total ?? 0,
    completed: completed.meta.total ?? 0,
  }
  const enrolled = counts.active + counts.probation

  // A sample of the active population, to show the year distribution without
  // asking the API for an aggregate endpoint it does not have. Explicitly a
  // sample, and labelled as one — a chart that looks like a census and is not
  // is worse than no chart.
  const sample = await client.students.list({ status: "active", limit: 200 })
  const byYear = new Map<number, number>()
  for (const student of sample.items) {
    const primary = student.programmes.find((p) => p.is_primary)
    if (!primary) continue
    byYear.set(primary.current_year_of_study, (byYear.get(primary.current_year_of_study) ?? 0) + 1)
  }

  return (
    <StudentsShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.Users />}
        title="Student records"
        description={
          semester
            ? `${semester.name}. Registration ${
                semester.registration_closes_on
                  ? `closes ${date(semester.registration_closes_on, institution?.locale)}`
                  : "window not set"
              }.`
            : "No current semester is set. Most life-cycle actions need one."
        }
      />

      <StatRow>
        <StatTile
          label="Enrolled"
          value={number(enrolled)}
          emphasis
          icon={<Icons.Users className="size-4" />}
          footnote="Active and on probation. This is the enrolment figure a statutory return counts."
        />
        <StatTile
          label="On probation"
          value={number(counts.probation)}
          icon={<Icons.AlertTriangle className="size-4" />}
          footnote={
            enrolled > 0 ? `${percent((counts.probation / enrolled) * 100)} of enrolled` : undefined
          }
        />
        <StatTile
          label="On approved leave"
          value={number(counts.onLeave)}
          icon={<Icons.PauseCircle className="size-4" />}
          footnote="Progression clock stopped"
        />
        <StatTile
          label="Awaiting conferment"
          value={number(counts.completed)}
          icon={<Icons.GraduationCap className="size-4" />}
          footnote="Coursework done, award not yet conferred"
        />
      </StatRow>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame
          title="Year of study"
          subtitle={`From a sample of ${number(sample.items.length)} active students — not a census.`}
          series={[{ key: "students", label: "Students", slot: 1 }]}
          footnote="A shape that narrows sharply between years one and two usually means attrition rather than a small intake; the progression report separates them."
          table={
            <table className="tabular w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                    Year
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Students
                  </th>
                </tr>
              </thead>
              <tbody>
                {[...byYear.entries()]
                  .sort(([a], [b]) => a - b)
                  .map(([year, count]) => (
                    <tr key={year} className="border-b last:border-0">
                      <td className="py-1.5 pr-3">Year {year}</td>
                      <td className="py-1.5 text-right">{number(count)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          }
        >
          {byYear.size > 0 ? (
            <BarRows
              rows={[...byYear.entries()]
                .sort(([a], [b]) => a - b)
                .map(([year, count]) => ({ label: `Year ${year}`, value: count }))}
              formatValue={(v) => number(v)}
            />
          ) : (
            <p className="text-muted-foreground py-6 text-center text-sm">
              No active students with a programme attachment.
            </p>
          )}
        </ChartFrame>

        <div className="bg-card shadow-card space-y-4 rounded-lg p-4">
          <div>
            <h3 className="text-base font-semibold">Population standing</h3>
            <p className="text-muted-foreground mt-1 text-sm">
              Proportion of the enrolled population in each academic standing.
            </p>
          </div>
          <Meter
            label="Normal progress"
            value={counts.active}
            max={enrolled || 1}
            tone="success"
            formatValue={(v) => number(v)}
          />
          <Meter
            label="Probation"
            value={counts.probation}
            max={enrolled || 1}
            tone="warning"
            formatValue={(v) => number(v)}
            threshold={Math.round((enrolled || 1) * 0.1)}
            thresholdLabel="A probation rate above about 10% is usually a question about a programme rather than about its students."
          />
          <p className="text-muted-foreground border-t pt-3 text-xs leading-relaxed">
            Standing is computed from the progression rules on each student&rsquo;s own curriculum
            version, and the rules used are stamped onto every computed result. A student put on
            probation in 2027 stays explainable under the 2027 rules.
          </p>
        </div>
      </div>
    </StudentsShell>
  )
}
