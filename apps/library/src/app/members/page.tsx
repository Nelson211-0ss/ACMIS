import * as Icons from "lucide-react"

import type { LibraryMemberRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money } from "@acmis/ui/lib/format"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Members" }

export default async function MembersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; debt?: string; cursor?: string }>
}) {
  const { q, debt, cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.members({
      q,
      with_debt: debt === "1",
      cursor,
      limit: 50,
      with_total: true,
    }),
  ])
  const currency = institution?.currency ?? "UGX"

  const columns: Array<Column<LibraryMemberRow>> = [
    {
      key: "number",
      header: "Membership",
      render: (row) => <span className="font-mono text-xs">{row.membership_number}</span>,
    },
    {
      key: "category",
      header: "Category",
      render: (row) => humaniseStatus(row.borrower_category),
    },
    {
      key: "out",
      header: "Out",
      numeric: true,
      render: (row) => row.items_on_loan,
    },
    {
      key: "owed",
      header: "Owed",
      numeric: true,
      render: (row) =>
        row.outstanding_fines_minor > 0 ? (
          <span className="text-destructive tabular-nums">
            {money(row.outstanding_fines_minor, currency)}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "expires",
      header: "Expires",
      secondary: true,
      render: (row) => (row.expires_on ? date(row.expires_on) : "—"),
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
    <LibraryShell user={user} institution={institution} currentPath="/members">
      <PageHeader
        title="Members"
        description="Readers, including the ones the academic system does not know: visiting researchers, alumni, staff of partner institutions."
      />

      <form className="flex flex-wrap items-end gap-3" method="get">
        <div className="space-y-1">
          <label htmlFor="q" className="text-muted-foreground text-xs font-medium">
            Search
          </label>
          <input
            id="q"
            name="q"
            defaultValue={q}
            placeholder="Membership number or name"
            className="border-input bg-background w-64 rounded-md border px-2.5 py-1.5 text-base sm:text-sm"
          />
        </div>
        <label className="flex items-center gap-2 pb-1.5 text-sm">
          <input type="checkbox" name="debt" value="1" defaultChecked={debt === "1"} />
          Owing only
        </label>
        <button
          type="submit"
          className="bg-primary text-primary-foreground h-9 rounded-md px-4 text-sm font-medium"
        >
          Search
        </button>
      </form>

      <DataTable
        caption="Library members"
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="font-mono text-xs">{row.membership_number}</div>
            <div className="text-muted-foreground text-xs">
              {humaniseStatus(row.borrower_category)} · {row.items_on_loan} out
              {row.outstanding_fines_minor > 0
                ? ` · ${money(row.outstanding_fines_minor, currency)} owed`
                : ""}
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.UserSearch />}
            title="No members match"
            reason="Membership is created on first use rather than in bulk at enrolment."
          />
        }
      />

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/members?${new URLSearchParams({
                ...(q ? { q } : {}),
                ...(debt === "1" ? { debt: "1" } : {}),
                cursor: page.meta.next_cursor,
              })}`
            : undefined
        }
      />
    </LibraryShell>
  )
}
