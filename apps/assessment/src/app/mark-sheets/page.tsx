import * as Icons from "lucide-react"

import type { MarkSheet } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, number } from "@acmis/ui/lib/format"

import { AssessmentShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Mark sheets" }

export default async function MarkSheetsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; mine?: string; cursor?: string }>
}) {
  const { status, mine, cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
  ])
  const page = await client.assessment.markSheets({
    status,
    mine_only: mine === "1",
    semester_id: semester?.id,
    cursor,
    limit: 50,
    with_total: true,
  })

  const columns: Array<Column<MarkSheet>> = [
    {
      key: "course",
      header: "Course offering",
      render: (row) => (
        <span className="font-mono text-xs">{row.course_offering_id.slice(0, 8)}</span>
      ),
    },
    {
      key: "status",
      header: "Stage",
      render: (row) => (
        <StatusBadge tone={toneForStatus(row.status)}>
          {humaniseStatus(row.status)}
        </StatusBadge>
      ),
    },
    {
      key: "progress",
      header: "Marked",
      numeric: true,
      render: (row) => (
        <span className={row.missing_count > 0 ? "text-warning-foreground" : ""}>
          {number(row.entered_count)} / {number(row.student_count)}
        </span>
      ),
    },
    {
      key: "mean",
      header: "Mean",
      numeric: true,
      secondary: true,
      render: (row) => (row.mean_mark !== null ? row.mean_mark.toFixed(1) : "—"),
    },
    {
      key: "pass",
      header: "Pass rate",
      numeric: true,
      secondary: true,
      render: (row) =>
        row.entered_count > 0
          ? `${Math.round((row.pass_count / row.entered_count) * 100)}%`
          : "—",
    },
    {
      key: "due",
      header: "Due",
      secondary: true,
      render: (row) => {
        const overdue =
          row.due_on !== null &&
          new Date(row.due_on) < new Date() &&
          !["senate_approved", "published"].includes(row.status)
        return (
          <span className={overdue ? "text-destructive text-xs" : "text-muted-foreground text-xs"}>
            {date(row.due_on, institution?.locale)}
            {overdue ? " · overdue" : ""}
          </span>
        )
      },
    },
  ]

  return (
    <AssessmentShell user={user} institution={institution} currentPath="/mark-sheets">
      <PageHeader
        title="Mark sheets"
        description="A sheet's statistics are shown before its marks. A 92% failure rate or a mean of 78 is a question about the assessment before it is a question about the candidates."
      />

      <form className="flex flex-wrap items-end gap-3" method="get">
        <div className="space-y-1">
          <label htmlFor="status" className="text-muted-foreground text-xs font-medium">
            Stage
          </label>
          <select
            id="status"
            name="status"
            defaultValue={status ?? ""}
            className="border-input bg-background min-h-11 w-full rounded-md border px-2.5 text-sm sm:w-auto"
          >
            <option value="">Any stage</option>
            {[
              "draft",
              "submitted",
              "returned",
              "moderated",
              "board_approved",
              "faculty_approved",
              "senate_approved",
              "published",
            ].map((value) => (
              <option key={value} value={value}>
                {humaniseStatus(value)}
              </option>
            ))}
          </select>
        </div>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" name="mine" value="1" defaultChecked={mine === "1"} />
          Only courses I teach
        </label>
        <button
          type="submit"
          className="bg-secondary text-secondary-foreground hover:bg-secondary/80 min-h-11 rounded-md px-3 text-sm font-medium"
        >
          Apply
        </button>
      </form>

      <DataTable
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        caption="Mark sheets, soonest deadline first"
        onRowHref={(row) => `/mark-sheets/${row.id}`}
        mobileCard={(row) => (
          <div className="space-y-1.5">
            <div className="flex items-start justify-between gap-2">
              <span className="font-mono text-xs">
                {row.course_offering_id.slice(0, 8)}
              </span>
              <StatusBadge tone={toneForStatus(row.status)}>
                {humaniseStatus(row.status)}
              </StatusBadge>
            </div>
            <p className="text-muted-foreground text-xs">
              {number(row.entered_count)} of {number(row.student_count)} marked
              {row.mean_mark !== null ? ` · mean ${row.mean_mark.toFixed(1)}` : ""}
            </p>
            {row.due_on ? (
              <p className="text-muted-foreground text-xs">
                Due {date(row.due_on, institution?.locale)}
              </p>
            ) : null}
          </div>
        )}
        empty={
          <EmptyState
            title="No mark sheets match"
            reason="Mark sheets are generated per course offering once registration closes. If a course you teach is missing, check that its offering exists and that you are recorded on its teaching allocation."
            icon={<Icons.ClipboardCheck className="size-8" />}
          />
        }
      />

      {page.items.length > 0 ? (
        <Pagination
          meta={page.meta}
          onNext={
            page.meta.next_cursor
              ? `/mark-sheets?${new URLSearchParams({
                  ...(status ? { status } : {}),
                  ...(mine ? { mine } : {}),
                  cursor: page.meta.next_cursor,
                }).toString()}`
              : undefined
          }
        />
      ) : null}
    </AssessmentShell>
  )
}
