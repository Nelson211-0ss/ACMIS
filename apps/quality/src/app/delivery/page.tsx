import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge } from "@acmis/ui/components/status-badge"
import { number } from "@acmis/ui/lib/format"

import { QualityShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Teaching delivery" }

interface Row {
  course_offering_id: string
  planned: number
  held: number
  cancelled: number
  not_held: number
  still_to_come: number
  delivery_percent: number | null
}

/**
 * Is the teaching that was promised actually happening?
 *
 * The one report here a head of department reads weekly. Worst first, because
 * that is the only end of the list anybody acts on — a report sorted by course
 * code buries the problem among the courses that are fine.
 */
export default async function DeliveryPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
  ])
  const delivery = semester
    ? await client.quality.delivery(semester.id).catch(() => null)
    : null

  const rows = (delivery?.offerings ?? []) as Row[]
  const columns: Array<Column<Row>> = [
    {
      key: "offering",
      header: "Offering",
      render: (row) => (
        <span className="font-mono text-xs">{row.course_offering_id.slice(0, 8)}</span>
      ),
    },
    {
      key: "delivery",
      header: "Delivered",
      numeric: true,
      render: (row) =>
        row.delivery_percent === null ? (
          <span className="text-muted-foreground">not started</span>
        ) : (
          <StatusBadge
            tone={
              row.delivery_percent >= 95
                ? "success"
                : row.delivery_percent >= 85
                  ? "warning"
                  : "danger"
            }
          >
            {row.delivery_percent.toFixed(0)}%
          </StatusBadge>
        ),
    },
    { key: "held", header: "Held", numeric: true, render: (row) => row.held },
    {
      key: "cancelled",
      header: "Announced",
      numeric: true,
      secondary: true,
      render: (row) => row.cancelled,
    },
    {
      key: "not_held",
      header: "Not held",
      numeric: true,
      render: (row) =>
        row.not_held > 0 ? (
          <span className="text-destructive font-medium tabular-nums">{row.not_held}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "remaining",
      header: "To come",
      numeric: true,
      secondary: true,
      render: (row) => row.still_to_come,
    },
  ]

  return (
    <QualityShell user={user} institution={institution} currentPath="/delivery">
      <PageHeader
        title="Teaching delivery"
        description={
          semester
            ? `${semester.name}. “Announced” is a cancellation somebody decided; “not held” is a class that simply did not happen — only the second is a delivery failure.`
            : "No current semester."
        }
      />

      <StatRow>
        <StatTile
          label="Sessions planned"
          value={number(delivery?.sessions_planned ?? 0)}
          footnote="From the timetable, less the days the campus is shut"
          icon={<Icons.CalendarRange />}
        />
        <StatTile
          label="Held"
          value={number(delivery?.sessions_held ?? 0)}
          footnote="Registers marked"
          icon={<Icons.CalendarCheck />}
        />
        <StatTile
          label="Not held"
          value={number(delivery?.unannounced_absences ?? 0)}
          footnote="Unannounced"
          icon={<Icons.CalendarX />}
          emphasis={(delivery?.unannounced_absences ?? 0) > 0}
        />
        <StatTile
          label="Courses tracked"
          value={number(rows.length)}
          footnote="With sessions generated"
          icon={<Icons.BookOpen />}
        />
      </StatRow>

      <DataTable
        caption="Teaching delivery by course offering, worst first"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.course_offering_id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="flex justify-between gap-3">
              <span className="font-mono text-xs">
                {row.course_offering_id.slice(0, 8)}
              </span>
              <span className="tabular-nums">
                {row.delivery_percent === null
                  ? "—"
                  : `${row.delivery_percent.toFixed(0)}%`}
              </span>
            </div>
            <div className="text-muted-foreground text-xs">
              {row.held} held · {row.cancelled} announced · {row.not_held} not held
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.CalendarRange />}
            title="No sessions generated"
            reason="A semester's classes are laid out from the timetable, less the public holidays that suspend teaching. Until that is done there is nothing to measure."
          />
        }
      />

      <p className="text-muted-foreground text-xs">
        The denominator counts only classes whose date has passed, so a course
        halfway through the semester is not marked down for the classes still to
        come.
      </p>
    </QualityShell>
  )
}
