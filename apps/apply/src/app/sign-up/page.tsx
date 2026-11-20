import * as Icons from "lucide-react"
import { redirect } from "next/navigation"

import { attempt } from "@acmis/api-client"
import { acmisPublic, readSession } from "@acmis/auth/server"
import { date } from "@acmis/ui/lib/format"

import { SignUpForm } from "./form"
import { openNow } from "@/lib/schemes"
import { APP } from "@/lib/config"

export const metadata = { title: "Create an account" }

export default async function SignUpPage() {
  if (await readSession()) redirect("/")

  const client = await acmisPublic(APP)
  const [institutionCall, schemesCall] = await Promise.all([
    attempt(client.public.institution()),
    attempt(client.public.admissionSchemes(), "the admissions service"),
  ])
  const institution = institutionCall.data
  // `openNow` sorts by deadline, so the first is the one to quote.
  const schemes = openNow(schemesCall.data ?? [])
  const closing = schemes[0]

  return (
    <div className="bg-muted/40 relative min-h-dvh overflow-hidden px-4 py-10" data-module="apply">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[26rem] bg-[radial-gradient(65%_100%_at_50%_0%,var(--module)_0%,transparent_70%)] opacity-[0.10]"
      />

      <div className="mx-auto w-full max-w-xl">
        <div className="mb-7 text-center">
          {institution?.crest_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={institution.crest_url}
              alt=""
              className="bg-card shadow-card mx-auto mb-4 size-16 rounded-2xl object-contain p-2.5"
            />
          ) : null}
          <h1 className="font-display text-balance text-[1.6rem] font-extrabold leading-tight tracking-tight">
            Apply to {institution?.short_name ?? institution?.name ?? "study"}
          </h1>
          <p className="text-muted-foreground mx-auto mt-2 max-w-md text-sm leading-relaxed">
            Creating an account takes a minute. You can then fill in your application a piece at a
            time and come back to it — nothing is sent to the admissions office until you submit it.
          </p>
        </div>

        {/* The deadline belongs on the screen where somebody decides whether to
            start, not three screens later where it becomes a reproach. */}
        {closing ? (
          <p className="bg-card shadow-card text-muted-foreground mb-5 flex items-start gap-2 rounded-xl px-4 py-3 text-sm">
            <Icons.CalendarClock className="text-module mt-0.5 size-4 shrink-0" aria-hidden />
            <span>
              <span className="text-foreground font-medium">{closing.name}</span> closes on{" "}
              {date(closing.closes_at, institution?.locale)}.
              {schemes.length > 1
                ? ` ${schemes.length - 1} other cycle${schemes.length > 2 ? "s are" : " is"} also open.`
                : ""}
            </span>
          </p>
        ) : schemesCall.problem ? (
          <p className="bg-card shadow-card text-muted-foreground mb-5 flex items-start gap-2 rounded-xl px-4 py-3 text-sm">
            <Icons.AlertTriangle className="text-warning-text mt-0.5 size-4 shrink-0" aria-hidden />
            <span>
              We could not load the open cycles just now. You can still create an account — the
              deadlines will be on your dashboard.
            </span>
          </p>
        ) : (
          <p className="bg-card shadow-card text-muted-foreground mb-5 flex items-start gap-2 rounded-xl px-4 py-3 text-sm">
            <Icons.CalendarOff className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span>
              No admission cycle is open at the moment, so accounts cannot be created yet. It is
              worth checking back before the next intake.
            </span>
          </p>
        )}

        <SignUpForm />
      </div>
    </div>
  )
}
