import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { humaniseStatus, number, relativeTime } from "@acmis/ui/lib/format"

import { DevelopersShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * The developer portal.
 *
 * The security position is stated on the page rather than buried in
 * documentation, because it is the thing integrators most often assume wrongly:
 * a token can never do anything the account it was issued for could not do by
 * hand. Scopes narrow; they never widen.
 */
export default async function DevelopersOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, clients, events] = await Promise.all([
    client.public.institution().catch(() => null),
    client.developers.clients({ mine_only: true, limit: 20 }).catch(() => null),
    client.developers.eventTypes().catch(() => []),
  ])

  const items = clients?.items ?? []
  const live = items.filter((c) => c.environment === "live" && c.status === "active")
  const pending = items.filter((c) => c.status === "pending")

  return (
    <DevelopersShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.Terminal />}
        title="Developers"
        description={`Build against ${institution?.name ?? "this institution"}'s ACMIS. Sandbox clients are approved immediately; a live client waits for an integration administrator to grant its scopes.`}
      />

      <section className="border-module/40 bg-module/5 rounded-lg border p-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Icons.ShieldCheck className="text-module size-4" aria-hidden />
          What a token can and cannot do
        </h2>
        <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
          A client&rsquo;s effective authority is the <strong>intersection</strong> of its granted
          scopes and the permissions of the account that owns it. Granting{" "}
          <code className="bg-muted rounded px-1 font-mono text-xs">results:approve</code> to a
          client owned by a lecturer grants nothing. Interactive-only actions — conferring an award,
          releasing results, waiving fees, changing a policy — are refused to machine tokens
          entirely, whatever their scopes.
        </p>
      </section>

      <StatRow>
        <StatTile
          label="Your clients"
          value={number(items.length)}
          emphasis
          icon={<Icons.Boxes className="size-4" />}
        />
        <StatTile
          label="Live"
          value={number(live.length)}
          icon={<Icons.Radio className="size-4" />}
          footnote="Reading real student records"
        />
        <StatTile
          label="Awaiting approval"
          value={number(pending.length)}
          icon={<Icons.Clock className="size-4" />}
          footnote="Scopes not yet granted"
        />
        <StatTile
          label="Event types"
          value={number(events.length)}
          icon={<Icons.Webhook className="size-4" />}
          footnote="Available to webhook subscriptions"
        />
      </StatRow>

      <section>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Your clients</h2>
          <a
            href="/clients/new"
            className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-9 rounded-md px-3 py-2 text-sm font-medium"
          >
            Register a client
          </a>
        </div>

        {items.length === 0 ? (
          <div className="mt-3">
            <EmptyState
              title="No clients yet"
              reason="Register a sandbox client to start. It gets synthetic data with realistic shapes — a sandbox with three students and no retakes produces an integration that falls over in week one of a real semester."
              icon={<Icons.Boxes className="size-8" />}
            />
          </div>
        ) : (
          <ul className="mt-3 space-y-2">
            {items.map((apiClient) => (
              <li
                key={apiClient.id}
                className="bg-card shadow-card flex flex-wrap items-start justify-between gap-3 rounded-lg p-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium">{apiClient.name}</p>
                    <StatusBadge tone={toneForStatus(apiClient.status)}>
                      {humaniseStatus(apiClient.status)}
                    </StatusBadge>
                    <StatusBadge
                      tone={apiClient.environment === "live" ? "info" : "neutral"}
                      dot={false}
                    >
                      {apiClient.environment}
                    </StatusBadge>
                  </div>
                  <p className="text-muted-foreground mt-1 font-mono text-xs">
                    {apiClient.client_id}
                  </p>
                  {apiClient.granted_scopes.length > 0 ? (
                    <p className="text-muted-foreground mt-1.5 text-xs">
                      Scopes: {apiClient.granted_scopes.join(", ")}
                    </p>
                  ) : (
                    <p className="text-warning-foreground mt-1.5 text-xs">
                      No scopes granted — this client cannot read anything yet.
                    </p>
                  )}
                  <p className="text-muted-foreground mt-1 text-xs">
                    {apiClient.last_used_at
                      ? `Last used ${relativeTime(apiClient.last_used_at, institution?.locale)}`
                      : "Never used"}
                  </p>
                </div>
                <a
                  href={`/clients/${apiClient.id}`}
                  className="hover:bg-muted min-h-9 shrink-0 rounded-md border px-3 py-2 text-sm font-medium"
                >
                  Manage
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="bg-card shadow-card rounded-lg p-4">
        <h2 className="text-base font-semibold">Standards supported</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          ACMIS speaks the interoperability standards your existing systems already use, so adopting
          it does not mean migrating everything.
        </p>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <Standard
            title="LTI 1.3 Advantage"
            detail="ACMIS is the platform: it issues launches into your tool and receives grades back. Deep Linking, Assignment & Grade Services and Names & Role Provisioning are each granted separately."
            path="/lti"
          />
          <Standard
            title="OneRoster 1.2"
            detail="Rostering and gradebook, read-only, at the specified paths. Write bindings are deliberately not implemented — enrolments and marks change through the approval chain, not over HTTP."
            path="/reference#oneroster"
          />
          <Standard
            title="QTI 2.1 and 3.0"
            detail="Import and export question banks. Round-tripping matters: a bank readable only through our own API is a bank held hostage."
            path="/reference#qti"
          />
          <Standard
            title="xAPI and SCORM"
            detail="Content packages are recorded on import; xAPI statements stay in your own database rather than being forwarded to an external record store by default."
            path="/reference#xapi"
          />
        </dl>
        <a
          href="/standards"
          className="text-module mt-4 inline-block text-xs font-medium underline"
        >
          What each module was based on, and why
        </a>
      </section>
    </DevelopersShell>
  )
}

function Standard({ title, detail, path }: { title: string; detail: string; path: string }) {
  return (
    <div>
      <dt className="text-sm font-semibold">
        <a href={path} className="hover:text-module underline decoration-dotted">
          {title}
        </a>
      </dt>
      <dd className="text-muted-foreground mt-1 text-xs leading-relaxed">{detail}</dd>
    </div>
  )
}
