import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge } from "@acmis/ui/components/status-badge"
import { humaniseStatus, number } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Attendance" }

/** The threshold below which an examination card is refused. */
const REQUIRED = 75

/**
 * A student's own attendance, per course.
 *
 * Visible to the student on purpose. Attendance gates examinations, and a
 * student who cannot see it finds out they are barred in the week of the
 * paper — by which time nothing can be done about it. The excused count is
 * shown separately because an excused absence is not a shortfall, and a
 * single figure that mixes them causes an argument every semester.
 */
export default async function AttendancePage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, rows] = await Promise.all([
    client.public.institution().catch(() => null),
    client.quality.myAttendance().catch(() => []),
  ])

  const measured = rows.filter((row) => row.percentage !== null)
  const short = measured.filter((row) => (row.percentage ?? 100) < REQUIRED)
  const sessions = rows.reduce((total, row) => total + row.sessions, 0)
  const attended = rows.reduce((total, row) => total + row.attended, 0)
  const overall = sessions > 0 ? Math.round((attended * 1000) / sessions) / 10 : null

  return (
    <PortalShell user={user} institution={institution} currentPath="/attendance">
      <PageHeader
        icon={<Icons.UserCheck />}
        title="Attendance"
        description={`Counted from closed registers only — a class whose register is still open does not count against you. ${REQUIRED}% is the threshold below which an examination card is refused.`}
      />

      {rows.length === 0 ? (
        <EmptyState
          icon={<Icons.UserCheck className="size-8" />}
          title="No attendance recorded yet"
          reason="Registers appear here once a lecturer closes one. Not every course keeps a register; where none is kept, attendance is not a gate on your examination card."
        />
      ) : (
        <>
          <StatRow>
            <StatTile
              label="Overall"
              value={overall !== null ? `${overall}%` : "—"}
              footnote={`Across ${number(rows.length)} course${rows.length === 1 ? "" : "s"}`}
              icon={<Icons.UserCheck />}
              emphasis={short.length > 0}
            />
            <StatTile
              label="Sessions held"
              value={number(sessions)}
              footnote="Registers closed"
              icon={<Icons.CalendarCheck />}
            />
            <StatTile
              label="Attended"
              value={number(attended)}
              footnote="Present or late"
              icon={<Icons.Check />}
            />
            <StatTile
              label="Courses short"
              value={number(short.length)}
              footnote={`Below ${REQUIRED}%`}
              icon={<Icons.TriangleAlert />}
            />
          </StatRow>

          {short.length > 0 ? (
            <section className="border-warning/40 bg-warning/10 rounded-lg border p-4">
              <h2 className="text-warning-foreground flex items-center gap-2 text-sm font-semibold">
                <Icons.TriangleAlert className="size-4" aria-hidden />
                {short.length === 1
                  ? "One course is below the threshold"
                  : `${short.length} courses are below the threshold`}
              </h2>
              <p className="text-muted-foreground mt-1 text-sm">
                An examination card can be refused on this. If any of these absences was for a
                reason the institution accepts — illness, bereavement, a university duty — take the
                evidence to your lecturer now so the register is marked excused rather than absent.
                After the card is refused it is an appeal, which is slower and less likely to
                succeed.
              </p>
              <ul className="mt-3 space-y-1 text-sm">
                {short.map((row) => (
                  <li key={row.course_offering_id}>
                    <span className="font-mono text-xs">{row.course_code || "—"}</span>
                    <span className="ml-2">{row.course_title}</span>
                    <span className="text-warning-foreground ml-2 font-medium">
                      {row.percentage}%
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="space-y-3">
            <h2 className="text-sm font-semibold">By course</h2>
            <ul className="space-y-3">
              {rows.map((row) => {
                const value = row.percentage
                const tone =
                  value === null
                    ? "neutral"
                    : value < REQUIRED
                      ? "warning"
                      : value < 85
                        ? "info"
                        : "success"
                return (
                  <li key={row.course_offering_id} className="bg-card shadow-card rounded-lg p-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                      <p className="min-w-0 text-sm font-medium">
                        <span className="font-mono text-xs">{row.course_code || "—"}</span>
                        <span className="ml-2">{row.course_title}</span>
                      </p>
                      <StatusBadge tone={tone} dot={false}>
                        {value === null ? "Not measurable" : `${value}%`}
                      </StatusBadge>
                    </div>

                    <div
                      className="bg-muted mt-3 h-2 overflow-hidden rounded-full"
                      role="img"
                      aria-label={`${row.attended} of ${row.sessions - row.excused} countable sessions attended`}
                    >
                      <div
                        className={
                          value !== null && value < REQUIRED
                            ? "bg-warning h-full rounded-full"
                            : "bg-success h-full rounded-full"
                        }
                        style={{ width: `${Math.min(100, value ?? 0)}%` }}
                      />
                    </div>

                    <dl className="text-muted-foreground mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs">
                      <span>
                        <dt className="inline">Sessions held: </dt>
                        <dd className="text-foreground inline font-medium">
                          {number(row.sessions)}
                        </dd>
                      </span>
                      <span>
                        <dt className="inline">Attended: </dt>
                        <dd className="text-foreground inline font-medium">
                          {number(row.attended)}
                        </dd>
                      </span>
                      <span>
                        <dt className="inline">Excused: </dt>
                        <dd className="text-foreground inline font-medium">
                          {number(row.excused)}
                        </dd>
                      </span>
                      {Object.entries(row.by_status)
                        .filter(([status]) => !["present", "excused"].includes(status))
                        .map(([status, count]) => (
                          <span key={status}>
                            <dt className="inline">{humaniseStatus(status)}: </dt>
                            <dd className="text-foreground inline font-medium">{number(count)}</dd>
                          </span>
                        ))}
                    </dl>
                  </li>
                )
              })}
            </ul>
          </section>

          <p className="text-muted-foreground text-xs leading-relaxed">
            Excused sessions are removed from the denominator rather than counted as attended, so an
            excused absence neither helps nor harms the percentage. If a register says you were
            absent from a class you attended, raise it with the lecturer who closed it — the
            register itself cannot be edited after closing, so the correction is recorded as a
            dispute against the entry with a reason and a decision.
          </p>
        </>
      )}
    </PortalShell>
  )
}
