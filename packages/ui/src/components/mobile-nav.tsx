"use client"

import * as Icons from "lucide-react"
import Link from "next/link"
import { useEffect, useState } from "react"

import { cn } from "@acmis/ui/lib/utils"
import type { NavSection } from "@acmis/ui/components/app-shell"

/**
 * Navigation below `lg`, where the sidebar is hidden.
 *
 * A drawer rather than a bottom tab bar, because these apps have eight to
 * twelve destinations grouped into sections and a tab bar tops out at five.
 * The trigger sits in the header where the sidebar would be.
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
 */
export function MobileNav({
  sections,
  currentPath,
  moduleName,
}: {
  sections: NavSection[]
  currentPath: string
  moduleName: string
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

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-label={`Open ${moduleName} navigation`}
        // 44px minimum touch target, which is the smallest a thumb reliably
        // hits.
        className="hover:bg-muted -ml-1 grid size-11 place-items-center rounded-md lg:hidden"
      >
        <Icons.Menu className="size-5" aria-hidden />
      </button>

      {open ? (
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
                className="hover:bg-muted grid size-9 place-items-center rounded-md"
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
                    <p className="text-muted-foreground mb-1.5 px-2 text-[11px] font-medium tracking-wide uppercase">
                      {section.title}
                    </p>
                  ) : null}
                  <ul className="space-y-0.5">
                    {section.items.map((item) => {
                      const active =
                        currentPath === item.href ||
                        (item.href !== "/" && currentPath.startsWith(`${item.href}/`))
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
                                className="bg-module absolute top-1/2 left-0 h-5 w-[2px] -translate-y-1/2 rounded-full"
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
      ) : null}
    </>
  )
}
