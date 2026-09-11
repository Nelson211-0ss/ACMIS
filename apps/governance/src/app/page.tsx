import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame } from "@acmis/ui/components/chart-frame"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge } from "@acmis/ui/components/status-badge"
import { number, relativeTime } from "@acmis/ui/lib/format"

import { GovernanceShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * The oversight dashboard.
 *
 * Built around denials rather than around activity, because that is where the
 * signal is. One denial is a mis-set role. Two hundred against different
 * students in ten minutes is somebody walking the record set, and the
 * difference is visible only when denials are grouped by actor *and* counted
 * by distinct resource — which is exactly what the API's denial summary
 * returns.
 */
export default async function GovernanceOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, denials, bundle, recent] = await Promise.all([
    client.public.institution().catch(() => null),
    client.governance.denialSummary(24).catch(() => null),
    client.authz.bundle(false).catch(() => null),
    client.governance.audit({ limit: 8, outcome: "denied" }).catch(() => null),
  ])

  const totalDenials = (denials?.by_actor ?? []).reduce((sum, a) => sum + a.denials, 0)
  const enumerating = (denials?.by_actor ?? []).filter((a) => a.looks_like_enumeration)
  const defaultDenies = (denials?.by_policy ?? []).filter((p) => p.policy === "(denied by default)")

  return (
    <GovernanceShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.ShieldCheck />}
        title="Governance &amp; audit"
        description="Reading the audit trail is itself audited. An audit log only its subjects can see is not oversight; one anyone can read is a directory of who has looked at whom."
      />

      <StatRow>
        <StatTile
          label="Denials, 24h"
          value={number(totalDenials)}
          emphasis
          icon={<Icons.ShieldAlert className="size-4" />}
          footnote="Every refused request is recorded, with the deciding rule"
          deltaIsGood={false}
        />
        <StatTile
          label="Possible enumeration"
          value={number(enumerating.length)}
          icon={<Icons.Search className="size-4" />}
          footnote="Actors denied across more than 20 distinct records"
          deltaIsGood={false}
        />
        <StatTile
          label="Policies loaded"
          value={number(bundle?.policy_count ?? 0)}
          icon={<Icons.Gavel className="size-4" />}
          footnote={`${number(bundle?.rule_count ?? 0)} rules · bundle ${bundle?.version ?? "—"}`}
        />
        <StatTile
          label="Bundle health"
          value={
            bundle?.lint && bundle.lint.length > 0
              ? `${bundle.lint.length} issue${bundle.lint.length === 1 ? "" : "s"}`
              : "Clean"
          }
          icon={<Icons.CheckCircle2 className="size-4" />}
          footnote="Static checks the bundle must pass to be served"
        />
      </StatRow>

      {defaultDenies.length > 0 ? (
        <section className="border-primary/30 bg-primary/5 rounded-lg border p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Icons.FileQuestion className="size-4" aria-hidden />
            {number(defaultDenies.reduce((sum, row) => sum + row.denials, 0))} denials with no
            applicable policy
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Nobody wrote a rule for these, so they were refused by default. Distinct from a rule
            that decided to refuse — which is a control working — this is a gap, and it is the most
            useful number on an access review: somebody is trying to do their job and the bundle has
            nothing to say about it.
          </p>
          <ul className="mt-3 space-y-1 text-sm">
            {defaultDenies.slice(0, 5).map((row) => (
              <li key={row.action} className="flex justify-between gap-4">
                <span className="text-muted-foreground font-mono text-xs">{row.action}</span>
                <strong className="tabular-nums">{number(row.denials)}</strong>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {enumerating.length > 0 ? (
        <section className="border-destructive/40 bg-destructive/10 rounded-lg border p-4">
          <h2 className="text-destructive flex items-center gap-2 text-sm font-semibold">
            <Icons.AlertTriangle className="size-4" aria-hidden />
            {enumerating.length} account
            {enumerating.length === 1 ? "" : "s"} showing an enumeration pattern
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Denied repeatedly across many different records in a short window. That shape is what
            distinguishes somebody probing from somebody confused.
          </p>
          <ul className="mt-3 space-y-2">
            {enumerating.map((actor) => (
              <li
                key={actor.actor_id ?? actor.actor_label ?? "unknown"}
                className="bg-card shadow-card flex flex-wrap items-center justify-between gap-3 rounded-md p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {actor.actor_label ?? "Unknown actor"}
                  </p>
                  <p className="text-muted-foreground font-mono text-xs">{actor.actor_id ?? "—"}</p>
                </div>
                <div className="flex shrink-0 items-center gap-3 text-xs">
                  <span>
                    <strong className="tabular">{number(actor.denials)}</strong> denials
                  </span>
                  <span>
                    <strong className="tabular">{number(actor.distinct_resources)}</strong> records
                  </span>
                  {actor.actor_id ? (
                    <a
                      href={`/audit?actor_id=${actor.actor_id}`}
                      className="text-module font-medium underline"
                    >
                      Trail
                    </a>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame
          title="What is being refused"
          subtitle="Denials in the last 24 hours, by the rule that refused them."
          series={[{ key: "denials", label: "Denials", slot: 3 }]}
          footnote="Denied-by-default means nothing was applicable, not that a rule said no — a different problem with a different fix. A pile of them usually means a missing role rather than an attack."
          table={
            <table className="tabular w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                    Policy
                  </th>
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                    Action
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Denials
                  </th>
                </tr>
              </thead>
              <tbody>
                {(denials?.by_policy ?? []).map((row) => (
                  <tr key={`${row.policy}-${row.action}`} className="border-b last:border-0">
                    <td className="py-1.5 pr-3 font-mono text-xs">{row.policy}</td>
                    <td className="py-1.5 pr-3 font-mono text-xs">{row.action}</td>
                    <td className="py-1.5 text-right">{number(row.denials)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          {(denials?.by_policy ?? []).length > 0 ? (
            <BarRows
              slot={3}
              rows={(denials?.by_policy ?? []).slice(0, 10).map((row) => ({
                label: row.action,
                value: row.denials,
                hint: `${row.action} refused by ${row.policy}`,
              }))}
              formatValue={(v) => number(v)}
            />
          ) : (
            <p className="text-muted-foreground py-6 text-center text-sm">
              No denials in the last 24 hours.
            </p>
          )}
        </ChartFrame>

        <div className="bg-card shadow-card rounded-lg p-4">
          <h3 className="text-base font-semibold">Most recent denials</h3>
          <p className="text-muted-foreground mt-1 text-sm">
            Each carries the deciding policy and rule, so a refusal can be explained rather than
            guessed at.
          </p>
          {(recent?.items ?? []).length === 0 ? (
            <p className="text-muted-foreground mt-4 text-sm">Nothing recent.</p>
          ) : (
            <ul className="mt-3 divide-y">
              {(recent?.items ?? []).map((event) => (
                <li key={event.id} className="space-y-1 py-2.5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-mono text-xs">{event.action}</span>
                    <span className="text-muted-foreground text-xs">
                      {relativeTime(event.occurred_at, institution?.locale)}
                    </span>
                  </div>
                  <p className="text-muted-foreground text-xs">
                    {event.actor_label ?? "unknown actor"} · {event.resource_type}
                  </p>
                  {event.decision_policy_id ? (
                    <p className="text-muted-foreground font-mono text-[11px]">
                      {event.decision_policy_id}/{event.decision_rule_id}
                    </p>
                  ) : (
                    <StatusBadge tone="neutral" dot={false}>
                      denied by default
                    </StatusBadge>
                  )}
                </li>
              ))}
            </ul>
          )}
          <a
            href="/denials"
            className="text-module mt-3 inline-block text-xs font-medium underline"
          >
            Full access review
          </a>
        </div>
      </div>

      {bundle?.lint && bundle.lint.length > 0 ? (
        <section className="border-warning/40 bg-warning/10 rounded-lg border p-4">
          <h2 className="text-warning-foreground text-sm font-semibold">Policy bundle warnings</h2>
          <ul className="mt-2 list-inside list-disc space-y-1 text-sm">
            {bundle.lint.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </GovernanceShell>
  )
}
