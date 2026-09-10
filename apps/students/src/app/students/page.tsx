import * as Icons from "lucide-react"

import type { Student } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { humaniseStatus, surnameFirst } from "@acmis/ui/lib/format"

import { StudentsShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Students" }

export default async function StudentsListPage({
  searchParams,
}: {
  searchParams: Promise<{
    status?: string
    search?: string
    year_of_study?: string
    cursor?: string
  }>
}) {
  const { status, search, year_of_study, cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.students.list({
      status,
      search,
      year_of_study: year_of_study ? Number(year_of_study) : undefined,
      cursor,
      limit: 50,
      with_total: true,
    }),
  ])

  const columns: Array<Column<Student>> = [
    {
      key: "number",
      header: "Student number",
      render: (row) => <span className="font-mono text-xs">{row.student_number}</span>,
    },
    { key: "name", header: "Name", render: (row) => surnameFirst(row) },
    {
      key: "status",
      header: "Standing",
      render: (row) => (
        <StatusBadge tone={toneForStatus(row.status)}>
          {humaniseStatus(row.status)}
        </StatusBadge>
      ),
    },
    {
      key: "year",
      header: "Year",
      numeric: true,
      secondary: true,
      render: (row) => {
        const primary = row.programmes.find((p) => p.is_primary)
        return primary ? primary.current_year_of_study : "—"
      },
    },
    {
      key: "cgpa",
      header: "CGPA",
      numeric: true,
      secondary: true,
      render: (row) => {
        const primary = row.programmes.find((p) => p.is_primary)
        return primary?.cgpa !== null && primary?.cgpa !== undefined
          ? primary.cgpa.toFixed(2)
          : "—"
      },
    },
    {
      key: "holds",
      header: "Holds",
      secondary: true,
      render: (row) => {
        const active = row.holds.filter((h) => !h.cleared_at)
        return active.length > 0 ? (
          <StatusBadge tone="warning" dot={false}>
            {active.length} · {active[0]?.kind}
          </StatusBadge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )
      },
    },
  ]

  return (
    <StudentsShell user={user} institution={institution} currentPath="/students">
      <PageHeader
        title="Students"
        description="Restricted to the faculties and departments you have reach over. A filter naming a unit outside your reach is intersected with it rather than refused."
      />

      <form className="flex flex-wrap items-end gap-3" method="get">
        <div className="space-y-1">
          <label htmlFor="search" className="text-muted-foreground text-xs font-medium">
            Search
          </label>
          <input
            id="search"
            name="search"
            defaultValue={search}
            placeholder="Name or student number"
            className="border-input bg-background w-56 rounded-md border px-2.5 py-1.5 text-sm"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="status" className="text-muted-foreground text-xs font-medium">
            Standing
          </label>
          <select
            id="status"
            name="status"
            defaultValue={status ?? ""}
            className="border-input bg-background rounded-md border px-2.5 py-1.5 text-sm"
          >
            <option value="">Any</option>
            {[
              "active",
              "probation",
              "on_leave",
              "suspended",
              "completed",
              "graduated",
              "withdrawn",
              "discontinued",
            ].map((value) => (
              <option key={value} value={value}>
                {humaniseStatus(value)}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label
            htmlFor="year_of_study"
            className="text-muted-foreground text-xs font-medium"
          >
            Year
          </label>
          <select
            id="year_of_study"
            name="year_of_study"
            defaultValue={year_of_study ?? ""}
            className="border-input bg-background rounded-md border px-2.5 py-1.5 text-sm"
          >
            <option value="">Any</option>
            {[1, 2, 3, 4, 5, 6].map((year) => (
              <option key={year} value={year}>
                Year {year}
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
      </form>

      <DataTable
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        caption="Students within your reach, by surname"
        onRowHref={(row) => `/students/${row.id}`}
        empty={
          <EmptyState
            title="No students match"
            reason="Either nothing matches these filters, or your roles give you no reach over any faculty or department. A dean sees their own faculties; the registry sees everyone."
            icon={<Icons.Users className="size-8" />}
          />
        }
      />

      {page.items.length > 0 ? (
        <Pagination
          meta={page.meta}
          onNext={
            page.meta.next_cursor
              ? `/students?${new URLSearchParams({
                  ...(status ? { status } : {}),
                  ...(search ? { search } : {}),
                  ...(year_of_study ? { year_of_study } : {}),
                  cursor: page.meta.next_cursor,
                }).toString()}`
              : undefined
          }
        />
      ) : null}
    </StudentsShell>
  )
}
