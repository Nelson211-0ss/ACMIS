import * as Icons from "lucide-react"

import type { LoanRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money } from "@acmis/ui/lib/format"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Loans" }

/**
 * The circulation register.
 *
 * Reachable only from the desk, and reading it is audited. Who borrowed what
 * reveals belief, health and politics, so this page exists for the people
 * working the counter and for nobody else — a head of department asking for
 * "the borrowing history of my students" is refused by the API, not by
 * hiding a link.
 */
export default async function LoansPage({
  searchParams,
}: {
  searchParams: Promise<{ overdue?: string; cursor?: string }>
}) {
  const { overdue, cursor } = await searchParams
  const overdueOnly = overdue !== "0"
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.loans({
      overdue_only: overdueOnly,
      cursor,
      limit: 50,
      with_total: true,
    }),
  ])
  const currency = institution?.currency ?? "UGX"

  const lateness = (row: LoanRow) =>
    Math.max(0, Math.round((Date.now() - new Date(row.due_on).getTime()) / 86_400_000))

  const columns: Array<Column<LoanRow>> = [
    {
      key: "copy",
      header: "Item",
      render: (row) => (
        <div>
          <div className="font-medium">{row.title ?? "—"}</div>
          <div className="text-muted-foreground font-mono text-xs">
            {row.accession_number ?? row.copy_id.slice(0, 8)}
          </div>
        </div>
      ),
    },
    {
      key: "member",
      header: "Borrower",
      render: (row) => (
        <span className="font-mono text-xs">{row.membership_number ?? "—"}</span>
      ),
    },
    {
      key: "due",
      header: "Due",
      render: (row) => date(row.due_on),
    },
    {
      key: "late",
      header: "Late by",
      numeric: true,
      render: (row) => {
        const days = lateness(row)
        return days > 0 ? (
          <StatusBadge tone={days > 30 ? "danger" : "warning"}>{days}d</StatusBadge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )
      },
    },
    {
      key: "accrued",
      header: "Accrued",
      numeric: true,
      secondary: true,
      render: (row) => money(lateness(row) * row.fine_per_day_minor, currency),
    },
    {
      key: "renewals",
      header: "Renewals",
      numeric: true,
      secondary: true,
      render: (row) => row.renewals,
    },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <StatusBadge tone={toneForStatus(row.status)}>
          {humaniseStatus(row.status)}
        </StatusBadge>
      ),
    },
  ]

  return (
    <LibraryShell user={user} institution={institution} currentPath="/loans">
      <PageHeader
        title="Loans"
        description="Desk work only. Reading this list is recorded in the audit trail — borrowing history is among the most sensitive data the institution holds."
      />

      <nav className="flex gap-2 text-sm" aria-label="Filter">
        <a
          href="/loans"
          aria-current={overdueOnly ? "page" : undefined}
          className={
            overdueOnly
              ? "bg-primary text-primary-foreground rounded-md px-3 py-1.5"
              : "border-input rounded-md border px-3 py-1.5"
          }
        >
          Overdue
        </a>
        <a
          href="/loans?overdue=0"
          aria-current={overdueOnly ? undefined : "page"}
          className={
            overdueOnly
              ? "border-input rounded-md border px-3 py-1.5"
              : "bg-primary text-primary-foreground rounded-md px-3 py-1.5"
          }
        >
          All open
        </a>
      </nav>

      <DataTable
        caption="Open loans"
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="font-medium">{row.title ?? row.accession_number ?? "—"}</div>
            <div className="text-muted-foreground text-xs">
              {row.membership_number ?? "—"} · due {date(row.due_on)}
              {lateness(row) > 0 ? ` · ${lateness(row)} days late` : ""}
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.BookCheck />}
            title={overdueOnly ? "Nothing overdue" : "Nothing on loan"}
            reason={
              overdueOnly
                ? "Every book out is within its loan period."
                : "The shelves are full."
            }
          />
        }
      />

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/loans?${new URLSearchParams({
                ...(overdueOnly ? {} : { overdue: "0" }),
                cursor: page.meta.next_cursor,
              })}`
            : undefined
        }
      />
    </LibraryShell>
  )
}
