import * as Icons from "lucide-react"
import { notFound, redirect } from "next/navigation"

import { attempt } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataUnavailable, EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { RecordTrail } from "@acmis/ui/components/record-trail"
import { date, money } from "@acmis/ui/lib/format"

import { ApplyShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Choose your programmes" }

/**
 * Ranking programme choices.
 *
 * ## Why ranked selects rather than a drag-and-drop list
 *
 * Preference order decides what an applicant is offered when their first
 * choice fills up, so it is not a detail — it is the most consequential thing
 * on the page. A list you reorder by dragging expresses that beautifully on a
 * laptop and is close to unusable on a phone with a cracked screen, which is
 * where a good share of these are filled in. Three labelled selects say the
 * same thing, work without JavaScript, and can be read back by a screen
 * reader in the order they mean.
 *
 * The cut-off from the last cycle is shown beside each programme. It is the
 * number applicants ring the office for one at a time, and withholding it
 * does not make a weak choice less likely — it makes it less informed.
 */
export default async function ChooseProgrammesPage({
  params,
  searchParams,
}: {
  params: Promise<{ schemeId: string }>
  searchParams: Promise<{ error?: string }>
}) {
  const { schemeId } = await params
  const { error } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institutionCall, schemesCall, intakesCall] = await Promise.all([
    attempt(client.public.institution()),
    attempt(client.public.admissionSchemes(), "the admissions service"),
    attempt(client.public.schemeIntakes(schemeId), "the programme list"),
  ])

  const institution = institutionCall.data
  const scheme = (schemesCall.data ?? []).find((s) => s.id === schemeId)
  // An open scheme is the only kind this journey can serve, and the public
  // endpoint only returns open ones — so a miss here is genuinely "not found"
  // rather than "not yet loaded", unless the call itself failed.
  if (!scheme && schemesCall.ok) notFound()

  const intakes = intakesCall.data ?? []
  const maxChoices = Math.min(scheme?.max_programme_choices ?? 3, 3)

  async function startApplication(formData: FormData) {
    "use server"

    const chosen = Array.from({ length: 3 }, (_, i) =>
      String(formData.get(`choice_${i + 1}`) ?? ""),
    ).filter(Boolean)

    if (chosen.length === 0) {
      redirect(`/apply/${schemeId}?error=none`)
    }
    if (new Set(chosen).size !== chosen.length) {
      redirect(`/apply/${schemeId}?error=duplicate`)
    }

    const authed = await acmis(APP)
    const application = await authed.admissions.startApplication({
      scheme_id: schemeId,
      programme_intake_ids: chosen,
    })
    redirect(`/applications/${application.id}`)
  }

  return (
    <ApplyShell user={user} institution={institution} currentPath="/apply">
      <PageHeader
        icon={<Icons.ListOrdered />}
        breadcrumbs={
          <RecordTrail
            items={[{ label: "Start an application", href: "/apply" }]}
            current={scheme?.name ?? "Programmes"}
          />
        }
        title="Choose your programmes"
        description={
          scheme
            ? `Rank up to ${maxChoices} in the order you would most like them. If your first choice fills up, you are considered for your second, and so on.`
            : "Rank your programmes in order of preference."
        }
      />

      {error ? (
        <p
          role="alert"
          className="bg-destructive/10 text-destructive flex items-start gap-2 rounded-lg px-4 py-3 text-sm"
        >
          <Icons.AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            {error === "duplicate"
              ? "You have chosen the same programme twice. Each choice must be different."
              : "Choose at least one programme."}
          </span>
        </p>
      ) : null}

      {intakesCall.problem ? (
        <DataUnavailable unavailable={intakesCall.problem} what="the programme list" />
      ) : intakes.length === 0 ? (
        <EmptyState
          title="This cycle has no programmes yet"
          reason="A scheme cannot be applied to until the admissions office adds its programme intakes. This is worth reporting to them."
          icon={<Icons.BookOpen className="size-8" />}
        />
      ) : (
        <form action={startApplication} className="space-y-6">
          <div className="space-y-4">
            {Array.from({ length: maxChoices }, (_, index) => {
              const n = index + 1
              const label = ["First choice", "Second choice", "Third choice"][index]
              return (
                <div key={n} className="bg-card shadow-card space-y-1.5 rounded-lg p-4">
                  <label htmlFor={`choice_${n}`} className="text-sm font-medium">
                    {label}{" "}
                    {n > 1 ? (
                      <span className="text-muted-foreground font-normal">(optional)</span>
                    ) : null}
                  </label>
                  <select
                    id={`choice_${n}`}
                    name={`choice_${n}`}
                    defaultValue=""
                    required={n === 1}
                    className="field px-3"
                  >
                    <option value="">
                      {n === 1 ? "Select a programme…" : "No further choice"}
                    </option>
                    {intakes.map((intake) => (
                      <option key={intake.programme_intake_id} value={intake.programme_intake_id}>
                        {intake.programme_name} ({intake.award_abbreviation})
                      </option>
                    ))}
                  </select>
                </div>
              )
            })}
          </div>

          <button
            type="submit"
            className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-colors sm:w-auto"
          >
            <Icons.ArrowRight className="size-4" aria-hidden />
            Start my application
          </button>

          <p className="text-muted-foreground text-sm">
            Starting an application does not submit it, and the{" "}
            {scheme && scheme.application_fee_minor > 0
              ? money(scheme.application_fee_minor, scheme.currency, institution?.locale)
              : "application"}{" "}
            fee is not due until you do.
            {scheme ? ` This cycle closes on ${date(scheme.closes_at, institution?.locale)}.` : ""}
          </p>
        </form>
      )}

      {/* The reference table. Separate from the form on purpose: these are the
          facts somebody weighs before choosing, and interleaving them with the
          selects made both harder to read. */}
      {intakes.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-base">What each programme asks for</h2>
          <ul className="space-y-2">
            {intakes.map((intake) => (
              <li key={intake.programme_intake_id} className="bg-card shadow-card rounded-lg p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <p className="text-title text-sm">{intake.programme_name}</p>
                  <p className="text-muted-foreground font-mono text-xs">{intake.programme_code}</p>
                </div>
                <p className="text-muted-foreground mt-1 text-xs">
                  {intake.award_title} · {intake.duration_semesters} semesters ·{" "}
                  {intake.approved_intake} places
                </p>
                {intake.entry_requirements ? (
                  <p className="mt-2 text-sm leading-relaxed">{intake.entry_requirements}</p>
                ) : null}
                <p className="text-muted-foreground mt-2 text-xs">
                  {intake.previous_cutoff !== null
                    ? `Last cycle the lowest admitted score was ${intake.previous_cutoff}.`
                    : "No cut-off from a previous cycle yet."}
                  {intake.tuition_per_semester_minor > 0
                    ? ` Tuition ${money(
                        intake.tuition_per_semester_minor,
                        scheme?.currency ?? institution?.currency ?? "SSP",
                        institution?.locale,
                      )} a semester.`
                    : ""}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </ApplyShell>
  )
}
