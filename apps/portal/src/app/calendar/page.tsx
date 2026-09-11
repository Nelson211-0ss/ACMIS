import * as Icons from "lucide-react"

import type { CalendarEventRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, duration, humaniseStatus } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Calendar" }

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

/**
 * The three calendars a student needs, on one page.
 *
 * The academic calendar says which weeks matter; the weekly timetable says
 * where to be on a Tuesday; the examination timetable says the dates that
 * cannot be moved. Splitting them across three screens is how a student
 * misses a paper — they are here together, in the order they get consulted.
 */
export default async function CalendarPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester, timetable, events] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
    client.students.myTimetable().catch(() => null),
    client.calendar.events().catch(() => []),
  ])

  // Unpublished events are drafts the registrar is still moving around; a
  // student planning against one has been misled.
  const published = events.filter((event) => event.is_published)
  const today = new Date().toISOString().slice(0, 10)
  const upcoming = published
    .filter((event) => event.ends_on >= today)
    .sort((a, b) => a.starts_on.localeCompare(b.starts_on))
  const past = published
    .filter((event) => event.ends_on < today)
    .sort((a, b) => b.starts_on.localeCompare(a.starts_on))
    .slice(0, 8)

  const byDay = new Map<number, NonNullable<typeof timetable>["classes"]>()
  for (const slot of timetable?.classes ?? []) {
    byDay.set(slot.day_of_week, [...(byDay.get(slot.day_of_week) ?? []), slot])
  }

  return (
    <PortalShell user={user} institution={institution} currentPath="/calendar">
      <PageHeader
        icon={<Icons.CalendarDays />}
        title="Calendar"
        description={
          semester
            ? `${semester.name}: teaching ${date(semester.teaching_starts_on)} to ${date(semester.teaching_ends_on)}, examinations from ${date(semester.exams_start_on)}.`
            : "No semester is currently running."
        }
      />

      {semester ? (
        <section className="bg-card shadow-card grid grid-cols-2 gap-4 rounded-lg p-4 sm:grid-cols-4">
          <Deadline label="Registration closes" on={semester.registration_closes_on} />
          <Deadline label="Add/drop closes" on={semester.add_drop_closes_on} />
          <Deadline label="Withdrawal deadline" on={semester.withdrawal_deadline_on} />
          <Deadline label="Examinations begin" on={semester.exams_start_on} />
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Examination timetable</h2>
        {(timetable?.exams ?? []).length === 0 ? (
          <EmptyState
            icon={<Icons.FileClock className="size-8" />}
            title="No examinations scheduled for your courses yet"
            reason="The examinations office publishes the timetable once seating and invigilation are settled. It appears here for the courses on your registration only, so a paper you see is a paper you sit."
          />
        ) : (
          <ul className="divide-border divide-y rounded-lg border">
            {(timetable?.exams ?? []).map((sitting) => (
              <li
                key={`${sitting.course_offering_id}-${sitting.sitting_date}-${sitting.session}`}
                className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 p-4"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    <span className="font-mono text-xs">{sitting.code}</span>
                    <span className="ml-2">{sitting.title}</span>
                  </p>
                  <p className="text-muted-foreground mt-0.5 text-xs">
                    {sitting.rooms.length > 0 ? sitting.rooms.join(", ") : "Hall not yet allocated"}
                    {sitting.session !== "main"
                      ? ` · ${humaniseStatus(sitting.session)} sitting`
                      : ""}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm font-semibold">{date(sitting.sitting_date)}</p>
                  <p className="text-muted-foreground text-xs">
                    {sitting.starts_at} · {duration(sitting.duration_minutes)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
        {(timetable?.exams ?? []).length > 0 ? (
          <p className="text-muted-foreground text-xs leading-relaxed">
            Bring your examination card and your campus ID to every paper. Two papers at the same
            time is a clash the examinations office has to resolve — report it the day you notice,
            not the week of the exam.
          </p>
        ) : null}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">My week</h2>
        {(timetable?.classes ?? []).length === 0 ? (
          <EmptyState
            icon={<Icons.CalendarDays className="size-8" />}
            title="No classes timetabled"
            reason="Slots appear once your department timetables the courses on your registration. If you are registered and this stays empty into teaching week two, ask your department."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {DAYS.map((name, index) => {
              const slots = byDay.get(index + 1) ?? []
              if (slots.length === 0) return null
              return (
                <div key={name} className="bg-card shadow-card rounded-lg p-4">
                  <h3 className="text-sm font-semibold">{name}</h3>
                  <ul className="mt-2 space-y-2 text-sm">
                    {slots.map((slot, position) => (
                      <li key={`${slot.course_offering_id}-${slot.starts_at}-${position}`}>
                        <p className="font-medium">
                          <span className="tabular">{slot.starts_at}</span>
                          <span className="text-muted-foreground">–{slot.ends_at}</span>
                        </p>
                        <p>
                          <span className="font-mono text-xs">{slot.code}</span>
                          <span className="ml-2">{slot.title}</span>
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {humaniseStatus(slot.session_kind)}
                          {slot.is_online
                            ? " · online"
                            : slot.room
                              ? ` · ${slot.room}`
                              : " · room to be confirmed"}
                        </p>
                        {slot.is_online && slot.meeting_url ? (
                          <a
                            href={slot.meeting_url}
                            className="text-module text-xs underline"
                            rel="noreferrer"
                            target="_blank"
                          >
                            Join the session
                          </a>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Academic calendar</h2>
        {upcoming.length === 0 ? (
          <EmptyState
            icon={<Icons.CalendarOff className="size-8" />}
            title="Nothing published ahead"
            reason="Only approved and published calendar entries appear. A date circulating informally is not one you can plan against."
          />
        ) : (
          <ul className="divide-border divide-y rounded-lg border">
            {upcoming.map((event) => (
              <Entry key={event.id} event={event} />
            ))}
          </ul>
        )}
      </section>

      {past.length > 0 ? (
        <details className="rounded-lg border p-4">
          <summary className="cursor-pointer text-sm font-medium">Earlier this year</summary>
          <ul className="divide-border mt-2 divide-y">
            {past.map((event) => (
              <Entry key={event.id} event={event} muted />
            ))}
          </ul>
        </details>
      ) : null}
    </PortalShell>
  )
}

function Entry({ event, muted = false }: { event: CalendarEventRow; muted?: boolean }) {
  const span =
    event.starts_on === event.ends_on
      ? date(event.starts_on)
      : `${date(event.starts_on)} – ${date(event.ends_on)}`
  return (
    <li
      className={
        muted
          ? "text-muted-foreground flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3"
          : "flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 p-4"
      }
    >
      <div className="min-w-0">
        <p className="text-sm font-medium">{event.title}</p>
        {event.description ? (
          <p className="text-muted-foreground mt-0.5 text-xs">{event.description}</p>
        ) : null}
        <p className="text-muted-foreground mt-0.5 text-xs">
          {humaniseStatus(event.kind)}
          {event.location ? ` · ${event.location}` : ""}
          {event.suspends_teaching ? " · no classes" : ""}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p className="text-sm">{span}</p>
        {event.starts_at ? (
          <p className="text-muted-foreground text-xs">
            {event.starts_at}
            {event.ends_at ? `–${event.ends_at}` : ""}
          </p>
        ) : null}
        {event.suspends_teaching ? (
          <StatusBadge tone={toneForStatus("suspended")} dot={false} className="mt-1">
            Teaching suspended
          </StatusBadge>
        ) : null}
      </div>
    </li>
  )
}

function Deadline({ label, on }: { label: string; on: string | null }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="mt-0.5 text-sm font-semibold">{date(on)}</p>
    </div>
  )
}
