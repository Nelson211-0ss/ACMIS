import * as Icons from "lucide-react"
import Link from "next/link"

import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus } from "@acmis/ui/lib/format"
import type { Application } from "@acmis/api-client"

import { AdmissionsShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Applications" }

const STATUSES = [
  "submitted",
  "awaiting_fee",
  "under_review",
  "interview",
  "recommended",
  "admitted",
  "waitlisted",
  "rejected",
]

export default async function ApplicationsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; search?: string; cursor?: string }>
}) {
  const { status, search, cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.admissions.applications({
      status,
      search,
      cursor,
      limit: 50,
      with_total: true,
    }),
  ])

  const columns: Array<Column<Application>> = [
    {
      key: "number",
      header: "Application",
      render: (row) => <span className="font-mono text-xs">{row.number}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <StatusBadge tone={toneForStatus(row.status)}>{humaniseStatus(row.status)}</StatusBadge>
      ),
    },
    {
      key: "score",
      header: "Score",
      numeric: true,
      render: (row) =>
        row.final_score !== null ? (
          <span className="font-medium">{row.final_score.toFixed(2)}</span>
        ) : (
          <span className="text-muted-foreground">not scored</span>
        ),
    },
    {
      key: "fee",
      header: "Fee",
      secondary: true,
      render: (row) =>
        row.fee_settled_at ? (
          <StatusBadge tone="success" dot={false}>
            Settled
          </StatusBadge>
        ) : (
          <StatusBadge tone="warning" dot={false}>
            Outstanding
          </StatusBadge>
        ),
    },
    {
      key: "submitted",
      header: "Submitted",
      secondary: true,
      render: (row) => (
        <span className="text-muted-foreground text-xs">
          {date(row.submitted_at, institution?.locale)}
          {row.is_late ? " · late" : ""}
        </span>
      ),
    },
    {
      key: "flags",
      header: "Flags",
      secondary: true,
      render: (row) =>
        row.flags.length > 0 ? (
          <span className="text-warning-foreground text-xs">{row.flags.join(", ")}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ]

  return (
    <AdmissionsShell user={user} institution={institution} currentPath="/applications">
      <PageHeader
        icon={<Icons.FileText />}
        title="Applications"
        description="Only applications ranked to a faculty you have reach over are listed. A selector without the office-wide grant sees their own faculties only."
      />

      {/* Filters in one row above the list, per the interaction spec. A GET
          form so a filtered view is a shareable URL and the back button works. */}
      <form className="flex flex-wrap items-end gap-3" method="get">
        <div className="space-y-1">
          <label htmlFor="search" className="text-muted-foreground text-xs font-medium">
            Search
          </label>
          <input
            id="search"
            name="search"
            defaultValue={search}
            placeholder="Name or application number"
            className="border-input bg-background w-56 rounded-md border px-2.5 py-1.5 text-sm"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="status" className="text-muted-foreground text-xs font-medium">
            Status
          </label>
          <select
            id="status"
            name="status"
            defaultValue={status ?? ""}
            className="border-input bg-background rounded-md border px-2.5 py-1.5 text-sm"
          >
            <option value="">Any status</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {humaniseStatus(value)}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          className="bg-secondary text-secondary-foreground hover:bg-secondary/80 rounded-md px-3 py-1.5 text-sm font-medium"
        >
          Apply
        </button>
        {status || search ? (
          <Link
            href="/applications"
            className="text-muted-foreground hover:text-foreground py-1.5 text-sm underline"
          >
            Clear
          </Link>
        ) : null}
      </form>

      <DataTable
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        caption="Applications, most competitive first"
        onRowHref={(row) => `/applications/${row.id}`}
        empty={
          <EmptyState
            title="No applications match"
            reason={
              status || search
                ? "Nothing matches these filters. Clear them to see everything within your reach."
                : "No applications have been submitted for the schemes and faculties you have access to."
            }
            icon={<Icons.FileText className="size-8" />}
          />
        }
      />

      {page.items.length > 0 ? (
        <Pagination
          meta={page.meta}
          onNext={
            page.meta.next_cursor
              ? `/applications?${new URLSearchParams({
                  ...(status ? { status } : {}),
                  ...(search ? { search } : {}),
                  cursor: page.meta.next_cursor,
                }).toString()}`
              : undefined
          }
        />
      ) : null}
    </AdmissionsShell>
  )
}
