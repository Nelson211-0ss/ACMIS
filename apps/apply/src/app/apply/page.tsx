import * as Icons from "lucide-react"
import Link from "next/link"

import { attempt } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataUnavailable, EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { date, money } from "@acmis/ui/lib/format"

import { ApplyShell } from "@/components/shell"
import { openNow } from "@/lib/schemes"
import { APP } from "@/lib/config"

export const metadata = { title: "Start an application" }

/**
 * Choosing a cycle.
 *
 * Most institutions have one open at a time, in which case this is a single
 * card and one button. It is still a screen of its own rather than a silent
 * redirect: the fee and the closing date are commitments, and an applicant
 * should meet them before they start filling anything in, not after.
 */
export default async function ChooseSchemePage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institutionCall, schemesCall] = await Promise.all([
    attempt(client.public.institution()),
    attempt(client.public.admissionSchemes(), "the admissions service"),
  ])
  const institution = institutionCall.data
  // Status alone would offer a cycle whose deadline has passed; see `openNow`.
  const schemes = openNow(schemesCall.data ?? [])

  return (
    <ApplyShell user={user} institution={institution} currentPath="/apply">
      <PageHeader
        icon={<Icons.FilePlus />}
        title="Start an application"
        description="Choose the cycle you are applying under. You can save your application and come back to it as often as you like before the closing date."
      />

      {schemesCall.problem ? (
        <DataUnavailable unavailable={schemesCall.problem} what="the open cycles" />
      ) : schemes.length === 0 ? (
        <EmptyState
          title="Nothing is open at the moment"
          reason="Admission cycles open a few times a year. When one opens it will appear here, and on the institution's website."
          icon={<Icons.CalendarOff className="size-8" />}
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {schemes.map((scheme) => (
            <li key={scheme.id}>
              <Link
                href={`/apply/${scheme.id}`}
                className="bg-card shadow-card hover:shadow-card-hover group flex h-full flex-col rounded-lg p-4 transition-shadow"
              >
                <p className="text-title text-base">{scheme.name}</p>
                <p className="text-muted-foreground mt-0.5 font-mono text-xs">{scheme.code}</p>
                {scheme.description ? (
                  <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
                    {scheme.description}
                  </p>
                ) : null}

                <dl className="mt-auto space-y-1.5 pt-4 text-sm">
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-muted-foreground text-xs uppercase tracking-wide">
                      Closes
                    </dt>
                    <dd className="font-medium">{date(scheme.closes_at, institution?.locale)}</dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-muted-foreground text-xs uppercase tracking-wide">
                      Application fee
                    </dt>
                    <dd className="tabular font-medium">
                      {scheme.application_fee_minor > 0
                        ? money(scheme.application_fee_minor, scheme.currency, institution?.locale)
                        : "None"}
                    </dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-muted-foreground text-xs uppercase tracking-wide">
                      Programme choices
                    </dt>
                    <dd className="font-medium">Up to {scheme.max_programme_choices}</dd>
                  </div>
                </dl>

                <span className="text-module mt-4 inline-flex items-center gap-1 text-sm font-medium">
                  Choose programmes
                  <Icons.ArrowRight
                    className="size-4 transition-transform group-hover:translate-x-0.5"
                    aria-hidden
                  />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </ApplyShell>
  )
}
