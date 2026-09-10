import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, dateTime, humaniseStatus, number, percent } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Exam cards" }

/** What a `clearance_snapshot` holds. Written by the issuing endpoint. */
type Snapshot = {
  fee_percentage_paid?: number
  required_percentage?: number
  attendance_ok?: boolean | null
  registration_status?: string
}

/**
 * Permission to sit, and the reasons it was or was not given.
 *
 * The card carries a snapshot of the gates as they stood at issue, and the
 * page shows it. A card printed on Monday and questioned on Friday has to be
 * explainable — a reversed payment after issue does not retrospectively make
 * the invigilator wrong to have admitted the candidate.
 */
export default async function ExamCardsPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, cards, registrations, semester] = await Promise.all([
    client.public.institution().catch(() => null),
    client.lifecycle.myExamCards().catch(() => []),
    client.students.myRegistrations().catch(() => []),
    client.reference.currentSemester().catch(() => null),
  ])

  const current = semester
    ? registrations.find((row) => row.semester_id === semester.id)
    : undefined
  const hasCurrentCard = cards.some(
    (card) => card.semester_id === semester?.id && card.status === "issued",
  )

  return (
    <PortalShell user={user} institution={institution} currentPath="/exam-cards">
      <PageHeader
        title="Exam cards"
        description="An examination card is permission to sit a specific set of papers. Bring it, with your campus ID, to every paper — an invigilator who cannot verify you is required to turn you away."
      />

      {!hasCurrentCard && current ? (
        <section className="bg-muted/40 rounded-lg border p-4">
          <h2 className="text-sm font-semibold">
            No card yet for {current.semester_name ?? "this semester"}
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Cards are issued by the faculty office once three things hold: your
            registration is approved, your fees have reached the threshold your
            institution sets, and your attendance is not short in any course
            where a register was kept. Where any of those is outstanding the
            card is refused with the reason, not silently withheld.
          </p>
          <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Registration</dt>
              <dd className="mt-0.5">
                <StatusBadge tone={toneForStatus(current.status)} dot={false}>
                  {humaniseStatus(current.status)}
                </StatusBadge>
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Courses on it</dt>
              <dd className="mt-0.5 font-medium">{number(current.courses.length)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Exams begin</dt>
              <dd className="mt-0.5 font-medium">{date(semester?.exams_start_on)}</dd>
            </div>
          </dl>
        </section>
      ) : null}

      {cards.length === 0 ? (
        <EmptyState
          icon={<Icons.Ticket className="size-8" />}
          title="No examination card has been issued to you"
          reason="Cards appear here as soon as the faculty office issues one. There is nothing to apply for: the office issues against an approved registration."
        />
      ) : (
        <ul className="space-y-4">
          {cards.map((card) => {
            const snapshot = card.clearance_snapshot as Snapshot
            return (
              <li key={card.id} className="bg-card overflow-hidden rounded-lg border">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b p-4">
                  <div>
                    <p className="font-semibold">
                      {card.semester_name ?? "Semester"} ·{" "}
                      {humaniseStatus(card.session)} examinations
                    </p>
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      Issued {dateTime(card.issued_at)}
                      {card.valid_until ? ` · valid until ${date(card.valid_until)}` : ""}
                    </p>
                  </div>
                  <StatusBadge tone={toneForStatus(card.status)}>
                    {humaniseStatus(card.status)}
                  </StatusBadge>
                </div>

                <div className="grid gap-4 p-4 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <div>
                    <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                      Papers this card admits you to
                    </p>
                    {card.papers.length === 0 ? (
                      <p className="text-muted-foreground mt-1 text-sm">
                        None recorded. Query this with your faculty office before
                        the first paper.
                      </p>
                    ) : (
                      <ul className="mt-2 space-y-1 text-sm">
                        {card.papers.map((paper) => (
                          <li key={paper.course_offering_id}>
                            <span className="font-mono text-xs">{paper.code}</span>
                            <span className="ml-2">{paper.title}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    <p className="text-muted-foreground mt-2 text-xs">
                      A paper not on this list is one you are not registered
                      for. Sitting it produces a mark that cannot be boarded.
                    </p>
                  </div>

                  <div className="bg-muted/50 rounded-md border p-3 text-center">
                    <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                      Verification code
                    </p>
                    <p className="mt-1 font-mono text-lg font-semibold tracking-widest">
                      {card.verification_code}
                    </p>
                    <p className="text-muted-foreground mt-1 text-xs">
                      Read by the invigilator at the hall door
                    </p>
                  </div>
                </div>

                <dl className="text-muted-foreground grid gap-3 border-t p-4 text-xs sm:grid-cols-3">
                  <div>
                    <dt>Fees at issue</dt>
                    <dd className="text-foreground mt-0.5 font-medium">
                      {snapshot.fee_percentage_paid !== undefined
                        ? `${percent(snapshot.fee_percentage_paid, "en-UG", 0)} paid${
                            snapshot.required_percentage !== undefined
                              ? ` of ${percent(snapshot.required_percentage, "en-UG", 0)} required`
                              : ""
                          }`
                        : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Attendance at issue</dt>
                    <dd className="text-foreground mt-0.5 font-medium">
                      {snapshot.attendance_ok === true
                        ? "Sufficient"
                        : snapshot.attendance_ok === false
                          ? "Short in at least one course"
                          : "No register kept"}
                    </dd>
                  </div>
                  <div>
                    <dt>Issued under override</dt>
                    <dd className="text-foreground mt-0.5 font-medium">
                      {card.override_reason ? "Yes" : "No"}
                    </dd>
                  </div>
                </dl>

                {card.override_reason ? (
                  <p className="text-warning-foreground bg-warning/10 border-t px-4 py-3 text-xs">
                    Issued on an override: {card.override_reason}
                  </p>
                ) : null}

                {card.status === "revoked" ? (
                  <p className="text-destructive bg-destructive/10 border-t px-4 py-3 text-xs">
                    This card has been revoked. It will not verify at the hall
                    door. Speak to your faculty office before the next paper.
                  </p>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </PortalShell>
  )
}
