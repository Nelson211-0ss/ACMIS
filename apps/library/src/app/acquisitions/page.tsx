import * as Icons from "lucide-react"

import type { AcquisitionRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money } from "@acmis/ui/lib/format"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Acquisitions" }

/**
 * Requested titles and where they have got to.
 *
 * The list is ordered oldest first and the point of the page is the top of
 * it: which titles a lecturer asked for months ago that are still not on the
 * shelf. That question is unanswerable from an inbox, which is the whole
 * reason this is a table.
 */
export default async function AcquisitionsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; cursor?: string }>
}) {
  const { status, cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.acquisitions({ status, cursor, limit: 50, with_total: true }),
  ])
  const currency = institution?.currency ?? "UGX"

  const waiting = page.items.filter(
    (row) => !["catalogued", "declined", "cancelled"].includes(row.status),
  )

  const columns: Array<Column<AcquisitionRow>> = [
    {
      key: "title",
      header: "Title",
      render: (row) => (
        <div>
          <div className="font-medium">{row.title}</div>
          {row.authors ? <div className="text-muted-foreground text-xs">{row.authors}</div> : null}
        </div>
      ),
    },
    { key: "copies", header: "Copies", numeric: true, render: (row) => row.copies_requested },
    {
      key: "cost",
      header: "Unit price",
      numeric: true,
      secondary: true,
      render: (row) =>
        row.estimated_unit_price_minor !== null
          ? money(row.estimated_unit_price_minor, currency)
          : "—",
    },
    {
      key: "requested",
      header: "Requested",
      secondary: true,
      render: (row) => date(row.requested_on),
    },
    {
      key: "waiting",
      header: "Waiting",
      numeric: true,
      render: (row) => {
        const days = Math.round((Date.now() - new Date(row.requested_on).getTime()) / 86_400_000)
        const open = !["catalogued", "declined", "cancelled"].includes(row.status)
        return open ? (
          <StatusBadge tone={days > 60 ? "danger" : days > 30 ? "warning" : "neutral"}>
            {days}d
          </StatusBadge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )
      },
    },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <StatusBadge tone={toneForStatus(row.status)}>{humaniseStatus(row.status)}</StatusBadge>
      ),
    },
  ]

  return (
    <LibraryShell user={user} institution={institution} currentPath="/acquisitions">
      <PageHeader
        icon={<Icons.PackagePlus />}
        title="Acquisitions"
        description="From “this should be on the reading list” to an accession number. Requests tied to a course and a cohort size are the ones that get funded."
      />

      {waiting.length > 0 ? (
        <p className="border-primary/30 bg-primary/5 rounded-md border px-3 py-2 text-sm">
          {waiting.length} requested title{waiting.length === 1 ? "" : "s"} not yet on the shelf.
        </p>
      ) : null}

      <DataTable
        caption="Acquisition requests"
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="font-medium">{row.title}</div>
            <div className="text-muted-foreground text-xs">
              {row.copies_requested} cop{row.copies_requested === 1 ? "y" : "ies"} ·{" "}
              {humaniseStatus(row.status)}
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.PackagePlus />}
            title="No requests"
            reason="Teaching staff can ask for a title from their course space."
          />
        }
      />

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/acquisitions?${new URLSearchParams({
                ...(status ? { status } : {}),
                cursor: page.meta.next_cursor,
              })}`
            : undefined
        }
      />
    </LibraryShell>
  )
}
