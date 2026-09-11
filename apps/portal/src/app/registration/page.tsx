import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money, number } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

import { openRegistration, submitRegistration } from "./actions"
import { ActionForm } from "./form"

export const metadata = { title: "Registration" }

/**
 * Semester registration: what is on it, what is blocking it, what to do next.
 *
 * Registration is the gate everything else hangs off — course material,
 * examination cards, a mark sheet with your name on it — so the page leads
 * with the current semester's state and the reason it is not further along.
 * "Pending approval" and "you have not submitted it" are different problems
 * and a student who cannot tell them apart waits for the wrong thing.
 */
export default async function RegistrationPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester, record, registrations] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
    client.students.myRecord().catch(() => null),
    client.students.myRegistrations().catch(() => []),
  ])

  const student = record?.data
  const currency = institution?.currency ?? "UGX"
  const current = semester
    ? registrations.find((row) => row.semester_id === semester.id)
    : undefined
  const history = registrations.filter((row) => row.id !== current?.id)

  const [statement, blocks] = await Promise.all([
    client.finance.myStatement().catch(() => null),
    student ? client.finance.blocks(student.id).catch(() => null) : Promise.resolve(null),
  ])

  const registrationBlocks = (blocks?.blocks ?? []).filter((block) => block.gate === "registration")
  const holds = (student?.holds ?? []).filter((hold) => !hold.cleared_at)

  return (
    <PortalShell user={user} institution={institution} currentPath="/registration">
      <PageHeader
        icon={<Icons.ClipboardList />}
        title="Registration"
        description={
          semester
            ? `${semester.name}. Registration closes ${date(semester.registration_closes_on)}; after that a late fee applies and the course list is frozen.`
            : "No semester is open for registration at the moment."
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
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {registrationBlocks.length > 0 ? (
        <section className="border-warning/40 bg-warning/10 rounded-lg border p-4">
          <h2 className="text-warning-foreground text-sm font-semibold">
            Registration is blocked by an unpaid invoice
          </h2>
          <ul className="mt-2 space-y-2 text-sm">
            {registrationBlocks.map((block) => (
              <li key={`${block.invoice}-${block.rule}`}>
                Invoice <span className="font-mono text-xs">{block.invoice}</span> is{" "}
                {block.days_overdue} days overdue under {block.rule}.
                <span className="text-muted-foreground block text-xs">
                  Clears when: {block.clears_when}
                  {block.waivable ? " — or by an approved payment plan." : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {blocks?.protected_by_plan ? (
        <p className="text-success border-success/30 bg-success/10 rounded-lg border px-4 py-3 text-sm">
          An approved payment plan is holding your blocks off. Keep to the instalments and
          registration stays open.
        </p>
      ) : null}

      <section className="space-y-4">
        <h2 className="text-sm font-semibold">{semester ? semester.name : "Current semester"}</h2>

        {!semester ? (
          <EmptyState
            icon={<Icons.CalendarOff className="size-8" />}
            title="No semester is currently open"
            reason="Registration opens on the date published in the academic calendar. Until a semester is marked current there is nothing to register for."
          />
        ) : !current ? (
          <EmptyState
            icon={<Icons.ClipboardList className="size-8" />}
            title="You have not started registering"
            reason={`Open a registration for ${semester.name}, add your courses with your department, then submit it. Nothing counts until it is submitted and approved.`}
            action={
              student ? (
                <ActionForm
                  action={openRegistration}
                  label="Open my registration"
                  hidden={{ student_id: student.id, semester_id: semester.id }}
                />
              ) : undefined
            }
          />
        ) : (
          <div className="bg-card shadow-card space-y-4 rounded-lg p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <StatusBadge tone={toneForStatus(current.status)}>
                  {humaniseStatus(current.status)}
                </StatusBadge>
                {current.is_late ? (
                  <StatusBadge tone="warning" dot={false}>
                    Late
                  </StatusBadge>
                ) : null}
              </div>
              <p className="text-muted-foreground text-sm">
                {number(current.courses.length)} course
                {current.courses.length === 1 ? "" : "s"} · {number(current.total_credits)} credit
                units
                {current.retake_credits > 0
                  ? ` (${number(current.retake_credits)} on retakes)`
                  : ""}
              </p>
            </div>

            {current.courses.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No courses on it yet. Your department adds the courses for your year and semester;
                anything elective you choose yourself has to be added before you submit.
              </p>
            ) : (
              <ul className="divide-border divide-y text-sm">
                {current.courses.map((course) => (
                  <li key={course.id} className="flex items-baseline justify-between gap-4 py-2">
                    <span className="min-w-0">
                      <span className="font-mono text-xs">{course.code || "—"}</span>
                      <span className="ml-2">{course.title}</span>
                      {course.is_retake ? (
                        <span className="text-warning-foreground ml-2 text-xs">
                          retake, attempt {course.attempt_number}
                        </span>
                      ) : null}
                      {course.is_audit ? (
                        <span className="text-muted-foreground ml-2 text-xs">audit</span>
                      ) : null}
                    </span>
                    <span className="text-muted-foreground shrink-0 text-xs">
                      {humaniseStatus(course.category)} · {course.credit_units} CU
                    </span>
                  </li>
                ))}
              </ul>
            )}

            <dl className="text-muted-foreground grid grid-cols-2 gap-3 border-t pt-3 text-xs sm:grid-cols-4">
              <Fact label="Submitted" value={date(current.submitted_at)} />
              <Fact label="Approved" value={date(current.approved_at)} />
              <Fact label="Exam card" value={date(current.exam_card_issued_at)} />
              <Fact
                label="Fee balance"
                value={statement ? money(statement.balance_minor, currency) : "—"}
              />
            </dl>

            {current.status === "draft" ? (
              <div className="border-t pt-3">
                <ActionForm
                  action={submitRegistration}
                  label="Submit for approval"
                  hidden={{ registration_id: current.id }}
                  hint="Once submitted the course list is fixed until your department returns it to you."
                />
              </div>
            ) : current.status === "submitted" ? (
              <p className="text-muted-foreground border-t pt-3 text-sm">
                With your department for approval. Nothing further is needed from you; chase your
                head of department if it sits here past the close of the registration window.
              </p>
            ) : null}
          </div>
        )}
      </section>

      {history.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Earlier semesters</h2>
          <ul className="divide-border divide-y text-sm">
            {history.map((row) => (
              <li key={row.id} className="flex items-baseline justify-between gap-4 py-2">
                <span>
                  {row.semester_name ?? "Semester"}
                  <span className="text-muted-foreground ml-2 text-xs">
                    {number(row.courses.length)} courses · {number(row.total_credits)} CU
                  </span>
                </span>
                <StatusBadge tone={toneForStatus(row.status)} dot={false}>
                  {humaniseStatus(row.status)}
                </StatusBadge>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </PortalShell>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className="text-foreground mt-0.5 font-medium">{value}</dd>
    </div>
  )
}
