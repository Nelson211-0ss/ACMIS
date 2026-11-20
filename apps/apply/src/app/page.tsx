import * as Icons from "lucide-react"
import Link from "next/link"

import { attempt } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataUnavailable, EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge } from "@acmis/ui/components/status-badge"
import { date, relativeTime } from "@acmis/ui/lib/format"

import { ApplyShell } from "@/components/shell"
import { APP } from "@/lib/config"
import { meaningOf } from "@/lib/status"

export const metadata = { title: "My applications" }

/**
 * The applicant's home.
 *
 * Ordered by what the reader came to find out. An applicant opens this screen
 * for one reason — *where does my application stand* — so the status and what
 * it means come before anything else, and the things needing their attention
 * are separated from the things that do not.
 *
 * It is deliberately not a dashboard of figures. There is nothing to count
 * here: one person has one or two applications, and a row of tiles reading
 * "1" would be decoration pretending to be information.
 */
export default async function MyApplicationsPage({
  searchParams,
}: {
  searchParams: Promise<{ welcome?: string }>
}) {
  const { welcome } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institutionCall, applicationsCall, schemesCall] = await Promise.all([
    attempt(client.public.institution()),
    attempt(client.admissions.myApplications({ limit: 20 }), "the admissions service"),
    attempt(client.public.admissionSchemes(), "the admissions service"),
  ])

  const institution = institutionCall.data
  const applications = applicationsCall.data?.items ?? []
  const schemes = schemesCall.data ?? []
  const schemeById = new Map(schemes.map((s) => [s.id, s]))

  const needsYou = applications.filter((a) => meaningOf(a.status).yours)

  return (
    <ApplyShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.FileText />}
        eyebrow={user.username ? `Application number ${user.username}` : undefined}
        title="My applications"
        description="Everything you have started, and where each one stands. Quote your application number whenever you contact the admissions office."
        actions={
          <Link
            href="/apply"
            className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex min-h-10 items-center gap-1.5 rounded-md px-3.5 text-sm font-medium transition-colors"
          >
            <Icons.FilePlus className="size-4" aria-hidden />
            Start an application
          </Link>
        }
      />

      {welcome ? (
        <p className="border-module/40 bg-module/5 flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm">
          <Icons.PartyPopper className="text-module mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            <strong className="font-semibold">Your account is ready.</strong> Your application
            number is <span className="font-mono text-[13px]">{user.username}</span> — it is also
            your username, and it has been emailed to you. Start an application when you are ready;
            you can save and come back.
          </span>
        </p>
      ) : null}

      {/* Checked before the empty case: an applicant who is told "you have no
          applications" when the service is merely down may well conclude their
          work was lost and start again. */}
      {applicationsCall.problem ? (
        <DataUnavailable unavailable={applicationsCall.problem} what="your applications" />
      ) : applications.length === 0 ? (
        <EmptyState
          title="You have not started an application yet"
          reason={
            schemes.length > 0
              ? "Pick a cycle and a programme, and you can fill the rest in a piece at a time."
              : "No admission cycle is open at the moment. It is worth checking back before the next intake."
          }
          icon={<Icons.FilePlus className="size-8" />}
          action={
            schemes.length > 0 ? (
              <Link
                href="/apply"
                className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex min-h-10 items-center gap-1.5 rounded-md px-3.5 text-sm font-medium"
              >
                Start an application
              </Link>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-6">
          {needsYou.length > 0 ? (
            <p className="border-warning/40 bg-warning/10 flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm">
              <Icons.AlertTriangle
                className="text-warning-foreground dark:text-warning mt-0.5 size-4 shrink-0"
                aria-hidden
              />
              <span>
                {needsYou.length === 1
                  ? "One application is waiting on you."
                  : `${needsYou.length} applications are waiting on you.`}{" "}
                Everything else is with the admissions office.
              </span>
            </p>
          ) : null}

          <ul className="space-y-3">
            {applications.map((application) => {
              const meaning = meaningOf(application.status)
              const scheme = schemeById.get(application.scheme_id)
              return (
                <li key={application.id}>
                  <Link
                    href={`/applications/${application.id}`}
                    className="bg-card shadow-card hover:shadow-card-hover group block rounded-lg p-4 transition-shadow"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-title text-base">{scheme?.name ?? "Application"}</p>
                        <p className="text-muted-foreground mt-0.5 font-mono text-xs">
                          {application.number}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <StatusBadge tone={meaning.tone}>{meaning.label}</StatusBadge>
                        <Icons.ChevronRight
                          className="text-muted-foreground size-4 transition-transform group-hover:translate-x-0.5"
                          aria-hidden
                        />
                      </div>
                    </div>

                    <p className="mt-2.5 text-sm leading-relaxed">{meaning.meaning}</p>
                    <p className="text-muted-foreground mt-1 text-sm leading-relaxed">
                      <span className="text-foreground font-medium">
                        {meaning.yours ? "Your move:" : "Next:"}
                      </span>{" "}
                      {meaning.next}
                    </p>

                    <p className="text-muted-foreground mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                      <span>Started {relativeTime(application.created_at)}</span>
                      {application.submitted_at ? (
                        <span>
                          · Submitted {date(application.submitted_at, institution?.locale)}
                        </span>
                      ) : null}
                      {scheme ? (
                        <span>· Closes {date(scheme.closes_at, institution?.locale)}</span>
                      ) : null}
                    </p>
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </ApplyShell>
  )
}
