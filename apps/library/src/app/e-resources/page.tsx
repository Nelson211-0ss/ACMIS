import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge } from "@acmis/ui/components/status-badge"
import { date, money, number } from "@acmis/ui/lib/format"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "E-resources" }

interface Row {
  id: string
  name: string
  provider: string
  kind: string
  access_url: string | null
  authentication_method: string | null
  expires_on: string
  concurrent_users: number | null
  is_active: boolean
}

/**
 * Licensed databases and e-journal packages.
 *
 * Two facts matter and both are administrative: when the licence lapses, and
 * how many concurrent users it allows. A subscription that quietly expires
 * mid-semester is discovered by students, which is the worst way to discover
 * it — so the table is ordered by expiry and the near ones are marked.
 */
export default async function EResourcesPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, rows] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.eResources().catch(() => []),
  ])
  const currency = institution?.currency ?? "UGX"

  const daysLeft = (row: Row) =>
    Math.round((new Date(row.expires_on).getTime() - Date.now()) / 86_400_000)

  const columns: Array<Column<Row>> = [
    {
      key: "name",
      header: "Resource",
      render: (row) => (
        <div>
          <div className="font-medium">{row.name}</div>
          <div className="text-muted-foreground text-xs">{row.provider}</div>
        </div>
      ),
    },
    {
      key: "expires",
      header: "Licence ends",
      render: (row) => {
        const left = daysLeft(row)
        return (
          <span className="flex items-center gap-2">
            {date(row.expires_on)}
            {left <= 90 ? (
              <StatusBadge tone={left <= 30 ? "danger" : "warning"}>{left}d</StatusBadge>
            ) : null}
          </span>
        )
      },
    },
    {
      key: "seats",
      header: "Seats",
      numeric: true,
      secondary: true,
      render: (row) => (row.concurrent_users === null ? "Unlimited" : number(row.concurrent_users)),
    },
    {
      key: "auth",
      header: "Access",
      secondary: true,
      render: (row) => row.authentication_method?.replace(/_/g, " ") ?? "—",
    },
    {
      key: "link",
      header: "",
      render: (row) =>
        row.access_url ? (
          <a
            href={row.access_url}
            className="text-primary inline-flex items-center gap-1 text-xs underline"
            rel="noreferrer noopener"
            target="_blank"
          >
            Open
            <Icons.ExternalLink className="size-3" aria-hidden />
          </a>
        ) : null,
    },
  ]

  const lapsingSoon = rows.filter((row) => daysLeft(row as Row) <= 90)

  return (
    <LibraryShell user={user} institution={institution} currentPath="/e-resources">
      <PageHeader
        icon={<Icons.Globe />}
        title="E-resources"
        description="Subscribed databases and packages. Turnaways — readers refused because every seat was taken — are the number that justifies buying more."
      />

      {lapsingSoon.length > 0 ? (
        <p
          role="alert"
          className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm"
        >
          {lapsingSoon.length} licence{lapsingSoon.length === 1 ? "" : "s"} end within three months.
          A renewal decision takes longer than that to get through finance.
        </p>
      ) : null}

      <DataTable
        caption="Licensed electronic resources"
        columns={columns}
        rows={rows as Row[]}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="font-medium">{row.name}</div>
            <div className="text-muted-foreground text-xs">
              {row.provider} · ends {date(row.expires_on)}
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.Globe />}
            title="No subscriptions recorded"
            reason="Add the databases the institution licenses so their expiry is visible before term starts."
          />
        }
      />

      <details className="text-muted-foreground text-xs">
        <summary className="cursor-pointer">Annual cost</summary>
        <ul className="mt-2 space-y-1">
          {(rows as Array<Row & { annual_cost_minor?: number | null }>).map((row) => (
            <li key={row.id} className="flex justify-between gap-4">
              <span>{row.name}</span>
              <span className="tabular-nums">
                {row.annual_cost_minor ? money(row.annual_cost_minor, currency) : "—"}
              </span>
            </li>
          ))}
        </ul>
      </details>
    </LibraryShell>
  )
}
