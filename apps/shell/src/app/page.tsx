import * as Icons from "lucide-react"
import Link from "next/link"

import { acmis, requireUser } from "@acmis/auth/server"
import { ThemeToggle } from "@acmis/ui/components/theme-toggle"
import { MODULES, moduleUrl, type ModuleDefinition } from "@acmis/ui/lib/modules"
import { relativeTime } from "@acmis/ui/lib/format"

import { APP } from "@/lib/config"

/**
 * The launcher.
 *
 * One job: get a signed-in person into the right module in one click, and tell
 * them what needs their attention before they get there. `whoami` already
 * decides which modules they see — computed server-side from permissions *and*
 * the tenant's plan — so this page renders that answer rather than recomputing
 * it.
 */

export const metadata = { title: "Home" }

export default async function LauncherPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, notifications, semester] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.notifications({ limit: 6, unread_only: true }).catch(() => null),
    client.reference.currentSemester().catch(() => null),
  ])

  const visible = MODULES.filter(
    (m) =>
      m.key !== "shell" &&
      user.modules.includes(m.key) &&
      m.audience.includes(user.kind as ModuleDefinition["audience"][number]),
  )

  return (
    <div className="bg-background min-h-dvh">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-4 sm:px-6">
          {institution?.crest_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={institution.crest_url} alt="" className="size-9 object-contain" />
          ) : null}
          <div className="min-w-0 flex-1">
            <p className="font-display truncate text-lg font-extrabold leading-tight tracking-tight">
              {institution?.name ?? user.tenant_name}
            </p>
            <p className="text-muted-foreground flex items-center gap-1.5 truncate text-xs">
              <Icons.CalendarRange className="size-3 shrink-0" aria-hidden />
              {semester ? semester.name : "ACMIS"}
              {institution?.city ? (
                <>
                  <span aria-hidden>·</span>
                  <Icons.MapPin className="size-3 shrink-0" aria-hidden />
                  {institution.city}
                </>
              ) : null}
            </p>
          </div>
          <ThemeToggle />
          <div className="text-right">
            <p className="text-sm font-medium leading-tight">{user.display_name}</p>
            <form action={signOut}>
              <button
                type="submit"
                className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs underline"
              >
                <Icons.LogOut className="size-3" aria-hidden />
                Sign out
              </button>
            </form>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
        {user.is_impersonated ? (
          <p className="border-warning/40 bg-warning/10 text-warning-foreground rounded-lg border px-4 py-3 text-sm">
            You are in a read-only support session. Every action is recorded in this
            institution&rsquo;s audit trail.
          </p>
        ) : null}

        <section>
          <h2 className="flex items-center gap-2 text-xl">
            <Icons.LayoutGrid className="text-module size-4.5 shrink-0" aria-hidden />
            Your modules
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            {visible.length === 0
              ? "Your account has no modules assigned yet."
              : "Only the modules your roles and your institution's plan include are shown."}
          </p>

          <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((module) => {
              const Icon =
                (Icons as unknown as Record<string, Icons.LucideIcon>)[module.icon] ?? Icons.Square
              return (
                <li key={module.key} data-module={module.key}>
                  <a
                    href={moduleUrl(module.key)}
                    className="bg-card shadow-card hover:shadow-card-hover group relative flex h-full flex-col gap-2 overflow-hidden rounded-lg p-4 transition-shadow"
                  >
                    <span aria-hidden className="bg-module absolute inset-x-0 top-0 h-[3px]" />
                    <span className="flex items-center gap-2.5">
                      <span
                        aria-hidden
                        className="bg-module/10 text-module ring-module/15 group-hover:bg-module/15 grid size-9 shrink-0 place-items-center rounded-lg ring-1 transition-colors"
                      >
                        <Icon className="size-[18px]" />
                      </span>
                      <span className="font-display text-base font-bold tracking-tight">
                        {module.name}
                      </span>
                      <Icons.ArrowRight
                        aria-hidden
                        className="text-module ml-auto size-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                      />
                    </span>
                    <span className="text-muted-foreground text-sm leading-relaxed">
                      {module.description}
                    </span>
                  </a>
                </li>
              )
            })}
          </ul>
        </section>

        {notifications && notifications.items.length > 0 ? (
          <section>
            <h2 className="flex items-center gap-2 text-xl">
              <Icons.BellRing className="text-module size-4.5 shrink-0" aria-hidden />
              Needs your attention
            </h2>
            <ul className="mt-4 divide-y rounded-lg border">
              {notifications.items.map((item) => (
                <li key={item.id} className="flex items-start gap-3 p-4">
                  {/* Urgency is a different glyph, not the same dot in a
                      different colour — this list is scanned, and red is the
                      one channel a reader may not have. */}
                  {item.is_urgent ? (
                    <Icons.AlertTriangle
                      aria-hidden
                      className="text-destructive mt-0.5 size-4 shrink-0"
                    />
                  ) : (
                    <Icons.Circle aria-hidden className="text-module mt-0.5 size-4 shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{item.subject}</p>
                    <p className="text-muted-foreground mt-0.5 text-sm leading-relaxed">
                      {item.body}
                    </p>
                    <p className="text-muted-foreground mt-1 text-xs">
                      {relativeTime(item.created_at)}
                      {item.is_urgent ? " · Urgent" : ""}
                    </p>
                  </div>
                  {item.action_url ? (
                    <Link
                      href={item.action_url}
                      className="text-module inline-flex shrink-0 items-center gap-1 text-xs font-medium underline"
                    >
                      Open
                      <Icons.ArrowUpRight className="size-3" aria-hidden />
                    </Link>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="text-muted-foreground text-xs">
          <p>
            Signed in as {user.display_name} ({user.kind}) at {user.tenant_name}.
            {user.roles.length > 0
              ? ` Roles: ${user.roles.map((r) => r.replace(/_/g, " ")).join(", ")}.`
              : ""}
          </p>
          {!user.mfa_satisfied ? (
            <p className="mt-2">
              Some actions — conferring an award, releasing results, waiving fees, exporting
              personal data — will ask you to confirm your identity with a second factor.
            </p>
          ) : null}
        </section>
      </main>
    </div>
  )
}

async function signOut() {
  "use server"
  const { clearSession } = await import("@acmis/auth/server")
  const { redirect } = await import("next/navigation")
  const client = await acmis(APP)
  await client.auth.logout().catch(() => undefined)
  await clearSession()
  redirect("/sign-in")
}
