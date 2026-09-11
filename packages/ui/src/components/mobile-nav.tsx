"use client"

import * as Icons from "lucide-react"
import Link from "next/link"
import { useEffect, useState, type ReactNode } from "react"
import { createPortal } from "react-dom"

import { cn } from "@acmis/ui/lib/utils"
import type { NavItem, NavSection } from "@acmis/ui/components/app-shell"

/**
 * Navigation below `lg`, where the sidebar is hidden.
 *
 * Two mechanisms, because the range below `lg` is not one device:
 *
 * - **A drawer**, from `lg` down. These apps have eight to twelve
 *   destinations grouped into sections, and only a drawer holds that many
 *   with their grouping intact.
 * - **A bottom tab bar**, below `sm` only. The drawer alone put every
 *   destination behind a control in the *top* corner of a phone — the one
 *   region a thumb cannot reach without regripping — so moving between two
 *   screens meant a reach, a tap, a scan of twelve items and a second tap.
 *   The four destinations staff actually alternate between are now one
 *   thumb-tap away, and the fifth slot opens the drawer for the rest.
 *
 * Both live in this one component because they share the drawer's open state.
 * Two components with two `useState`s would need it lifted into a context for
 * no other reason.
 *
 * Three things that matter on a real phone and are easy to miss:
 *
 * - **Scroll lock while open**, or the page behind scrolls under the drawer
 *   and the user loses their place.
 * - **`h-dvh`, not `h-screen`.** On mobile Safari `100vh` is taller than the
 *   visible area, so the last nav item sits under the browser chrome and
 *   cannot be tapped.
 * - **`env(safe-area-inset-bottom)`**, so the last item clears the home
 *   indicator on a notched device.
 * - **Both fixed layers are portalled to `<body>`.** See `ViewportLayer`.
 */

/**
 * Renders into `<body>`, outside whatever this component was mounted in.
 *
 * `position: fixed` is only relative to the viewport while no ancestor has a
 * transform, filter, backdrop-filter, perspective, `contain` or `will-change`.
 * Any one of those makes *that* ancestor the containing block for every fixed
 * descendant instead — silently, with no warning and no error.
 *
 * `AppShell` mounts `MobileNav` inside its header, and that header carries
 * `backdrop-blur` so the page does not smear through it while scrolling. So
 * the containing block for both layers below was a 56px-tall bar at the top of
 * the screen. The tab bar's `bottom-0` resolved to the bottom of *the header*
 * and it rendered across the top of the phone — measured at y = -2 — covering
 * the module chip and the launcher it was supposed to sit opposite, while the
 * bottom of the screen, the whole reason the tab bar exists, stayed empty. The
 * drawer's `inset-0` was confined to the same 56px strip.
 *
 * Portalling fixes it at the root rather than by deleting the blur, and keeps
 * it fixed: the header can grow a transform or a filter later and these layers
 * will not care. The two still live in one component so they can share the
 * drawer's open state, which is the arrangement the note above defends.
 *
 * `mounted` gates it because `document` does not exist during server render.
 * The trigger button is *not* portalled — it belongs in the header, where it
 * is mounted.
 */
function ViewportLayer({ moduleKey, children }: { moduleKey: string; children: ReactNode }) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  if (!mounted) return null
  // `data-module` has to be re-declared here. `--module` is scoped to the
  // `[data-module]` element `AppShell` renders, and the portal's destination is
  // `<body>` — outside it. Without this the drawer title and the active tab
  // fall back to `--primary`, so Finance's rail reads green while its drawer
  // reads senate blue: the one cue that says which app you are in, disagreeing
  // with itself on the one screen where the rail is not visible to correct it.
  return createPortal(
    <div data-module={moduleKey} className="contents">
      {children}
    </div>,
    document.body,
  )
}

export function MobileNav({
  sections,
  currentPath,
  moduleName,
  moduleKey,
  primary,
}: {
  sections: NavSection[]
  currentPath: string
  moduleName: string
  /** Drives `--module` inside the portalled layers. See `ViewportLayer`. */
  moduleKey: string
  /**
   * The tab bar's destinations, at most four.
   *
   * Defaults to the first four in nav order, which is the right guess because
   * the sections are already written most-used-first. An app overrides it when
   * its own order disagrees — the student portal's fees screen is its second
   * tab and its ninth nav item.
   */
  primary?: NavItem[]
}) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = "hidden"
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener("keydown", onKey)
    }
  }, [open])

  const isActive = (href: string) =>
    currentPath === href || (href !== "/" && currentPath.startsWith(`${href}/`))

  const tabs = (primary ?? sections.flatMap((s) => s.items)).slice(0, 4)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-label={`Open ${moduleName} navigation`}
        // Shown from `sm` to `lg`: below `sm` the tab bar's "More" is the
        // trigger, and a second one in the far corner is just clutter.
        className="hover:bg-muted -ml-1 hidden size-11 place-items-center rounded-md sm:grid lg:hidden"
      >
        <Icons.Menu className="size-5" aria-hidden />
      </button>

      {/* ---- Bottom tab bar, phones only -------------------------------- */}
      <ViewportLayer moduleKey={moduleKey}>
        <nav
          aria-label={`${moduleName} primary navigation`}
          className="bg-background/95 no-print fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t backdrop-blur sm:hidden"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        >
          {tabs.map((item) => {
            const active = isActive(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex min-h-14 flex-col items-center justify-center gap-0.5 px-1 pb-1 pt-1.5",
                  active ? "text-module" : "text-muted-foreground",
                )}
              >
                {active ? (
                  // The active marker is a shape at the top edge as well as a
                  // colour, so the current tab survives being read by someone
                  // who cannot separate the accent from the ink.
                  <span
                    aria-hidden
                    className="bg-module absolute inset-x-3 top-0 h-[2px] rounded-b-full"
                  />
                ) : null}
                <span className="relative [&>svg]:size-5">
                  {item.icon ?? <Icons.Circle />}
                  {item.badge !== undefined && item.badge !== 0 ? (
                    <span className="bg-destructive text-destructive-foreground tabular absolute -right-2 -top-1 min-w-4 rounded-full px-1 text-[10px] font-semibold leading-4">
                      {item.badge}
                    </span>
                  ) : null}
                </span>
                {/* Two lines maximum and no truncation: a tab label clipped to
                    "Registrat…" is worse than one that wraps. */}
                <span className="w-full text-center text-[10px] leading-tight">{item.label}</span>
              </Link>
            )
          })}

          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-expanded={open}
            aria-label={`Open all of ${moduleName}`}
            className="text-muted-foreground flex min-h-14 flex-col items-center justify-center gap-0.5 px-1 pb-1 pt-1.5"
          >
            <Icons.MoreHorizontal className="size-5" aria-hidden />
            <span className="text-[10px] leading-tight">More</span>
          </button>
        </nav>
      </ViewportLayer>

      {/* ---- Drawer ------------------------------------------------------ */}
      {open ? (
        <ViewportLayer moduleKey={moduleKey}>
          <div className="fixed inset-0 z-50 lg:hidden">
            <button
              type="button"
              aria-label="Close navigation"
              onClick={() => setOpen(false)}
              className="bg-foreground/40 absolute inset-0 backdrop-blur-sm"
            />
            <nav
              aria-label={`${moduleName} navigation`}
              className="bg-sidebar text-sidebar-foreground absolute inset-y-0 left-0 flex h-dvh w-[min(19rem,85vw)] flex-col border-r shadow-xl"
            >
              <div className="flex h-14 shrink-0 items-center justify-between border-b px-4">
                <span className="text-module text-sm font-semibold">{moduleName}</span>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close navigation"
                  className="hover:bg-muted grid size-11 place-items-center rounded-md"
                >
                  <Icons.X className="size-4" aria-hidden />
                </button>
              </div>

              <div
                className="min-h-0 flex-1 space-y-5 overflow-y-auto px-2 py-4"
                style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" }}
              >
                {sections.map((section, index) => (
                  <div key={section.title ?? index}>
                    {section.title ? (
                      <p className="text-muted-foreground mb-1.5 px-2 text-[11px] font-medium uppercase tracking-wide">
                        {section.title}
                      </p>
                    ) : null}
                    <ul className="space-y-0.5">
                      {section.items.map((item) => {
                        const active = isActive(item.href)
                        return (
                          <li key={item.href}>
                            <Link
                              href={item.href}
                              onClick={() => setOpen(false)}
                              aria-current={active ? "page" : undefined}
                              className={cn(
                                // 44px rows here too — a 32px nav row in a
                                // drawer is a mis-tap machine.
                                "relative flex min-h-11 items-center gap-2.5 rounded-md px-2.5 text-sm",
                                active
                                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                                  : "text-muted-foreground",
                              )}
                            >
                              {active ? (
                                <span
                                  aria-hidden
                                  className="bg-module absolute left-0 top-1/2 h-5 w-[2px] -translate-y-1/2 rounded-full"
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
              </div>
            </nav>
          </div>
        </ViewportLayer>
      ) : null}
    </>
  )
}
