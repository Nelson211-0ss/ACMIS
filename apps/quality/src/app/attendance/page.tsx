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

export const metadata = { title: "Attendance" }

/** The threshold most institutions set for examination eligibility. */
const REQUIRED_PERCENT = 75

interface Row {
  student_id: string
  sessions_held: number
  sessions_attended: number
  excused: number
  percentage: number | null
}

/**
 * Attendance for one course offering, worst first.
 *
 * Excused absences leave the denominator: a student excused from a class is
 * neither present nor penalised, and counting them absent turns an accepted
 * medical note into a threshold failure. Lateness counts as attendance — a
 * student twenty minutes into a two-hour lecture attended it, and a threshold
 * that says otherwise measures punctuality while claiming to measure
 * attendance.
 */
export default async function AttendancePage({
  searchParams,
}: {
  searchParams: Promise<{ offering?: string }>
}) {
  const { offering } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
  ])

  const delivery = semester
    ? await client.quality.delivery(semester.id).catch(() => null)
    : null
  const offerings = delivery?.offerings ?? []
  const selected = offering ?? offerings[0]?.course_offering_id

  const rows = selected
    ? ((await client.quality
        .offeringAttendance(selected)
        .catch(() => [])) as Row[])
    : []

  const belowThreshold = rows.filter(
    (row) => row.percentage !== null && row.percentage < REQUIRED_PERCENT,
  )

  const columns: Array<Column<Row>> = [
    {
      key: "student",
      header: "Student",
      render: (row) => <span className="font-mono text-xs">{row.student_id.slice(0, 8)}</span>,
    },
    {
      key: "percentage",
      header: "Attendance",
      numeric: true,
      render: (row) =>
        row.percentage === null ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <StatusBadge
            tone={
              row.percentage >= REQUIRED_PERCENT
                ? "success"
                : row.percentage >= REQUIRED_PERCENT - 10
                  ? "warning"
                  : "danger"
            }
          >
            {row.percentage.toFixed(0)}%
          </StatusBadge>
        ),
    },
    {
      key: "attended",
      header: "Attended",
      numeric: true,
      render: (row) => `${row.sessions_attended} / ${row.sessions_held}`,
    },
    {
      key: "excused",
      header: "Excused",
      numeric: true,
      secondary: true,
      render: (row) =>
        row.excused > 0 ? row.excused : <span className="text-muted-foreground">—</span>,
    },
  ]

  return (
    <QualityShell user={user} institution={institution} currentPath="/attendance">
      <PageHeader
        title="Attendance"
        description={`Per student, worst first. Excused absences leave the denominator; lateness counts as attendance. ${REQUIRED_PERCENT}% is the usual threshold for sitting an examination.`}
      />

      {offerings.length > 1 ? (
        <form method="get" className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label htmlFor="offering" className="text-muted-foreground text-xs font-medium">
              Course offering
            </label>
            <select
              id="offering"
              name="offering"
              defaultValue={selected}
              className="border-input bg-background rounded-md border px-2.5 py-1.5 font-mono text-base sm:text-sm"
            >
              {offerings.map((row) => (
                <option key={row.course_offering_id} value={row.course_offering_id}>
                  {row.course_offering_id.slice(0, 8)} · {row.held} held
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className="bg-primary text-primary-foreground h-9 rounded-md px-4 text-sm font-medium"
          >
            Show
          </button>
        </form>
      ) : null}

      <StatRow>
        <StatTile
          label="Students"
          value={number(rows.length)}
          footnote="With a marked register"
          icon={<Icons.Users />}
        />
        <StatTile
          label="Below threshold"
          value={number(belowThreshold.length)}
          footnote={`Under ${REQUIRED_PERCENT}%`}
          icon={<Icons.UserX />}
          emphasis={belowThreshold.length > 0}
        />
        <StatTile
          label="Mean attendance"
          value={
            rows.length > 0
              ? `${(
                  rows.reduce((sum, row) => sum + (row.percentage ?? 0), 0) / rows.length
                ).toFixed(0)}%`
              : "—"
          }
          footnote="Across the cohort"
          icon={<Icons.Percent />}
        />
        <StatTile
          label="Excusals"
          value={number(rows.reduce((sum, row) => sum + row.excused, 0))}
          footnote="With a reason on file"
          icon={<Icons.FileCheck />}
        />
      </StatRow>

      {belowThreshold.length > 0 ? (
        <p className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm">
          {belowThreshold.length} student{belowThreshold.length === 1 ? "" : "s"} below the
          threshold. Found now, this is a conversation; found at examination clearance, it
          is an appeal.
        </p>
      ) : null}

      <DataTable
        caption="Attendance by student"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.student_id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="flex justify-between gap-3">
              <span className="font-mono text-xs">{row.student_id.slice(0, 8)}</span>
              <span className="tabular-nums">
                {row.percentage === null ? "—" : `${row.percentage.toFixed(0)}%`}
              </span>
            </div>
            <div className="text-muted-foreground text-xs">
              {row.sessions_attended} of {row.sessions_held}
              {row.excused > 0 ? ` · ${row.excused} excused` : ""}
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.UserCheck />}
            title="No registers marked"
            reason="Attendance is recorded per session by whoever taught it. Absences are recorded explicitly rather than inferred from silence, so that a class where nobody marked the register is distinguishable from a class nobody attended."
          />
        }
      />
    </QualityShell>
  )
}
