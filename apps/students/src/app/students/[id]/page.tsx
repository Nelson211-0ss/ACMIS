import * as Icons from "lucide-react"
import Link from "next/link"
import { notFound } from "next/navigation"

import { ApiError } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { Meter } from "@acmis/ui/components/chart-frame"
import { NotPermitted } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money, number, surnameFirst } from "@acmis/ui/lib/format"

import { StudentsShell } from "@/components/shell"
import { APP } from "@/lib/config"

/**
 * One student's record.
 *
 * Pulls from three modules — the student record, their ledger and their
 * clearance — because that is the question staff actually have at the counter:
 * can this person register, sit, or graduate. Each of those depends on all
 * three, and a page that shows only the record sends the clerk to two more
 * screens.
 */
export default async function StudentPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const institution = await client.public.institution().catch(() => null)

  let envelope
  try {
    envelope = await client.students.get(id)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    if (error instanceof ApiError && error.isForbidden) {
      return (
        <StudentsShell user={user} institution={institution} currentPath="/students">
          <NotPermitted what="this student's record" />
        </StudentsShell>
      )
    }
    throw error
  }

  const student = envelope.data
  const masked = new Set(envelope.masked_fields)
  const can = (action: string) =>
    envelope.capabilities.find((c) => c.action === action)?.allowed ?? false

  // Both are permission-gated on the API. A refusal here is normal — a hall
  // warden may read the record and not the ledger — so it degrades to "not
  // shown" rather than failing the page.
  const [statement, clearance] = await Promise.all([
    can("finance:read_statement")
      ? client.finance.statement(id).catch(() => null)
      : Promise.resolve(null),
    client.students.clearance(id).catch(() => null),
  ])

  const primary = student.programmes.find((p) => p.is_primary)
  const activeHolds = student.holds.filter((h) => !h.cleared_at)

  return (
    <StudentsShell user={user} institution={institution} currentPath="/students">
      <PageHeader
        title={surnameFirst(student)}
        description={
          <>
            <span className="font-mono">{student.student_number}</span>
            {primary ? (
              <>
                {" · "}Year {primary.current_year_of_study}, semester{" "}
                {primary.current_semester_number}
                {" · "}
                {humaniseStatus(primary.sponsorship)} sponsorship
              </>
            ) : null}
          </>
        }
        breadcrumbs={
          <nav className="text-muted-foreground text-xs" aria-label="Breadcrumb">
            <Link href="/students" className="hover:text-foreground underline">
              Students
            </Link>
            <span aria-hidden> / </span>
            <span>{student.student_number}</span>
          </nav>
        }
        actions={
          <StatusBadge tone={toneForStatus(student.status)}>
            {humaniseStatus(student.status)}
          </StatusBadge>
        }
      />

      {activeHolds.length > 0 ? (
        <section className="border-warning/40 bg-warning/10 rounded-lg border p-4">
          <h2 className="text-warning-foreground flex items-center gap-2 text-sm font-semibold">
            <Icons.Lock className="size-4" aria-hidden />
            {activeHolds.length} hold{activeHolds.length === 1 ? "" : "s"} on this record
          </h2>
          <ul className="mt-2 space-y-1.5">
            {activeHolds.map((hold, index) => (
              <li key={`${hold.kind}-${index}`} className="text-sm">
                <span className="font-medium capitalize">{hold.kind.replace(/_/g, " ")}</span>
                {" — "}
                {hold.reason}
                {hold.placed_at ? (
                  <span className="text-muted-foreground text-xs">
                    {" "}
                    ({date(hold.placed_at, institution?.locale)})
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-2 text-xs">
            Each hold is cleared by the office that placed it, so a finalist can
            be told which desk is holding them up rather than just
            &ldquo;not cleared&rdquo;.
          </p>
        </section>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="bg-card space-y-3 rounded-lg border p-4 lg:col-span-2">
          <h2 className="text-base font-semibold">Bio-data</h2>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <Field label="Full name" value={`${student.given_names} ${student.other_names ?? ""} ${student.surname}`.replace(/\s+/g, " ")} />
            <Field
              label="Date of birth"
              value={date(student.date_of_birth, institution?.locale)}
            />
            <Field label="Sex" value={humaniseStatus(student.sex)} />
            <Field label="Nationality" value={student.nationality} />
            <Field label="District of origin" value={student.district_of_origin} />
            <Field label="Institutional email" value={student.email} />
            <Field label="Phone" value={student.phone} />
            <Field label="Residence" value={student.residence} />
            <Field
              label="National ID"
              value={student.national_id}
              restricted={masked.has("national_id")}
            />
            <Field
              label="Bank account"
              value={student.bank_account_number}
              restricted={masked.has("bank_account_number")}
            />
            <Field
              label="Next of kin"
              value={
                student.next_of_kin_name
                  ? `${student.next_of_kin_name} · ${student.next_of_kin_phone ?? ""}`
                  : null
              }
            />
            <Field
              label="Disability"
              value={student.disability}
              restricted={masked.has("disability_detail")}
            />
          </dl>
          {masked.size > 0 ? (
            <p className="text-muted-foreground border-t pt-3 text-xs">
              {masked.size} field{masked.size === 1 ? "" : "s"} withheld from your
              role. Special-category data is readable only with a specific grant,
              and every such read is logged against the reader.
            </p>
          ) : null}
        </section>

        <div className="space-y-4">
          {primary ? (
            <section className="bg-card space-y-4 rounded-lg border p-4">
              <h2 className="text-base font-semibold">Academic progress</h2>
              <div className="flex items-baseline gap-2">
                <span className="tabular text-3xl font-semibold">
                  {primary.cgpa !== null ? primary.cgpa.toFixed(2) : "—"}
                </span>
                <span className="text-muted-foreground text-sm">CGPA</span>
                <StatusBadge tone={toneForStatus(primary.progression_status)} className="ml-auto">
                  {humaniseStatus(primary.progression_status)}
                </StatusBadge>
              </div>
              <Meter
                label="Credit units earned"
                value={primary.credits_earned}
                max={primary.credits_required || 1}
                formatValue={(v) => number(v)}
              />
              {primary.outstanding_retakes > 0 ? (
                <p className="text-warning-foreground text-xs">
                  {primary.outstanding_retakes} outstanding retake
                  {primary.outstanding_retakes === 1 ? "" : "s"}. An award cannot
                  be classified until these are cleared.
                </p>
              ) : null}
              <dl className="space-y-2 border-t pt-3 text-sm">
                <Field label="Entry route" value={humaniseStatus(primary.entry_route)} />
                <Field
                  label="Started"
                  value={date(primary.started_on, institution?.locale)}
                />
                <Field
                  label="Expected completion"
                  value={date(primary.expected_completion_on, institution?.locale)}
                />
                {primary.sponsor_name ? (
                  <Field label="Sponsor" value={primary.sponsor_name} />
                ) : null}
              </dl>
            </section>
          ) : null}

          {statement ? (
            <section className="bg-card space-y-3 rounded-lg border p-4">
              <h2 className="text-base font-semibold">Fees</h2>
              <div className="flex items-baseline justify-between gap-2">
                <span
                  className={
                    statement.balance_minor > 0
                      ? "text-destructive tabular text-2xl font-semibold"
                      : "text-success tabular text-2xl font-semibold"
                  }
                >
                  {money(statement.balance_minor, statement.currency, institution?.locale)}
                </span>
                <span className="text-muted-foreground text-xs">
                  {statement.balance_minor > 0 ? "outstanding" : "cleared"}
                </span>
              </div>
              <dl className="space-y-1.5 text-xs">
                <Row
                  label="Invoiced"
                  value={money(
                    statement.total_invoiced_minor,
                    statement.currency,
                    institution?.locale,
                  )}
                />
                <Row
                  label="Paid"
                  value={money(statement.total_paid_minor, statement.currency, institution?.locale)}
                />
                <Row
                  label="Waived"
                  value={money(
                    statement.total_waived_minor,
                    statement.currency,
                    institution?.locale,
                  )}
                />
              </dl>
              <p className="text-muted-foreground border-t pt-2 text-xs">
                Recomputed from the ledger on every read. The entries are the
                authority; the cached balance is only a cache.
              </p>
            </section>
          ) : null}
        </div>
      </div>

      {clearance && clearance.length > 0 ? (
        <section className="bg-card rounded-lg border p-4">
          <h2 className="text-base font-semibold">Clearance</h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Each office signs independently. Graduation waits on the last one.
          </p>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {clearance.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-2 rounded-md border p-2.5"
              >
                <span className="text-sm capitalize">{item.office.replace(/_/g, " ")}</span>
                <StatusBadge tone={toneForStatus(item.status)}>
                  {humaniseStatus(item.status)}
                </StatusBadge>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </StudentsShell>
  )
}

function Field({
  label,
  value,
  restricted = false,
}: {
  label: string
  value?: string | number | null
  restricted?: boolean
}) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5">
        {restricted ? (
          <span className="text-muted-foreground text-sm italic">Restricted</span>
        ) : (
          (value ?? <span className="text-muted-foreground">—</span>)
        )}
      </dd>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="tabular font-medium">{value}</dd>
    </div>
  )
}
