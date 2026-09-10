import * as Icons from "lucide-react"

import type { LibraryFineRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money } from "@acmis/ui/lib/format"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Fines" }

/**
 * Charges raised by the library and settled through the ledger.
 *
 * Every row shows the arithmetic. "You owe 14,000" is disputed; "14 days at
 * 1,000" is paid, and the difference is most of the desk's argument budget.
 */
export default async function FinesPage({
  searchParams,
}: {
  searchParams: Promise<{ all?: string; cursor?: string }>
}) {
  const { all, cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.fines({
      unpaid_only: all !== "1",
      cursor,
      limit: 50,
      with_total: true,
    }),
  ])
  const currency = institution?.currency ?? "UGX"
  const canWaive = ["library:admin", "finance:waive"].some((code) =>
    user.permissions.includes(code),
  )

  const columns: Array<Column<LibraryFineRow>> = [
    {
      key: "reason",
      header: "Reason",
      render: (row) => humaniseStatus(row.reason),
    },
    {
      key: "amount",
      header: "Amount",
      numeric: true,
      render: (row) => money(row.amount_minor, currency),
    },
    {
      key: "working",
      header: "How it was reached",
      secondary: true,
      render: (row) =>
        row.days_overdue !== null && row.rate_per_day_minor !== null ? (
          <span className="text-muted-foreground text-xs">
            {row.days_overdue} day{row.days_overdue === 1 ? "" : "s"} ×{" "}
            {money(row.rate_per_day_minor, currency)}
          </span>
        ) : (
          <span className="text-muted-foreground text-xs">Replacement cost</span>
        ),
    },
    { key: "raised", header: "Raised", secondary: true, render: (row) => date(row.raised_on) },
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
    <LibraryShell user={user} institution={institution} currentPath="/fines">
      <PageHeader
        title="Fines"
        description="Raised here, settled through the ledger. The library owns why the money is owed; finance owns the money — which is what stops the library becoming a second, unreconciled cash system."
      />

      {!canWaive ? (
        <p className="text-muted-foreground bg-muted/40 rounded-md border px-3 py-2 text-xs">
          Waiving a charge is money the institution has decided not to collect, so it
          needs the librarian&rsquo;s grant rather than the desk&rsquo;s.
        </p>
      ) : null}

      <nav className="flex gap-2 text-sm" aria-label="Filter">
        <a
          href="/fines"
          className={
            all === "1"
              ? "border-input rounded-md border px-3 py-1.5"
              : "bg-primary text-primary-foreground rounded-md px-3 py-1.5"
          }
        >
          Unpaid
        </a>
        <a
          href="/fines?all=1"
          className={
            all === "1"
              ? "bg-primary text-primary-foreground rounded-md px-3 py-1.5"
              : "border-input rounded-md border px-3 py-1.5"
          }
        >
          Everything
        </a>
      </nav>

      <DataTable
        caption="Library charges"
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="flex justify-between gap-3">
              <span className="font-medium">{humaniseStatus(row.reason)}</span>
              <span className="tabular-nums">{money(row.amount_minor, currency)}</span>
            </div>
            {row.days_overdue !== null && row.rate_per_day_minor !== null ? (
              <div className="text-muted-foreground text-xs">
                {row.days_overdue} × {money(row.rate_per_day_minor, currency)}
              </div>
            ) : null}
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.ReceiptText />}
            title="Nothing outstanding"
            reason="No unpaid library charges."
          />
        }
      />

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/fines?${new URLSearchParams({
                ...(all === "1" ? { all: "1" } : {}),
                cursor: page.meta.next_cursor,
              })}`
            : undefined
        }
      />
    </LibraryShell>
  )
}
