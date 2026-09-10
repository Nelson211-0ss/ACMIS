import * as Icons from "lucide-react"

import type { Invoice } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money } from "@acmis/ui/lib/format"

import { FinanceShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Invoices" }

/**
 * Invoices, overdue first by default.
 *
 * The sponsor split is on every row because it changes what "outstanding"
 * means: a student whose government sponsorship covers 80% owes the balance
 * of their own portion, and chasing them for the sponsor's share is both
 * futile and unkind.
 */
export default async function InvoicesPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; overdue?: string; cursor?: string }>
}) {
  const { status, overdue, cursor } = await searchParams
  const overdueOnly = overdue === "1"
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.finance.invoices({
      status,
      overdue_only: overdueOnly,
      cursor,
      limit: 50,
      with_total: true,
    }),
  ])
  const currency = institution?.currency ?? "UGX"

  const columns: Array<Column<Invoice>> = [
    {
      key: "number",
      header: "Invoice",
      render: (row) => <span className="font-mono text-xs">{row.number}</span>,
    },
    { key: "kind", header: "For", render: (row) => humaniseStatus(row.kind) },
    {
      key: "total",
      header: "Total",
      numeric: true,
      render: (row) => money(row.total_minor, currency),
    },
    {
      key: "sponsor",
      header: "Sponsor pays",
      numeric: true,
      secondary: true,
      render: (row) =>
        row.sponsor_portion_minor > 0 ? (
          money(row.sponsor_portion_minor, currency)
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "balance",
      header: "Outstanding",
      numeric: true,
      render: (row) =>
        row.balance_minor > 0 ? (
          <span className="tabular-nums font-medium">
            {money(row.balance_minor, currency)}
          </span>
        ) : (
          <span className="text-muted-foreground">settled</span>
        ),
    },
    {
      key: "due",
      header: "Due",
      secondary: true,
      render: (row) => (row.due_on ? date(row.due_on) : "—"),
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

  const outstanding = page.items.reduce((sum, row) => sum + row.balance_minor, 0)

  return (
    <FinanceShell user={user} institution={institution} currentPath="/invoices">
      <PageHeader
        title="Invoices"
        description="What was billed, what the sponsor covers, and what is still owed. A student on an agreed instalment plan is not late, whatever the due date says."
      />

      <form className="flex flex-wrap items-end gap-3" method="get">
        <div className="space-y-1">
          <label htmlFor="status" className="text-muted-foreground text-xs font-medium">
            Status
          </label>
          <select
            id="status"
            name="status"
            defaultValue={status ?? ""}
            className="border-input bg-background rounded-md border px-2.5 py-1.5 text-base sm:text-sm"
          >
            <option value="">Any</option>
            {["draft", "issued", "part_paid", "paid", "overdue", "cancelled"].map((v) => (
              <option key={v} value={v}>
                {humaniseStatus(v)}
              </option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 pb-1.5 text-sm">
          <input type="checkbox" name="overdue" value="1" defaultChecked={overdueOnly} />
          Overdue only
        </label>
        <button
          type="submit"
          className="bg-primary text-primary-foreground h-9 rounded-md px-4 text-sm font-medium"
        >
          Apply
        </button>
      </form>

      <p className="text-muted-foreground text-sm">
        {money(outstanding, currency)} outstanding across the invoices shown.
      </p>

      <DataTable
        caption="Invoices"
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="flex justify-between gap-3">
              <span className="font-mono text-xs">{row.number}</span>
              <span className="tabular-nums">{money(row.balance_minor, currency)}</span>
            </div>
            <div className="text-muted-foreground text-xs">
              {humaniseStatus(row.kind)} · {row.due_on ? `due ${date(row.due_on)}` : "no date"}
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.FileText />}
            title="No invoices match"
            reason="A semester invoice is raised per student from the published fee structure."
          />
        }
      />

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/invoices?${new URLSearchParams({
                ...(status ? { status } : {}),
                ...(overdueOnly ? { overdue: "1" } : {}),
                cursor: page.meta.next_cursor,
              })}`
            : undefined
        }
      />
    </FinanceShell>
  )
}
