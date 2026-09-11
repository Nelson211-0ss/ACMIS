import * as Icons from "lucide-react"
import Link from "next/link"
import { notFound } from "next/navigation"

import { ApiError } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { NotPermitted } from "@acmis/ui/components/empty-state"
import { date, humaniseStatus } from "@acmis/ui/lib/format"

import { AdmissionsShell } from "@/components/shell"
import { APP } from "@/lib/config"

/**
 * One application.
 *
 * Two things this page does that are worth pointing at:
 *
 * **Masked fields are named, not blanked.** The API withholds an applicant's
 * disability disclosure and national ID from most readers and returns
 * `masked_fields` saying so. A blank cell reads as "not recorded"; "Restricted"
 * reads as what it is.
 *
 * **Actions come from `capabilities`, not from a permission check here.** The
 * server decided; this renders its answer. A button that appears and then 403s
 * is worse than no button.
 */

export default async function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const institution = await client.public.institution().catch(() => null)

  let envelope
  try {
    envelope = await client.admissions.application(id)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    if (error instanceof ApiError && error.isForbidden) {
      return (
        <AdmissionsShell user={user} institution={institution} currentPath="/applications">
          <NotPermitted what="this application" />
        </AdmissionsShell>
      )
    }
    throw error
  }

  const application = envelope.data as typeof envelope.data & {
    applicant: Record<string, string | null>
    choices: Array<Record<string, unknown>>
  }
  const masked = new Set(envelope.masked_fields)
  const can = (action: string) =>
    envelope.capabilities.find((c) => c.action === action)?.allowed ?? false

  const applicant = application.applicant ?? {}
  const fullName = [applicant.given_names, applicant.other_names, applicant.surname]
    .filter(Boolean)
    .join(" ")

  return (
    <AdmissionsShell user={user} institution={institution} currentPath="/applications">
      <PageHeader
        icon={<Icons.FileText />}
        title={fullName || application.number}
        description={
          <>
            Application {application.number} · {humaniseStatus(application.status)}
            {application.is_late ? " · submitted late" : ""}
          </>
        }
        breadcrumbs={
          <nav className="text-muted-foreground text-xs" aria-label="Breadcrumb">
            <Link href="/applications" className="hover:text-foreground underline">
              Applications
            </Link>
            <span aria-hidden> / </span>
            <span>{application.number}</span>
          </nav>
        }
        actions={
          <>
            <StatusBadge tone={toneForStatus(application.status)}>
              {humaniseStatus(application.status)}
            </StatusBadge>
            {can("application:score") ? (
              <button className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-3 py-1.5 text-sm font-medium">
                Record interview score
              </button>
            ) : null}
          </>
        }
      />

      {masked.size > 0 ? (
        <p className="border-border/70 bg-muted/40 text-muted-foreground rounded-lg border px-3 py-2 text-xs">
          <Icons.EyeOff className="mr-1.5 inline size-3.5" aria-hidden />
          {masked.size} field{masked.size === 1 ? "" : "s"} on this record
          {masked.size === 1 ? " is" : " are"} withheld from your role:{" "}
          {[...masked].join(", ").replace(/_/g, " ")}. Every read of them is logged against the
          reader.
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="bg-card shadow-card space-y-3 rounded-lg p-4 lg:col-span-2">
          <h2 className="text-base font-semibold">Applicant</h2>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <Field label="Full name" value={fullName} />
            <Field
              label="Date of birth"
              value={date(applicant.date_of_birth, institution?.locale)}
            />
            <Field label="Sex" value={humaniseStatus(applicant.sex)} />
            <Field label="Nationality" value={applicant.nationality} />
            <Field label="District of origin" value={applicant.district_of_origin} />
            <Field label="Email" value={applicant.email} />
            <Field label="Phone" value={applicant.phone} />
            <Field
              label="National ID"
              value={applicant.national_id}
              restricted={masked.has("national_id")}
            />
            <Field
              label="Disability"
              value={applicant.disability}
              restricted={masked.has("disability_detail") || masked.has("disability")}
            />
          </dl>
        </section>

        <section className="bg-card shadow-card space-y-3 rounded-lg p-4">
          <h2 className="text-base font-semibold">Scoring</h2>
          <dl className="space-y-3 text-sm">
            <Field label="Aggregate" value={application.aggregate_score?.toFixed(2) ?? null} />
            <Field label="Final score" value={application.final_score?.toFixed(2) ?? null} />
            <Field
              label="Waitlist position"
              value={application.waitlist_position?.toString() ?? null}
            />
            <Field
              label="Fee"
              value={
                application.fee_settled_at
                  ? `Settled ${date(application.fee_settled_at, institution?.locale)}`
                  : "Outstanding"
              }
            />
          </dl>
          <p className="text-muted-foreground border-t pt-3 text-xs leading-relaxed">
            The weights used to compute this score are copied onto the application when it is
            scored. A score recomputed under a later year&rsquo;s weights is not the score the
            candidate was ranked on.
          </p>
        </section>
      </div>

      <section className="bg-card shadow-card rounded-lg p-4">
        <h2 className="text-base font-semibold">Programme choices</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Ranked by the applicant. Eligibility was computed at submission against the requirements
          in force then.
        </p>
        <ol className="mt-3 space-y-2">
          {(application.choices ?? []).map((choice) => {
            const eligible = choice.is_eligible as boolean | null
            const reasons = (choice.ineligibility_reasons ?? []) as string[]
            return (
              <li
                key={String(choice.id)}
                className="flex flex-wrap items-start justify-between gap-3 rounded-md border p-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    Choice {String(choice.rank)}
                    <span className="text-muted-foreground ml-2 font-mono text-xs">
                      {String(choice.programme_intake_id).slice(0, 8)}
                    </span>
                  </p>
                  {reasons.length > 0 ? (
                    <ul className="text-warning-foreground mt-1 list-inside list-disc text-xs">
                      {reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {eligible === null ? (
                    <StatusBadge tone="neutral">Not assessed</StatusBadge>
                  ) : eligible ? (
                    <StatusBadge tone="success">Eligible</StatusBadge>
                  ) : (
                    <StatusBadge tone="danger">Not eligible</StatusBadge>
                  )}
                  {choice.outcome ? (
                    <StatusBadge tone={toneForStatus(String(choice.outcome))}>
                      {humaniseStatus(String(choice.outcome))}
                    </StatusBadge>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ol>
      </section>

      {application.decision_reason ? (
        <section className="bg-card shadow-card rounded-lg p-4">
          <h2 className="text-base font-semibold">Decision</h2>
          <p className="text-muted-foreground mt-1 text-xs">
            {date(application.decided_at, institution?.locale)}
          </p>
          <p className="mt-2 text-sm leading-relaxed">{application.decision_reason}</p>
        </section>
      ) : null}
    </AdmissionsShell>
  )
}

function Field({
  label,
  value,
  restricted = false,
}: {
  label: string
  value?: string | null
  restricted?: boolean
}) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5">
        {restricted ? (
          <span
            className="text-muted-foreground text-sm italic"
            title="Your role does not include this field."
          >
            Restricted
          </span>
        ) : (
          (value ?? <span className="text-muted-foreground">—</span>)
        )}
      </dd>
    </div>
  )
}
