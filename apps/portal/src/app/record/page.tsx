import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { NotPermitted } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, number, surnameFirst } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "My record" }

/**
 * The student's own record, as the registry holds it.
 *
 * Two things this page is careful about. Fields the mask withheld are named
 * as restricted rather than shown blank — a blank cell reads as missing data
 * and starts a support call. And the registry-owned fields are labelled as
 * such, because the honest answer to "why can't I edit my name" is that the
 * change needs a document, not that the form is broken.
 */
export default async function RecordPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, record, timeOff] = await Promise.all([
    client.public.institution().catch(() => null),
    client.students.myRecord().catch(() => null),
    client.lifecycle.myTimeOff().catch(() => null),
  ])

  if (!record) {
    return (
      <PortalShell user={user} institution={institution} currentPath="/record">
        <NotPermitted what="your student record" contact="the academic registrar" />
      </PortalShell>
    )
  }

  const student = record.data
  const masked = new Set(record.masked_fields)
  const holds = student.holds.filter((hold) => !hold.cleared_at)
  const clearance = await client.students.clearance(student.id).catch(() => [])

  return (
    <PortalShell user={user} institution={institution} currentPath="/record">
      <PageHeader
        title="My record"
        description="What the registry holds about you. Contact details you may correct yourself; name, date of birth, programme and sponsorship are registry-owned and need documentary evidence to change."
        actions={
          <StatusBadge tone={toneForStatus(student.status)}>
            {humaniseStatus(student.status)}
          </StatusBadge>
        }
      />

      {holds.length > 0 ? (
        <section className="border-destructive/40 bg-destructive/10 rounded-lg border p-4">
          <h2 className="text-destructive flex items-center gap-2 text-sm font-semibold">
            <Icons.Lock className="size-4" aria-hidden />
            {holds.length === 1 ? "A hold" : `${holds.length} holds`} on your record
          </h2>
          <ul className="mt-2 space-y-1 text-sm">
            {holds.map((hold) => (
              <li key={`${hold.kind}-${hold.placed_at ?? ""}`}>
                <span className="font-medium">{humaniseStatus(hold.kind)}</span>
                <span className="text-muted-foreground"> — {hold.reason}</span>
                {hold.placed_at ? (
                  <span className="text-muted-foreground text-xs">
                    {" "}
                    (placed {date(hold.placed_at)})
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Identity</h2>
        <dl className="bg-card grid gap-4 rounded-lg border p-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Student number" value={student.student_number} mono />
          <Field label="Name" value={surnameFirst(student)} />
          <Field label="Date of birth" value={date(student.date_of_birth)} />
          <Field label="Sex" value={humaniseStatus(student.sex)} />
          <Field label="Nationality" value={student.nationality} />
          <Field label="District of origin" value={student.district_of_origin} />
          <Field
            label="National ID"
            value={student.national_id}
            restricted={masked.has("national_id")}
            mono
          />
          <Field label="Admitted" value={date(student.admitted_on)} />
          <Field label="Residence" value={humaniseStatus(student.residence)} />
        </dl>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Contact</h2>
        <dl className="bg-card grid gap-4 rounded-lg border p-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="University email" value={student.email} />
          <Field label="Phone" value={student.phone} />
          <Field label="Next of kin" value={student.next_of_kin_name} />
          <Field label="Next of kin phone" value={student.next_of_kin_phone} />
          <Field
            label="Bank account"
            value={student.bank_account_number}
            restricted={masked.has("bank_account_number")}
            mono
          />
        </dl>
        <p className="text-muted-foreground text-xs">
          Corrections to contact details are made at the registry counter or by
          your faculty administrator. They take effect immediately; a change of
          name or date of birth goes to a status-change decision instead.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Programme</h2>
        {student.programmes.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            No programme attached. That is a registry error — report it.
          </p>
        ) : (
          <ul className="space-y-3">
            {student.programmes.map((programme) => (
              <li key={programme.id} className="bg-card rounded-lg border p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm font-medium">
                    Year {programme.current_year_of_study}, semester{" "}
                    {programme.current_semester_number}
                    {programme.is_primary ? "" : " (second programme)"}
                  </p>
                  <StatusBadge tone={toneForStatus(programme.progression_status)} dot={false}>
                    {humaniseStatus(programme.progression_status)}
                  </StatusBadge>
                </div>
                <dl className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <Field
                    label="CGPA"
                    value={programme.cgpa !== null ? programme.cgpa.toFixed(2) : null}
                  />
                  <Field
                    label="Credits"
                    value={`${number(programme.credits_earned)} of ${number(programme.credits_required)}`}
                  />
                  <Field label="Entry route" value={humaniseStatus(programme.entry_route)} />
                  <Field
                    label="Sponsorship"
                    value={
                      programme.sponsor_name
                        ? `${humaniseStatus(programme.sponsorship)} — ${programme.sponsor_name}`
                        : humaniseStatus(programme.sponsorship)
                    }
                  />
                  <Field label="Started" value={date(programme.started_on)} />
                  <Field
                    label="Expected completion"
                    value={date(programme.expected_completion_on)}
                  />
                  <Field
                    label="Outstanding retakes"
                    value={number(programme.outstanding_retakes)}
                  />
                </dl>
              </li>
            ))}
          </ul>
        )}
      </section>

      {timeOff ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Time away from study</h2>
          <div className="bg-card rounded-lg border p-4">
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Dead semesters taken" value={number(timeOff.dead_semesters)} />
              <Field label="Dead years taken" value={number(timeOff.dead_years)} />
              <Field label="Leaves of absence" value={number(timeOff.leaves_of_absence)} />
              <Field
                label="Semesters used"
                value={`${number(timeOff.semesters_enrolled)} of ${number(timeOff.semesters_permitted)}`}
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
                "Within the maximum period of study your programme allows."}
            </p>
          </div>
        </section>
      ) : null}

      {clearance.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Graduation clearance</h2>
          <ul className="divide-border divide-y text-sm">
            {clearance.map((office) => (
              <li
                key={office.id}
                className="flex flex-wrap items-baseline justify-between gap-x-4 py-2"
              >
                <span>
                  {humaniseStatus(office.office)}
                  {office.obligation_note ? (
                    <span className="text-muted-foreground block text-xs">
                      {office.obligation_note}
                    </span>
                  ) : null}
                </span>
                <StatusBadge tone={toneForStatus(office.status)} dot={false}>
                  {humaniseStatus(office.status)}
                </StatusBadge>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground text-xs leading-relaxed">
            Every office has to clear you before you can graduate. They are
            listed together so you can start on the slow ones — the library and
            the hall of residence — rather than discovering them in the week
            the list closes.
          </p>
        </section>
      ) : null}
    </PortalShell>
  )
}

function Field({
  label,
  value,
  restricted = false,
  mono = false,
}: {
  label: string
  value: string | number | null | undefined
  restricted?: boolean
  mono?: boolean
}) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd
        className={
          restricted
            ? "text-muted-foreground mt-0.5 text-sm italic"
            : mono
              ? "mt-0.5 font-mono text-sm break-words"
              : "mt-0.5 text-sm break-words"
        }
      >
        {restricted ? "Restricted" : (value ?? "—")}
      </dd>
    </div>
  )
}
