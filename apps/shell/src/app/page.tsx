import * as Icons from "lucide-react"
import Link from "next/link"

import { acmis, requireUser } from "@acmis/auth/server"
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
            <p className="truncate text-lg leading-tight font-semibold">
              {institution?.name ?? user.tenant_name}
            </p>
            <p className="text-muted-foreground truncate text-xs">
              {semester ? semester.name : "ACMIS"}
              {institution?.city ? ` · ${institution.city}` : ""}
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm leading-tight font-medium">{user.display_name}</p>
            <form action={signOut}>
              <button
                type="submit"
                className="text-muted-foreground hover:text-foreground text-xs underline"
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
        {user.is_impersonated ? (
          <p className="border-warning/40 bg-warning/10 text-warning-foreground rounded-lg border px-4 py-3 text-sm">
            You are in a read-only support session. Every action is recorded in
            this institution&rsquo;s audit trail.
          </p>
        ) : null}

        <section>
          <h2 className="text-xl font-semibold tracking-tight">
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
                (Icons as unknown as Record<string, Icons.LucideIcon>)[module.icon] ??
                Icons.Square
              return (
                <li key={module.key} data-module={module.key}>
                  <a
                    href={moduleUrl(module.key)}
                    className="bg-card hover:border-module/50 group relative flex h-full flex-col gap-2 overflow-hidden rounded-lg border p-4 transition-colors"
                  >
                    <span
                      aria-hidden
                      className="bg-module absolute inset-x-0 top-0 h-[3px]"
                    />
                    <span className="flex items-center gap-2">
                      <Icon className="text-module size-5 shrink-0" aria-hidden />
                      <span className="text-base font-semibold">
                        {module.name}
                      </span>
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
            <h2 className="text-xl font-semibold tracking-tight">
              Needs your attention
            </h2>
            <ul className="mt-4 divide-y rounded-lg border">
              {notifications.items.map((item) => (
                <li key={item.id} className="flex items-start gap-3 p-4">
                  <span
                    aria-hidden
                    className={
                      item.is_urgent
                        ? "bg-destructive mt-1.5 size-2 shrink-0 rounded-full"
                        : "bg-module mt-1.5 size-2 shrink-0 rounded-full"
                    }
                  />
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
                      className="text-module shrink-0 text-xs font-medium underline"
                    >
                      Open
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
              Some actions — conferring an award, releasing results, waiving fees,
              exporting personal data — will ask you to confirm your identity with
              a second factor.
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
