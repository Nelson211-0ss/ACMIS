import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame, Meter } from "@acmis/ui/components/chart-frame"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge } from "@acmis/ui/components/status-badge"
import { number } from "@acmis/ui/lib/format"

import { QualityShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * The quality dashboard.
 *
 * Leads with indicators below target and open audit findings, because those
 * are the two things on this screen that somebody has undertaken to fix by a
 * date. Everything else here is a measurement; those are commitments.
 */
export default async function QualityOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, currentSemester, belowTarget, openAudits, indicators] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
    client.quality.indicators({ below_target_only: true, limit: 20 }).catch(() => null),
    client.quality.audits({ open_findings_only: true, limit: 20 }).catch(() => null),
    client.quality.indicators({ limit: 50 }).catch(() => null),
  ])

  const delivery = currentSemester
    ? await client.quality.delivery(currentSemester.id).catch(() => null)
    : null

  const deliveryRate =
    delivery && delivery.sessions_held + delivery.unannounced_absences > 0
      ? (delivery.sessions_held / (delivery.sessions_held + delivery.unannounced_absences)) * 100
      : null

  const openFindings = (openAudits?.items ?? []).reduce(
    (sum, audit) => sum + audit.open_findings,
    0,
  )

  const latest = new Map<string, { name: string; value: number; target: number | null }>()
  for (const row of indicators?.items ?? []) {
    if (!latest.has(row.code)) {
      latest.set(row.code, { name: row.name, value: row.value, target: row.target })
    }
  }

  return (
    <QualityShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.BadgeCheck />}
        title="Quality assurance"
        description="One question in four ways: is the teaching that was promised actually happening, and is it any good? Evaluation responses carry no identity at all — a student who thinks their lecturer can work out who wrote a comment does not write one."
      />

      {delivery && delivery.unannounced_absences > 0 ? (
        <section
          role="alert"
          className="border-destructive/40 bg-destructive/10 rounded-lg border p-4"
        >
          <h2 className="text-destructive flex items-center gap-2 text-sm font-semibold">
            <Icons.CalendarX className="size-4" aria-hidden />
            {delivery.unannounced_absences} class
            {delivery.unannounced_absences === 1 ? "" : "es"} did not happen and were not announced
          </h2>
          <p className="text-muted-foreground mt-2 text-xs">
            An announced cancellation is a decision. A class that simply did not happen is a
            delivery failure, and it is invisible in any system that records both as “cancelled”.
          </p>
          <a href="/delivery" className="text-primary mt-2 inline-block text-sm underline">
            Which courses →
          </a>
        </section>
      ) : null}

      <StatRow>
        <StatTile
          label="Teaching delivered"
          value={deliveryRate !== null ? `${deliveryRate.toFixed(1)}%` : "—"}
          footnote={delivery ? `${number(delivery.sessions_held)} sessions held` : "No semester"}
          icon={<Icons.CalendarCheck />}
        />
        <StatTile
          label="Indicators below target"
          value={number(belowTarget?.items.length ?? 0)}
          footnote="Measured against the stated target"
          icon={<Icons.TrendingDown />}
          emphasis={(belowTarget?.items.length ?? 0) > 0}
        />
        <StatTile
          label="Open findings"
          value={number(openFindings)}
          footnote={`Across ${number(openAudits?.items.length ?? 0)} audit(s)`}
          icon={<Icons.ClipboardList />}
        />
        <StatTile
          label="Sessions planned"
          value={number(delivery?.sessions_planned ?? 0)}
          footnote="This semester"
          icon={<Icons.CalendarRange />}
        />
      </StatRow>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartFrame
          title="Indicators against target"
          subtitle="The target is stored beside each value, so a historical breach stays a breach after the target moves."
        >
          <div className="space-y-3">
            {[...latest.values()].slice(0, 6).map((row) => (
              <Meter
                key={row.name}
                label={row.name}
                value={row.value}
                max={Math.max(row.value, row.target ?? row.value, 100)}
                threshold={row.target ?? undefined}
                thresholdLabel="target"
                formatValue={(v) => v.toFixed(1)}
              />
            ))}
            {latest.size === 0 ? (
              <p className="text-muted-foreground text-sm">No indicators computed yet.</p>
            ) : null}
          </div>
        </ChartFrame>

        <ChartFrame
          title="Worst delivery this semester"
          subtitle="Ordered by the proportion of elapsed classes actually held."
        >
          <BarRows
            rows={(delivery?.offerings ?? [])
              .filter((row) => row.delivery_percent !== null)
              .slice(0, 6)
              .map((row) => ({
                label: row.course_offering_id.slice(0, 8),
                value: row.delivery_percent ?? 0,
                hint: `${row.held} of ${row.held + row.cancelled + row.not_held}`,
              }))}
            max={100}
            formatValue={(value) => `${value.toFixed(0)}%`}
          />
        </ChartFrame>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Findings still open</h2>
        <ul className="divide-border divide-y text-sm">
          {(openAudits?.items ?? []).slice(0, 5).flatMap((audit) =>
            (audit.findings as Array<Record<string, unknown>>)
              .filter((finding) => (finding.status ?? "open") === "open")
              .slice(0, 3)
              .map((finding, index) => (
                <li
                  key={`${audit.id}-${String(finding.code ?? index)}`}
                  className="flex items-start justify-between gap-4 py-2"
                >
                  <span>
                    <span className="text-muted-foreground font-mono text-xs">
                      {audit.reference}/{String(finding.code ?? "")}
                    </span>{" "}
                    {String(finding.finding ?? "")}
                  </span>
                  <StatusBadge
                    tone={finding.severity === "major" ? "danger" : "warning"}
                    dot={false}
                  >
                    {String(finding.severity ?? "finding")}
                  </StatusBadge>
                </li>
              )),
          )}
          {openFindings === 0 ? (
            <li className="text-muted-foreground py-2">Nothing outstanding.</li>
          ) : null}
        </ul>
      </section>
    </QualityShell>
  )
}
