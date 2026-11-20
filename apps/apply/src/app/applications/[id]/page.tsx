import * as Icons from "lucide-react"
import { notFound, redirect } from "next/navigation"
import { revalidatePath } from "next/cache"

import { ApiError, attempt } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataUnavailable, RuleRefused } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { RecordTrail } from "@acmis/ui/components/record-trail"
import { StatusBadge } from "@acmis/ui/components/status-badge"
import { date, dateTime, money } from "@acmis/ui/lib/format"

import { ApplyShell } from "@/components/shell"
import { APP } from "@/lib/config"
import { meaningOf } from "@/lib/status"

export const metadata = { title: "My application" }

/**
 * One application, from the applicant's side.
 *
 * The office's version of this screen is a review tool — scores, flags,
 * reviewer notes. None of that belongs here, and not only because the policy
 * masks it: what an applicant needs is the answer to "what is happening, and
 * is it my turn". So the page leads with the state and what it means, and the
 * record itself follows underneath.
 *
 * Submitting is the one irreversible thing an applicant can do in ACMIS, so
 * it says what it costs before the button rather than after.
 */
export default async function ApplicationPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<{ refused?: string }>
}) {
  const { id } = await params
  const { refused } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institutionCall, applicationCall, schemesCall] = await Promise.all([
    attempt(client.public.institution()),
    attempt(client.admissions.application(id), "your application"),
    attempt(client.public.admissionSchemes(), "the admissions service"),
  ])

  if (applicationCall.problem?.kind === "missing") notFound()

  const institution = institutionCall.data
  const envelope = applicationCall.data
  const application = envelope?.data
  const scheme = application
    ? (schemesCall.data ?? []).find((s) => s.id === application.scheme_id)
    : undefined

  async function submit() {
    "use server"

    const authed = await acmis(APP)
    try {
      await authed.admissions.submitApplication(id)
    } catch (error) {
      // A rule refusal is the expected failure here — an unpaid fee, a missing
      // document — and it is the API's message that explains which. Anything
      // else is a real fault and goes to the error boundary.
      if (error instanceof ApiError && error.isRuleViolation) {
        redirect(`/applications/${id}?refused=${encodeURIComponent(error.message)}`)
      }
      throw error
    }
    revalidatePath(`/applications/${id}`)
    redirect(`/applications/${id}`)
  }

  if (applicationCall.problem) {
    return (
      <ApplyShell user={user} institution={institution} currentPath="/">
        <PageHeader
          icon={<Icons.FileText />}
          breadcrumbs={<RecordTrail items={[{ label: "My applications", href: "/" }]} />}
          title="Your application"
        />
        <DataUnavailable unavailable={applicationCall.problem} what="this application" />
      </ApplyShell>
    )
  }

  if (!application) notFound()

  const meaning = meaningOf(application.status)

  return (
    <ApplyShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.FileText />}
        breadcrumbs={
          <RecordTrail
            items={[{ label: "My applications", href: "/" }]}
            current={application.number}
          />
        }
        eyebrow={scheme?.name}
        title={scheme?.name ?? "Your application"}
        description={`Application ${application.number}. Quote this number whenever you contact the admissions office.`}
        actions={<StatusBadge tone={meaning.tone}>{meaning.label}</StatusBadge>}
      />

      {refused ? (
        <RuleRefused
          message="This application cannot be submitted yet."
          details={<p>{refused}</p>}
        />
      ) : null}

      {/* The state, in words, before anything else on the page. */}
      <section
        className={
          meaning.yours
            ? "border-warning/40 bg-warning/10 rounded-lg border p-4"
            : "bg-card shadow-card rounded-lg p-4"
        }
      >
        <h2 className="flex items-center gap-2 text-base">
          {meaning.yours ? (
            <Icons.AlertTriangle className="text-warning-text size-4 shrink-0" aria-hidden />
          ) : (
            <Icons.Info className="text-module size-4 shrink-0" aria-hidden />
          )}
          {meaning.label}
        </h2>
        <p className="mt-2 text-sm leading-relaxed">{meaning.meaning}</p>
        <p className="text-muted-foreground mt-1.5 text-sm leading-relaxed">
          <span className="text-foreground font-medium">
            {meaning.yours ? "Your move:" : "Next:"}
          </span>{" "}
          {meaning.next}
        </p>
        {application.decision_reason ? (
          <p className="mt-3 text-sm leading-relaxed">
            <span className="font-medium">Reason given:</span> {application.decision_reason}
          </p>
        ) : null}
      </section>

      <section className="bg-card shadow-card rounded-lg p-4">
        <h2 className="text-base">The record</h2>
        <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <div>
            <dt className="eyebrow">Application number</dt>
            <dd className="mt-0.5 font-mono text-sm">{application.number}</dd>
          </div>
          <div>
            <dt className="eyebrow">Started</dt>
            <dd className="mt-0.5 text-sm">
              {dateTime(application.created_at, institution?.locale, institution?.timezone)}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">Submitted</dt>
            <dd className="mt-0.5 text-sm">
              {application.submitted_at
                ? dateTime(application.submitted_at, institution?.locale, institution?.timezone)
                : "Not yet"}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">Application fee</dt>
            <dd className="mt-0.5 text-sm">
              {application.fee_settled_at
                ? `Received ${date(application.fee_settled_at, institution?.locale)}`
                : scheme && scheme.application_fee_minor > 0
                  ? `${money(scheme.application_fee_minor, scheme.currency, institution?.locale)} — not yet received`
                  : "None payable"}
            </dd>
          </div>
          {scheme ? (
            <div>
              <dt className="eyebrow">Cycle closes</dt>
              <dd className="mt-0.5 text-sm">
                {date(scheme.closes_at, institution?.locale)}
                {application.is_late ? " · submitted late" : ""}
              </dd>
            </div>
          ) : null}
        </dl>
      </section>

      {application.status === "draft" ? (
        <section className="bg-card shadow-card rounded-lg p-4">
          <h2 className="text-base">Send it to the admissions office</h2>
          <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-relaxed">
            Once you submit, you cannot change this application yourself — the admissions office
            can, if you ask them and they agree. Check your programme choices before you do.
            {scheme && scheme.application_fee_minor > 0
              ? ` The ${money(scheme.application_fee_minor, scheme.currency, institution?.locale)} fee becomes payable on submission; your application is not reviewed until it clears.`
              : ""}
          </p>
          <form action={submit} className="mt-4">
            <button
              type="submit"
              className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex min-h-11 items-center gap-2 rounded-lg px-4 text-sm font-medium transition-colors"
            >
              <Icons.Send className="size-4" aria-hidden />
              Submit my application
            </button>
          </form>
        </section>
      ) : null}
    </ApplyShell>
  )
}
