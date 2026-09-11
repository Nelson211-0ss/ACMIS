"use client"

import * as Icons from "lucide-react"
import { useState } from "react"

import { cn } from "@acmis/ui/lib/utils"
import { MODULES, moduleUrl, type ModuleDefinition } from "@acmis/ui/lib/modules"

/**
 * The grid that moves staff between apps.
 *
 * `allowed` comes from `/auth/whoami`, which computes it server-side from
 * permissions *and* the tenant's plan. Deliberately not computed here: a
 * module the institution has not bought must not appear because the user
 * happens to hold a permission, and putting that logic in the client would
 * make eleven apps each capable of getting it wrong differently.
 *
 * Each tile carries its own module accent, which is the only place in the UI
 * where all nine colours appear together — that is what makes them learnable.
 */
export function ModuleLauncher({
  allowed,
  currentModule,
  kind,
  baseUrl,
}: {
  allowed: string[]
  currentModule: string
  kind: string
  baseUrl?: string
}) {
  const [open, setOpen] = useState(false)

  const visible = MODULES.filter(
    (m) =>
      m.key !== "shell" &&
      allowed.includes(m.key) &&
      m.audience.includes(kind as ModuleDefinition["audience"][number]),
  )

  if (visible.length <= 1) return null

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="hover:bg-muted hover:border-module/40 flex h-9 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors"
      >
        <Icons.LayoutGrid className="size-3.5" aria-hidden />
        <span className="hidden sm:inline">Modules</span>
        <Icons.ChevronDown
          aria-hidden
          className={cn("size-3 transition-transform", open && "rotate-180")}
        />
      </button>

      {open ? (
        <>
          {/* A click-away layer rather than a focus trap: this is a launcher,
              and trapping focus in it makes keyboard escape harder than the
              modal behaviour is worth. Escape closes it. */}
          <div className="fixed inset-0 z-30" aria-hidden onClick={() => setOpen(false)} />
          <div
            role="menu"
            // Width is clamped to the viewport, and the grid collapses to one
            // column below `xs` so a tile's description is still readable.
            className="bg-popover absolute right-0 z-40 mt-2 max-h-[70dvh] w-[min(22rem,calc(100vw-1.5rem))] overflow-y-auto rounded-lg border p-2 shadow-lg"
            onKeyDown={(event) => {
              if (event.key === "Escape") setOpen(false)
            }}
          >
            <ul className="grid grid-cols-1 gap-1 [@media(min-width:22rem)]:grid-cols-2">
              {visible.map((module) => {
                const Icon =
                  (Icons as unknown as Record<string, Icons.LucideIcon>)[module.icon] ??
                  Icons.Square
                const isCurrent = module.key === currentModule
                return (
                  <li key={module.key}>
                    <a
                      href={moduleUrl(module.key, baseUrl)}
                      role="menuitem"
                      data-module={module.key}
                      aria-current={isCurrent ? "true" : undefined}
                      className={cn(
                        "hover:bg-muted flex h-full flex-col gap-1 rounded-md p-2.5 transition-colors",
                        isCurrent && "bg-muted/70",
                      )}
                    >
                      <span className="flex items-center gap-2">
                        {/* The glyph sits on its own accent-tinted chip rather
                            than loose against the tile. Twelve bare icons in
                            twelve hues read as decoration; twelve chips read
                            as twelve things, which is what makes the accents
                            learnable in the one place they appear together. */}
                        <span
                          aria-hidden
                          className="bg-module/12 text-module grid size-6 shrink-0 place-items-center rounded-md"
                        >
                          <Icon className="size-3.5" />
                        </span>
                        <span className="font-display truncate text-xs font-bold tracking-tight">
                          {module.name}
                        </span>
                      </span>
                      <span className="text-muted-foreground text-[11px] leading-snug">
                        {module.description}
                      </span>
                    </a>
                  </li>
                )
              })}
            </ul>
          </div>
        </>
      ) : null}
    </div>
  )
}
