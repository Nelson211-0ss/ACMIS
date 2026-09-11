import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame, Meter } from "@acmis/ui/components/chart-frame"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { date, humaniseStatus, number, percent } from "@acmis/ui/lib/format"

import { PeopleShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * The HR dashboard, in academic terms.
 *
 * The doctorate proportion and contract expiries lead, because those two are
 * what an accreditation visit asks about and what nobody notices until it is
 * late. A general HRIS dashboard would lead with headcount, which no
 * accreditation body has ever asked for.
 */
export default async function PeopleOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester, staff] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
    client.people.list({ limit: 200 }).catch(() => null),
  ])

  const items = staff?.items ?? []
  const academic = items.filter((s) => s.category === "academic")
  const doctorates = academic.filter((s) => s.has_doctorate)

  const soon = new Date()
  soon.setMonth(soon.getMonth() + 3)
  const expiring = items
    .filter(
      (s) =>
        s.contract_ends_on !== null &&
        new Date(s.contract_ends_on) <= soon &&
        s.status === "active",
    )
    .sort((a, b) => (a.contract_ends_on ?? "").localeCompare(b.contract_ends_on ?? ""))

  const byCategory = new Map<string, number>()
  for (const person of items) {
    byCategory.set(person.category, (byCategory.get(person.category) ?? 0) + 1)
  }

  const workload = semester ? await client.people.workload(semester.id).catch(() => []) : []
  const overNorm = workload.filter((row) => {
    const total = Number(row.total_load_hours ?? 0)
    const norm = row.norm_hours === null ? null : Number(row.norm_hours ?? 0)
    return norm !== null && total > norm
  })

  return (
    <PeopleShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.Briefcase />}
        title="Faculty &amp; staff"
        description="Salary is visible to payroll and to the individual, and to nobody else — not deans, not heads of department, not the registry. Where a figure is missing from a list, that is why."
      />

      {expiring.length > 0 ? (
        <section className="border-warning/40 bg-warning/10 rounded-lg border p-4">
          <h2 className="text-warning-foreground flex items-center gap-2 text-sm font-semibold">
            <Icons.CalendarClock className="size-4" aria-hidden />
            {expiring.length} contract{expiring.length === 1 ? "" : "s"} ending within three months
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            A lapsed contract revokes mark-entry authority, because that follows the teaching
            allocation and the allocation ends with the contract. A part-time lecturer mid-marking
            is the case to watch.
          </p>
          <ul className="mt-3 space-y-1.5">
            {expiring.slice(0, 8).map((person) => (
              <li
                key={person.id}
                className="flex flex-wrap items-baseline justify-between gap-2 text-sm"
              >
                <span>
                  {person.surname}, {person.given_names}
                  <span className="text-muted-foreground ml-2 text-xs">
                    {humaniseStatus(person.category)}
                    {person.rank ? ` · ${person.rank}` : ""}
                  </span>
                </span>
                <span className="text-warning-foreground text-xs font-medium">
                  ends {date(person.contract_ends_on, institution?.locale)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <StatRow>
        <StatTile
          label="Staff"
          value={number(items.length)}
          emphasis
          icon={<Icons.Users className="size-4" />}
        />
        <StatTile
          label="Academic staff"
          value={number(academic.length)}
          icon={<Icons.GraduationCap className="size-4" />}
          footnote="Counted by accreditation returns"
        />
        <StatTile
          label="With a doctorate"
          value={
            academic.length > 0
              ? percent((doctorates.length / academic.length) * 100, institution?.locale, 0)
              : "—"
          }
          icon={<Icons.Award className="size-4" />}
          footnote={`${number(doctorates.length)} of ${number(academic.length)} academic staff`}
        />
        <StatTile
          label="Over workload norm"
          value={number(overNorm.length)}
          icon={<Icons.Gauge className="size-4" />}
          footnote="Teaching above the norm for their rank"
          deltaIsGood={false}
        />
      </StatRow>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame
          title="Staff by category"
          subtitle="Academic, academic support, administrative and part-time are counted separately because accreditation returns count only academic staff."
          series={[{ key: "staff", label: "Staff", slot: 1 }]}
          table={
            <table className="tabular w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                    Category
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Staff
                  </th>
                </tr>
              </thead>
              <tbody>
                {[...byCategory.entries()].map(([category, count]) => (
                  <tr key={category} className="border-b last:border-0">
                    <td className="py-1.5 pr-3">{humaniseStatus(category)}</td>
                    <td className="py-1.5 text-right">{number(count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          {byCategory.size > 0 ? (
            <BarRows
              rows={[...byCategory.entries()]
                .sort(([, a], [, b]) => b - a)
                .map(([category, count]) => ({
                  label: humaniseStatus(category),
                  value: count,
                }))}
              formatValue={(v) => number(v)}
            />
          ) : (
            <p className="text-muted-foreground py-6 text-center text-sm">
              No staff records within your reach.
            </p>
          )}
        </ChartFrame>

        <div className="bg-card shadow-card space-y-4 rounded-lg p-4">
          <div>
            <h3 className="text-base font-semibold">Doctorate proportion</h3>
            <p className="text-muted-foreground mt-1 text-sm">
              A headline accreditation metric, which is why it is a queryable column rather than
              something derived from qualification rows.
            </p>
          </div>
          <Meter
            label="Academic staff holding a doctorate"
            value={doctorates.length}
            max={academic.length || 1}
            formatValue={(v) => number(v)}
            threshold={Math.round((academic.length || 1) * 0.5)}
            thresholdLabel="Many regulators expect at least half of academic staff to hold a doctorate; the line is the institution's own target."
          />
          <p className="text-muted-foreground border-t pt-3 text-xs leading-relaxed">
            Counted from verified qualifications only. An unverified doctorate on an accreditation
            return is the kind of finding that suspends a programme, so the verification step is not
            paperwork for its own sake.
          </p>
        </div>
      </div>
    </PeopleShell>
  )
}
