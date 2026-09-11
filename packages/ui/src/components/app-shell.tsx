import Link from "next/link"
import type { ReactNode } from "react"

import { MobileNav } from "@acmis/ui/components/mobile-nav"
import { ThemeToggle } from "@acmis/ui/components/theme-toggle"
import { cn } from "@acmis/ui/lib/utils"

/**
 * The chrome every module app renders inside.
 *
 * One layout, eleven apps. Staff move between several in a day, so the rail,
 * the header and the launcher are in the same place with the same behaviour
 * everywhere — the only thing that changes is the module accent on the rail
 * edge and the chip, which is how you know at a glance which app you are in
 * without reading.
 *
 * A server component: it takes the user and the nav as data and renders no
 * interactivity of its own, so a page using it costs no client JavaScript for
 * the frame.
 */

/**
 * First letter of the first and last name, which is what a person recognises
 * their own avatar by. Falls back to one letter rather than to a blank circle,
 * and to nothing at all rather than to a crash, because `display_name` comes
 * from the institution's own records and one of them will be a single word.
 */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return "?"
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase()
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase()
}

export interface NavItem {
  href: string
  label: string
  /** A count worth interrupting for — mark sheets due, unmatched payments. */
  badge?: number | string
  icon?: ReactNode
}

export interface NavSection {
  title?: string
  items: NavItem[]
}

export function AppShell({
  moduleKey,
  moduleName,
  institutionName,
  institutionShortName,
  crestUrl,
  sections,
  currentPath,
  user,
  launcher,
  banner,
  primaryNav,
  children,
}: {
  moduleKey: string
  moduleName: string
  institutionName: string
  institutionShortName?: string
  crestUrl?: string | null
  sections: NavSection[]
  currentPath: string
  user: { display_name: string; kind: string; is_impersonated?: boolean }
  /** The module launcher, rendered in the header. */
  launcher?: ReactNode
  /** An institution-wide notice. Renders above everything, unmissable. */
  banner?: ReactNode
  /**
   * The phone tab bar's four destinations. Defaults to the first four in nav
   * order; see `MobileNav`.
   */
  primaryNav?: NavItem[]
  children: ReactNode
}) {
  return (
    // `data-module` is what drives `--module` in globals.css. Set once, here.
    <div data-module={moduleKey} className="bg-background min-h-dvh">
      {user.is_impersonated ? (
        // A support session must be visible at all times, to the institution
        // as much as to the support engineer. A banner nobody can dismiss is
        // the point.
        <div className="bg-warning text-warning-foreground no-print px-4 py-1.5 text-center text-xs font-medium">
          Support session — read-only. Every action is recorded in this institution&rsquo;s audit
          trail.
        </div>
      ) : null}
      {banner}

      <div className="lg:grid lg:grid-cols-[16rem_1fr]">
        <aside
          className={cn(
            "bg-sidebar text-sidebar-foreground no-print relative hidden border-r lg:block",
            "lg:sticky lg:top-0 lg:h-dvh lg:overflow-y-auto",
          )}
        >
          <span aria-hidden className="bg-module absolute inset-y-0 left-0 w-[3px]" />
          <div className="flex h-14 items-center gap-2.5 border-b px-4">
            {crestUrl ? (
              // A plain `img`, not `next/image`. This package is
              // framework-agnostic — it is imported by thirteen Next apps and
              // must not depend on one of them — and the crest is an
              // arbitrary URL the institution supplied, which `next/image`
              // would refuse without every deployment listing every tenant's
              // host in `remotePatterns`.
              <img src={crestUrl} alt="" className="size-7 shrink-0 rounded object-contain" />
            ) : (
              <span className="bg-module/15 text-module grid size-7 shrink-0 place-items-center rounded text-xs font-bold">
                {(institutionShortName ?? institutionName).slice(0, 3).toUpperCase()}
              </span>
            )}
            <div className="min-w-0">
              {/* The institution's name is the one piece of chrome that should
                  read as an institution rather than as an app, so it takes the
                  display face. The module under it stays on the interface face
                  — it is a label for where you are, not a title. */}
              <p
                className="font-display truncate text-sm font-bold leading-tight tracking-tight"
                title={institutionName}
              >
                {institutionShortName ?? institutionName}
              </p>
              <p className="text-module truncate text-[11px] font-medium leading-tight">
                {moduleName}
              </p>
            </div>
          </div>

          <nav className="space-y-5 px-2 py-4" aria-label={`${moduleName} navigation`}>
            {sections.map((section, index) => (
              <div key={section.title ?? index}>
                {section.title ? <p className="eyebrow mb-1.5 px-2">{section.title}</p> : null}
                <ul className="space-y-0.5">
                  {section.items.map((item) => {
                    const active =
                      currentPath === item.href ||
                      (item.href !== "/" && currentPath.startsWith(`${item.href}/`))
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "relative flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors",
                            active
                              ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                              : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
                          )}
                        >
                          {active ? (
                            // The active marker is the module accent, and it
                            // is a shape as well as a colour.
                            <span
                              aria-hidden
                              className="bg-module absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full"
                            />
                          ) : null}
                          {item.icon ? (
                            <span className="shrink-0 [&>svg]:size-4">{item.icon}</span>
                          ) : null}
                          <span className="min-w-0 flex-1 truncate">{item.label}</span>
                          {item.badge !== undefined && item.badge !== 0 ? (
                            <span className="bg-module/15 text-module tabular shrink-0 rounded-full px-1.5 py-0.5 text-[11px] font-semibold">
                              {item.badge}
                            </span>
                          ) : null}
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </nav>
        </aside>

        <div className="min-w-0">
          <header className="bg-background/95 no-print supports-[backdrop-filter]:bg-background/80 sticky top-0 z-20 flex h-14 items-center gap-2 border-b px-3 backdrop-blur sm:gap-3 sm:px-4">
            <MobileNav
              sections={sections}
              currentPath={currentPath}
              moduleName={moduleName}
              moduleKey={moduleKey}
              primary={primaryNav}
            />
            <span className="bg-module/15 text-module truncate rounded px-2 py-0.5 text-xs font-semibold lg:hidden">
              {moduleName}
            </span>
            <div className="flex-1" />
            {launcher}
            {/* The toggle was written, exported and imported here, and never
                rendered — so the whole `.dark` palette in `globals.css` was
                unreachable. It sits before the identity block because it is a
                control and the identity block is not. */}
            <ThemeToggle />
            {/* The name is dropped below `sm` rather than truncated: on a
                360px screen the module chip and the launcher are what the user
                needs, and their own name is the least useful thing there. The
                initials survive, because on a shared registry machine the one
                question worth answering at a glance is whose session this is. */}
            <div className="flex items-center gap-2">
              <div className="hidden text-right sm:block">
                <p className="max-w-[12rem] truncate text-sm font-medium leading-tight">
                  {user.display_name}
                </p>
                <p className="text-muted-foreground text-[11px] capitalize leading-tight">
                  {user.kind}
                </p>
              </div>
              <span
                aria-hidden
                title={user.display_name}
                className="bg-module/12 text-module ring-module/20 font-display grid size-8 shrink-0 place-items-center rounded-full text-[11px] font-bold ring-1"
              >
                {initials(user.display_name)}
              </span>
            </div>
          </header>

          {/* `min-w-0` at every level down from the grid: without it a wide
              table forces the whole column wider than the viewport and the
              page scrolls horizontally instead of the table. */}
          <main
            className="mx-auto min-w-0 max-w-7xl space-y-5 px-3 py-5 sm:space-y-6 sm:px-6 sm:py-6"
            style={{
              // Below `sm` the tab bar is a 56px-tall fixed layer across the
              // foot of the screen, so the page has to end above it or its
              // last row — usually the pagination — sits underneath and cannot
              // be tapped. The bar is `sm:hidden`, and so is this clearance:
              // `--tab-bar` is set to zero from `sm` up by the rule below.
              paddingBottom: "calc(1.25rem + var(--tab-bar, 3.5rem) + env(safe-area-inset-bottom))",
            }}
          >
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
