import * as Icons from "lucide-react"
import Link from "next/link"
import { notFound } from "next/navigation"

import type { CatalogueCopyRow } from "@acmis/api-client"
import { ApiError } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, type Column } from "@acmis/ui/components/data-table"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, number } from "@acmis/ui/lib/format"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Record" }

/**
 * One catalogue record, with its copies.
 *
 * `earliest_due` is the field that matters to a reader: "all copies out" is
 * useless, "the first one is back on Tuesday" is something they can plan
 * around.
 */
export default async function RecordPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, record, availability, copies] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.record(id).catch((error) => {
      if (error instanceof ApiError && error.status === 404) notFound()
      throw error
    }),
    client.library.availability(id),
    client.library.copies(id).catch(() => [] as CatalogueCopyRow[]),
  ])

  const columns: Array<Column<CatalogueCopyRow>> = [
    {
      key: "accession",
      header: "Accession",
      render: (row) => <span className="font-mono text-xs">{row.accession_number}</span>,
    },
    {
      key: "call",
      header: "Call number",
      render: (row) =>
        row.call_number ? (
          <span className="font-mono text-xs">{row.call_number}</span>
        ) : (
          "—"
        ),
    },
    {
      key: "shelf",
      header: "Where",
      secondary: true,
      render: (row) => row.shelf_location ?? "—",
    },
    {
      key: "class",
      header: "Loan class",
      render: (row) => (
        <StatusBadge tone="neutral" dot={false}>
          {row.loan_class.replace(/_/g, " ")}
        </StatusBadge>
      ),
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
    {
      key: "issued",
      header: "Times issued",
      numeric: true,
      secondary: true,
      render: (row) => number(row.times_issued),
    },
  ]

  return (
    <LibraryShell user={user} institution={institution} currentPath="/catalogue">
      <PageHeader
        title={record.title}
        description={record.statement_of_responsibility ?? undefined}
        breadcrumbs={
          <nav aria-label="Breadcrumb" className="text-muted-foreground text-xs">
            <Link href="/catalogue" className="hover:text-foreground underline">
              Catalogue
            </Link>
            <span aria-hidden> / </span>
            <span>{record.title}</span>
          </nav>
        }
      />

      <StatRow>
        <StatTile
          label="Copies"
          value={number(availability.copies)}
          footnote="Accessioned"
          icon={<Icons.Library />}
        />
        <StatTile
          label="On the shelf"
          value={number(availability.available)}
          footnote="Available now"
          icon={<Icons.BookOpen />}
          emphasis={availability.available > 0}
        />
        <StatTile
          label="Out"
          value={number(availability.on_loan)}
          footnote={
            availability.earliest_due
              ? `First back ${date(availability.earliest_due)}`
              : "None on loan"
          }
          icon={<Icons.BookMarked />}
        />
        <StatTile
          label="Waiting"
          value={number(availability.reservations)}
          footnote="Readers in the queue"
          icon={<Icons.Users />}
        />
      </StatRow>

      {availability.available === 0 && availability.earliest_due ? (
        <p className="border-primary/30 bg-primary/5 rounded-md border px-3 py-2 text-sm">
          Every copy is out. The first is due back on {date(availability.earliest_due)} —
          a reservation puts the reader at the head of the queue when it arrives.
        </p>
      ) : null}

      <DataTable
        caption="Copies of this work"
        columns={columns}
        rows={copies}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="font-mono text-xs">{row.accession_number}</div>
            <div className="text-muted-foreground text-xs">
              {row.call_number ?? "—"} · {humaniseStatus(row.status)}
            </div>
          </div>
        )}
      />
    </LibraryShell>
  )
}
