"use client"

import { AlertTriangle, ArrowLeft, LayoutGrid, RotateCw, SearchX } from "lucide-react"
import Link from "next/link"
import type { ReactNode } from "react"

import { moduleUrl } from "@acmis/ui/lib/modules"
import { cn } from "@acmis/ui/lib/utils"

/**
 * The two pages nobody designs until the day they are needed.
 *
 * ## Why they fetch nothing
 *
 * Every other screen in ACMIS opens with `requireUser` and a call for the
 * institution's crest and name. These two deliberately do not. An `error.tsx`
 * that asks the API for a crest is an error page that fails when the API is
 * the thing that failed, and what the reader sees then is the framework's own
 * white page — the exact outcome this component exists to prevent.
 *
 * So everything here comes from the route: the module's name and key are
 * compile-time constants in each app's `lib/config.ts`, and the links are
 * static. No crest, and no institution name. A plainer page than the rest of
 * the system, which is the correct trade: it renders when nothing else will.
 *
 * ## Why the module accent survives
 *
 * It is the one piece of identity that costs nothing — `data-module` is a
 * string the app already knows — and it is what tells a registrar that they
 * are still inside Finance rather than somewhere unrecognisable. On a page
 * whose whole job is to stop someone feeling lost, that is worth a `<div>`.
 */

function Frame({
  moduleKey,
  icon,
  title,
  children,
  actions,
}: {
  moduleKey?: string
  icon: ReactNode
  title: string
  children: ReactNode
  actions: ReactNode
}) {
  return (
    <div
      data-module={moduleKey}
      className="bg-background grid min-h-dvh place-items-center px-4 py-12"
    >
      <main className="w-full max-w-lg">
        <div className="bg-card shadow-raised relative overflow-hidden rounded-xl p-7 sm:p-9">
          <span aria-hidden className="bg-module absolute inset-x-0 top-0 h-[3px]" />
          <span
            aria-hidden
            className="bg-module/10 text-module mb-5 grid size-11 place-items-center rounded-lg [&>svg]:size-5"
          >
            {icon}
          </span>
          <h1 className="font-display text-balance text-xl font-extrabold tracking-tight">
            {title}
          </h1>
          <div className="text-muted-foreground mt-2.5 space-y-2.5 text-sm leading-relaxed">
            {children}
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-2">{actions}</div>
        </div>
      </main>
    </div>
  )
}

const buttonish =
  "inline-flex min-h-10 items-center gap-1.5 rounded-md px-3.5 text-sm font-medium transition-colors"

/**
 * Rendered by every app's `error.tsx`.
 *
 * `reset` re-runs the segment's render without a full page load, which is the
 * right first move: most of what lands here is one call that failed once.
 *
 * `digest` is Next's hash of the server-side stack. It is the only thing on
 * this page an engineer can act on, so it is shown rather than hidden — in the
 * mono face, because it will be read aloud or pasted into a ticket. The
 * message itself is not shown: in production it is scrubbed to "an error
 * occurred in the Server Components render" anyway, and in development the
 * overlay already has it.
 */
export function ErrorState({
  error,
  reset,
  moduleKey,
  moduleName,
}: {
  error: Error & { digest?: string }
  reset: () => void
  moduleKey?: string
  moduleName?: string
}) {
  return (
    <Frame
      moduleKey={moduleKey}
      icon={<AlertTriangle />}
      title="Something went wrong on this page"
      actions={
        <>
          <button
            type="button"
            onClick={reset}
            className={cn(buttonish, "bg-primary text-primary-foreground hover:bg-primary/90")}
          >
            <RotateCw className="size-4" aria-hidden />
            Try again
          </button>
          <Link href="/" className={cn(buttonish, "border-border hover:bg-muted border")}>
            <ArrowLeft className="size-4" aria-hidden />
            {moduleName ? `Back to ${moduleName}` : "Back"}
          </Link>
          <a
            href={moduleUrl("shell")}
            className={cn(buttonish, "text-muted-foreground hover:text-foreground")}
          >
            <LayoutGrid className="size-4" aria-hidden />
            All modules
          </a>
        </>
      }
    >
      <p>
        The page could not be built. Nothing you were doing has been saved or changed by this — if
        you had just submitted something, check before sending it again.
      </p>
      <p>
        Trying again is worth one attempt. If it keeps happening, quote the reference below to
        whoever supports {moduleName ?? "this module"} at your institution.
      </p>
      {error.digest ? (
        <p className="text-muted-foreground/80 font-mono text-xs">ref {error.digest}</p>
      ) : null}
    </Frame>
  )
}

/**
 * Rendered by every app's `not-found.tsx`, and by `notFound()` on a record
 * route whose id resolves to nothing.
 *
 * Says *gone or never existed* rather than guessing between them, because the
 * API deliberately does not distinguish the two for a reader who may not be
 * allowed to know which — the same reasoning as `NotPermitted`.
 */
export function NotFoundState({
  moduleKey,
  moduleName,
  what = "page",
  backHref = "/",
  backLabel,
}: {
  moduleKey?: string
  moduleName?: string
  /** "page", "student", "invoice" — what was being looked for. */
  what?: string
  backHref?: string
  backLabel?: string
}) {
  return (
    <Frame
      moduleKey={moduleKey}
      icon={<SearchX />}
      title={`That ${what} is not here`}
      actions={
        <>
          <Link
            href={backHref}
            className={cn(buttonish, "bg-primary text-primary-foreground hover:bg-primary/90")}
          >
            <ArrowLeft className="size-4" aria-hidden />
            {backLabel ?? (moduleName ? `Back to ${moduleName}` : "Back")}
          </Link>
          <a
            href={moduleUrl("shell")}
            className={cn(buttonish, "border-border hover:bg-muted border")}
          >
            <LayoutGrid className="size-4" aria-hidden />
            All modules
          </a>
        </>
      }
    >
      <p>
        It may have been removed, it may never have existed, or the address may have been mistyped.
        Records are not deleted silently in ACMIS, so if you reached this from a link inside the
        system it is worth reporting.
      </p>
    </Frame>
  )
}
