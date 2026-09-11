import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame, StackedBar } from "@acmis/ui/components/chart-frame"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, number, percent } from "@acmis/ui/lib/format"

import { AdmissionsShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

export default async function AdmissionsOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, schemes] = await Promise.all([
    client.public.institution().catch(() => null),
    client.admissions.schemes({ limit: 5, status: "open" }).catch(() => null),
  ])

  const openScheme = schemes?.items[0] ?? null
  const stats = openScheme
    ? await client.admissions.schemeStatistics(openScheme.id).catch(() => null)
    : null

  const byStatus = stats?.by_status ?? {}
  const total = stats?.total ?? 0
  const admitted = byStatus.admitted ?? 0
  const underReview = (byStatus.under_review ?? 0) + (byStatus.submitted ?? 0)
  const awaitingFee = byStatus.awaiting_fee ?? 0

  return (
    <AdmissionsShell
      user={user}
      institution={institution}
      currentPath="/"
      counts={{ review: underReview, awaitingFee }}
    >
      <PageHeader
        icon={<Icons.UserPlus />}
        title="Admissions"
        description={
          openScheme
            ? `${openScheme.name} closes ${date(openScheme.closes_at, institution?.locale)}. Applications become visible to selectors once the application fee settles.`
            : "No admission scheme is currently open. Publish one to start accepting applications."
        }
      />

      {openScheme ? (
        <>
          <StatRow>
            <StatTile
              label="Applications"
              value={number(total)}
              emphasis
              icon={<Icons.FileText className="size-4" />}
              footnote={`Under ${openScheme.code}`}
            />
            <StatTile
              label="Awaiting review"
              value={number(underReview)}
              icon={<Icons.Clock className="size-4" />}
              footnote="Fee settled, ready for a selector"
            />
            <StatTile
              label="Awaiting fee"
              value={number(awaitingFee)}
              icon={<Icons.Wallet className="size-4" />}
              footnote="Submitted but not yet payable"
            />
            <StatTile
              label="Admitted"
              value={number(admitted)}
              icon={<Icons.UserCheck className="size-4" />}
              footnote={
                total > 0 ? `${percent((admitted / total) * 100)} of applications` : undefined
              }
            />
          </StatRow>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartFrame
              title="Where applications stand"
              subtitle={`All ${number(total)} applications under ${openScheme.code}, by status.`}
              series={[{ key: "count", label: "Applications", slot: 1 }]}
              table={
                <table className="tabular w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                        Status
                      </th>
                      <th scope="col" className="py-1.5 text-right font-medium">
                        Applications
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(byStatus).map(([status, count]) => (
                      <tr key={status} className="border-b last:border-0">
                        <td className="py-1.5 pr-3">{humaniseStatus(status)}</td>
                        <td className="py-1.5 text-right">{number(count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              }
            >
              {Object.keys(byStatus).length > 0 ? (
                <BarRows
                  rows={Object.entries(byStatus)
                    .sort(([, a], [, b]) => b - a)
                    .map(([status, count]) => ({
                      label: humaniseStatus(status),
                      value: count,
                    }))}
                  formatValue={(v) => number(v)}
                />
              ) : (
                <p className="text-muted-foreground py-6 text-center text-sm">
                  No applications yet.
                </p>
              )}
            </ChartFrame>

            <ChartFrame
              title="Competition by programme"
              subtitle="Applications received per approved seat. Above 1.0 means the programme is oversubscribed."
              series={[{ key: "ratio", label: "Applications per seat", slot: 2 }]}
              footnote="Seats are the figure the academic board approved, not the number offered — institutions over-offer for expected declines."
              table={
                <table className="tabular w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                        Programme
                      </th>
                      <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                        Seats
                      </th>
                      <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                        Applications
                      </th>
                      <th scope="col" className="py-1.5 text-right font-medium">
                        Per seat
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(stats?.intakes ?? []).map((intake) => (
                      <tr key={intake.programme_intake_id} className="border-b last:border-0">
                        <td className="py-1.5 pr-3 font-mono text-xs">
                          {intake.programme_id.slice(0, 8)}
                        </td>
                        <td className="py-1.5 pr-3 text-right">{number(intake.approved_intake)}</td>
                        <td className="py-1.5 pr-3 text-right">
                          {number(intake.applications_received)}
                        </td>
                        <td className="py-1.5 text-right">{intake.competition_ratio ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              }
            >
              {(stats?.intakes ?? []).length > 0 ? (
                <BarRows
                  slot={2}
                  rows={(stats?.intakes ?? [])
                    .filter((i) => i.competition_ratio !== null)
                    .sort((a, b) => (b.competition_ratio ?? 0) - (a.competition_ratio ?? 0))
                    .slice(0, 8)
                    .map((intake) => ({
                      label: intake.programme_id.slice(0, 8),
                      value: intake.competition_ratio ?? 0,
                      hint: `${number(intake.applications_received)} applications for ${number(intake.approved_intake)} seats`,
                    }))}
                  formatValue={(v) => v.toFixed(2)}
                />
              ) : (
                <p className="text-muted-foreground py-6 text-center text-sm">
                  No programme intakes configured for this scheme.
                </p>
              )}
            </ChartFrame>
          </div>

          <div className="bg-card shadow-card rounded-lg p-4">
            <h3 className="text-base font-semibold">Intake fill</h3>
            <p className="text-muted-foreground mt-1 text-sm">
              Offers issued, accepted and enrolled against approved seats, per programme.
            </p>
            <div className="mt-4 space-y-4">
              {(stats?.intakes ?? []).slice(0, 6).map((intake) => (
                <div key={intake.programme_intake_id}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-2">
                    <span className="font-mono text-xs">{intake.programme_id.slice(0, 8)}</span>
                    <span className="text-muted-foreground tabular text-xs">
                      {number(intake.enrolled)} enrolled of {number(intake.approved_intake)} seats
                    </span>
                  </div>
                  <StackedBar
                    segments={[
                      { label: "Enrolled", value: intake.enrolled, slot: 6 },
                      {
                        label: "Accepted, not enrolled",
                        value: Math.max(0, intake.offers_accepted - intake.enrolled),
                        slot: 2,
                      },
                      {
                        label: "Offered, no response",
                        value: Math.max(0, intake.offers_issued - intake.offers_accepted),
                        slot: 4,
                      },
                      {
                        label: "Seats unfilled",
                        value: Math.max(0, intake.approved_intake - intake.offers_issued),
                        slot: 8,
                      },
                    ]}
                    formatValue={(v) => number(v)}
                  />
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <EmptyState
          title="No open admission scheme"
          reason="Applicants can only apply under a published scheme. Create one, add its programme intakes, then publish it — publishing is what makes its fee and deadline a commitment."
          icon={<Icons.CalendarRange className="size-8" />}
        />
      )}

      {schemes && schemes.items.length > 0 ? (
        <div>
          <h3 className="text-base font-semibold">Open schemes</h3>
          <ul className="mt-3 space-y-2">
            {schemes.items.map((scheme) => (
              <li
                key={scheme.id}
                className="bg-card shadow-card flex flex-wrap items-center justify-between gap-3 rounded-lg p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{scheme.name}</p>
                  <p className="text-muted-foreground text-xs">
                    {scheme.code} · {humaniseStatus(scheme.entry_scheme)} · closes{" "}
                    {date(scheme.closes_at, institution?.locale)}
                  </p>
                </div>
                <StatusBadge tone={toneForStatus(scheme.status)}>
                  {humaniseStatus(scheme.status)}
                </StatusBadge>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </AdmissionsShell>
  )
}
