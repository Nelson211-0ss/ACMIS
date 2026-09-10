import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, dateTime, humaniseStatus, money, number } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

import { SpecialExamForm } from "./form"

export const metadata = { title: "Requests" }

/**
 * Everything a student asks the institution for, and where each one has got to.
 *
 * The reason these are on one page is that a student rarely knows which
 * office owns their problem. What they know is that they missed a paper, or
 * need a semester off, or are moving university. The page is organised by what
 * happened to them rather than by which office handles it.
 */
export default async function RequestsPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester, registrations, specials, transfers, timeOff] =
    await Promise.all([
      client.public.institution().catch(() => null),
      client.reference.currentSemester().catch(() => null),
      client.students.myRegistrations().catch(() => []),
      client.lifecycle
        .specialExams({ mine_only: true, limit: 25 })
        .catch(() => null),
      client.lifecycle.myTransfers().catch(() => []),
      client.lifecycle.myTimeOff().catch(() => null),
    ])

  const currency = institution?.currency ?? "UGX"
  const current = semester
    ? registrations.find((row) => row.semester_id === semester.id)
    : undefined
  const courses = (current?.courses ?? []).map((course) => ({
    id: course.course_offering_id,
    label: `${course.code} — ${course.title}`,
  }))
  const requests = specials?.items ?? []

  return (
    <PortalShell user={user} institution={institution} currentPath="/requests">
      <PageHeader
        title="Requests"
        description="Special and supplementary examinations, time away from study, and transfers. Each shows where it has got to and whose desk it is on."
      />

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Special and supplementary examinations</h2>
        {requests.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            You have not applied for any.
          </p>
        ) : (
          <ul className="space-y-3">
            {requests.map((request) => (
              <li key={request.id} className="bg-card rounded-lg border p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      <span className="font-mono text-xs">{request.reference}</span>
                      <span className="ml-2">
                        {humaniseStatus(request.kind)} examination
                      </span>
                    </p>
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      On the ground of {humaniseStatus(request.ground).toLowerCase()}
                      {request.missed_on ? ` · missed ${date(request.missed_on)}` : ""} ·
                      lodged {dateTime(request.submitted_at)}
                    </p>
                  </div>
                  <StatusBadge tone={toneForStatus(request.status)}>
                    {humaniseStatus(request.status)}
                  </StatusBadge>
                </div>

                <p className="mt-3 text-sm">{request.narrative}</p>

                <dl className="text-muted-foreground mt-3 grid gap-3 border-t pt-3 text-xs sm:grid-cols-3">
                  <div>
                    <dt>Evidence</dt>
                    <dd className="text-foreground mt-0.5 font-medium">
                      {request.evidence_verified_at
                        ? `Verified ${date(request.evidence_verified_at)}`
                        : request.evidence_attachment_ids.length > 0
                          ? "Lodged, awaiting verification"
                          : "Not yet lodged"}
                    </dd>
                  </div>
                  <div>
                    <dt>Recommended</dt>
                    <dd className="text-foreground mt-0.5 font-medium">
                      {date(request.recommended_at)}
                    </dd>
                  </div>
                  <div>
                    <dt>Fee</dt>
                    <dd className="text-foreground mt-0.5 font-medium">
                      {request.fee_minor
                        ? money(request.fee_minor, currency)
                        : "None charged"}
                    </dd>
                  </div>
                </dl>

                {request.decision_note ? (
                  <p className="text-muted-foreground bg-muted/40 mt-3 rounded-md border p-3 text-xs">
                    {request.decision_note}
                    {request.minute_reference
                      ? ` (minute ${request.minute_reference})`
                      : ""}
                  </p>
                ) : null}

                {!request.evidence_verified_at &&
                request.evidence_attachment_ids.length === 0 ? (
                  <p className="text-warning-foreground mt-3 text-xs">
                    This cannot be granted until the evidence reaches the faculty
                    office. Lodging the application does not put the evidence in.
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Apply for a special examination</h2>
        {!semester ? (
          <p className="text-muted-foreground text-sm">
            No semester is currently running, so there is nothing to apply
            against.
          </p>
        ) : courses.length === 0 ? (
          <EmptyState
            icon={<Icons.FileQuestion className="size-8" />}
            title="No registered courses to apply against"
            reason="A special examination is granted for a paper you were registered to sit. Register first; if the registration itself is the problem, that is a registry matter rather than an examinations one."
          />
        ) : (
          <div className="bg-card rounded-lg border p-4">
            <p className="text-muted-foreground mb-4 text-sm">
              Applications are decided by the faculty board on the facts and the
              evidence, in that order. Apply as soon as you can: a late
              application is refused on lateness alone even where the ground was
              good.
            </p>
            <SpecialExamForm semesterId={semester.id} courses={courses} />
          </div>
        )}
      </section>

      {timeOff ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Time away from study</h2>
          <div className="bg-card rounded-lg border p-4">
            <dl className="grid gap-4 text-sm sm:grid-cols-4">
              <Figure label="Dead semesters" value={number(timeOff.dead_semesters)} />
              <Figure label="Dead years" value={number(timeOff.dead_years)} />
              <Figure label="Leaves of absence" value={number(timeOff.leaves_of_absence)} />
              <Figure
                label="Permitted dead semesters"
                value={number(timeOff.dead_semesters_permitted)}
              />
            </dl>
            <p
              className={
                timeOff.standing === "exceeded"
                  ? "text-destructive mt-3 text-sm"
                  : timeOff.standing === "final_chance"
                    ? "text-warning-foreground mt-3 text-sm"
                    : "text-muted-foreground mt-3 text-sm"
              }
            >
              {timeOff.reason ??
                "You are within the maximum period of study your programme allows."}
            </p>
            <p className="text-muted-foreground mt-3 text-xs leading-relaxed">
              A dead semester is taken before the semester starts, at the
              registry, with a reason. Simply not registering is not a dead
              semester — it counts against your maximum period of study and can
              end in discontinuation. If you need to stop, say so.
            </p>
          </div>
        </section>
      ) : null}

      {transfers.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">University transfers</h2>
          <ul className="space-y-3">
            {transfers.map((transfer) => (
              <li key={transfer.id} className="bg-card rounded-lg border p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      <span className="font-mono text-xs">{transfer.reference}</span>
                      <span className="ml-2">
                        {transfer.direction === "incoming" ? "In from" : "Out to"}{" "}
                        {transfer.other_institution_name}
                      </span>
                    </p>
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      {transfer.other_programme_name ?? "Programme not stated"} ·
                      requested {date(transfer.requested_at)}
                    </p>
                  </div>
                  <StatusBadge tone={toneForStatus(transfer.status)}>
                    {humaniseStatus(transfer.status)}
                  </StatusBadge>
                </div>
                <dl className="text-muted-foreground mt-3 grid gap-3 border-t pt-3 text-xs sm:grid-cols-3">
                  <div>
                    <dt>Credits claimed</dt>
                    <dd className="text-foreground mt-0.5 font-medium">
                      {number(transfer.credits_claimed)}
                    </dd>
                  </div>
                  <div>
                    <dt>Credits awarded</dt>
                    <dd className="text-foreground mt-0.5 font-medium">
                      {number(transfer.credits_awarded)}
                    </dd>
                  </div>
                  <div>
                    <dt>Transfer cap</dt>
                    <dd className="text-foreground mt-0.5 font-medium">
                      {transfer.credit_transfer_cap_percent
                        ? `${transfer.credit_transfer_cap_percent}% of the programme`
                        : "—"}
                    </dd>
                  </div>
                </dl>
                {transfer.direction === "outgoing" && transfer.transcript_issued_at ? (
                  <p className="text-muted-foreground mt-3 text-xs">
                    Transfer papers issued {date(transfer.transcript_issued_at)}.
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground text-xs leading-relaxed">
            A transfer is not complete until the receiving institution accepts
            the credit assessment. Credit is capped as a proportion of the
            programme — an institution cannot award its degree on a majority of
            someone else&rsquo;s teaching.
          </p>
        </section>
      ) : null}
    </PortalShell>
  )
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold">{value}</dd>
    </div>
  )
}
