"use client"

import * as Icons from "lucide-react"
import { useRouter } from "next/navigation"
import { useCallback, useEffect, useState } from "react"

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@acmis/ui/components/command"
import { MODULES, moduleUrl, visibleModules } from "@acmis/ui/lib/modules"
import { cn } from "@acmis/ui/lib/utils"

/**
 * One way in, from any of the eighty screens.
 *
 * ## Why this was worth mounting
 *
 * `command.tsx` and its cmdk dependency shipped in this package and were
 * rendered by nothing. Until now the only way to reach a page was to know
 * which of thirteen apps it lived in, open that app, and read its rail —
 * which is fine for the four screens a person uses daily and hopeless for the
 * fifth. There was exactly one search input in the whole system, on a
 * student-facing library page.
 *
 * ## What it searches, and what it deliberately does not
 *
 * Destinations: the pages of the module you are in, and the modules you may
 * open. Both are already in hand — the nav is data the shell was rendering
 * anyway, and `whoami` has decided the module list server-side — so the
 * palette costs no request and cannot offer a door that will refuse you.
 *
 * It does **not** search records. "MAK/2023/0041" ought to work here and one
 * day should, but there is no federated search endpoint in the API: every
 * resource takes its own `search` parameter and none of them crosses a module
 * boundary. Inventing a client-side fan-out across thirteen services to fake
 * it would be slow, would leak the shape of records the reader may not be
 * allowed to see, and would be the wrong place to solve it. `extra` is the
 * seam for when that endpoint exists.
 *
 * ## The accent
 *
 * Every module result carries its own hue. This is the second place in the
 * system where all twelve appear together, and the better of the two for
 * learning them: in the launcher they sit under names you are browsing, and
 * here they sit beside a name you were already looking for.
 */

export interface CommandDestination {
  /** Shown as the row's label. */
  label: string
  /** Where it goes. A path inside this app, or an absolute URL. */
  href: string
  /** Optional right-aligned hint — the module, the record type. */
  hint?: string
  /** Extra words that should match, never displayed. */
  keywords?: string[]
  icon?: React.ReactNode
}

export interface CommandSection {
  heading: string
  items: CommandDestination[]
}

export function CommandMenu({
  allowed,
  kind,
  currentModule,
  currentModuleName,
  sections,
  extra,
  baseUrl,
}: {
  /** From `whoami`. Which modules this person may open. */
  allowed: string[]
  kind: string
  currentModule: string
  currentModuleName: string
  /** This module's own pages, flattened from the shell's nav. */
  sections: CommandSection[]
  /** Anything the app wants to add — reports, actions, later: records. */
  extra?: CommandSection[]
  baseUrl?: string
}) {
  const router = useRouter()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "k" || (!event.metaKey && !event.ctrlKey)) return
      // Not while the person is mid-word in a field: ⌘K is a text shortcut in
      // some inputs, and stealing it there is how a palette becomes a thing
      // people turn off.
      const target = event.target as HTMLElement | null
      const tag = target?.tagName
      if (!open && (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable)) {
        return
      }
      event.preventDefault()
      setOpen((value) => !value)
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [open])

  const go = useCallback(
    (href: string) => {
      setOpen(false)
      // Another module is another origin in development and another path
      // prefix in production; either way it is a document load, not a
      // client-side route change.
      if (/^https?:\/\//.test(href)) {
        window.location.href = href
      } else {
        router.push(href)
      }
    },
    [router],
  )

  const others = visibleModules(allowed, kind).filter((m) => m.key !== currentModule)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-muted-foreground hover:bg-muted hover:text-foreground hover:border-module/40 flex h-9 items-center gap-2 rounded-md border px-2.5 text-xs font-medium transition-colors"
      >
        <Icons.Search className="size-3.5 shrink-0" aria-hidden />
        <span className="hidden sm:inline">Search</span>
        {/* The hint is hidden on touch, where there is no key to press. */}
        <kbd className="bg-muted text-muted-foreground ml-1 hidden rounded px-1.5 py-0.5 font-sans text-[10px] font-semibold lg:inline">
          ⌘K
        </kbd>
        <span className="sr-only">Search ACMIS. Shortcut: command or control K.</span>
      </button>

      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Search ACMIS"
        description="Jump to a page or another module."
        className="top-[12vh] translate-y-0"
      >
        <CommandInput placeholder={`Search ${currentModuleName} and your other modules…`} />
        <CommandList className="max-h-[60dvh]">
          <CommandEmpty>
            <span className="text-sm">Nothing matches that.</span>
            <p className="text-muted-foreground mx-auto mt-1.5 max-w-xs text-xs leading-relaxed">
              This finds pages and modules. Records are found from the list inside the module that
              owns them.
            </p>
          </CommandEmpty>

          {sections.map((section) => (
            <CommandGroup key={section.heading} heading={section.heading}>
              {section.items.map((item) => (
                <CommandItem
                  key={item.href}
                  value={`${item.label} ${item.keywords?.join(" ") ?? ""}`}
                  onSelect={() => go(item.href)}
                >
                  <span
                    aria-hidden
                    className="bg-muted text-muted-foreground grid size-6 shrink-0 place-items-center rounded-md [&>svg]:size-3.5"
                  >
                    {item.icon ?? <Icons.FileText />}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  {item.hint ? (
                    <span className="text-muted-foreground shrink-0 text-xs">{item.hint}</span>
                  ) : null}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}

          {extra?.map((section) => (
            <CommandGroup key={section.heading} heading={section.heading}>
              {section.items.map((item) => (
                <CommandItem
                  key={item.href}
                  value={`${item.label} ${item.keywords?.join(" ") ?? ""}`}
                  onSelect={() => go(item.href)}
                >
                  <span
                    aria-hidden
                    className="bg-muted text-muted-foreground grid size-6 shrink-0 place-items-center rounded-md [&>svg]:size-3.5"
                  >
                    {item.icon ?? <Icons.CornerDownRight />}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  {item.hint ? (
                    <span className="text-muted-foreground shrink-0 text-xs">{item.hint}</span>
                  ) : null}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}

          {others.length > 0 ? (
            <>
              <CommandSeparator />
              <CommandGroup heading="Other modules">
                {others.map((module) => {
                  const Icon =
                    (Icons as unknown as Record<string, Icons.LucideIcon>)[module.icon] ??
                    Icons.Square
                  return (
                    <CommandItem
                      key={module.key}
                      // The description is searchable but not shown: "fees"
                      // should find Finance, without a wall of prose in a list
                      // meant to be scanned.
                      value={`${module.name} ${module.description}`}
                      onSelect={() => go(moduleUrl(module.key, baseUrl))}
                    >
                      <span
                        aria-hidden
                        data-module={module.key}
                        className="bg-module/12 text-module grid size-6 shrink-0 place-items-center rounded-md [&>svg]:size-3.5"
                      >
                        <Icon />
                      </span>
                      <span className="min-w-0 flex-1 truncate">{module.name}</span>
                      <Icons.ArrowUpRight
                        className="text-muted-foreground size-3.5 shrink-0"
                        aria-hidden
                      />
                    </CommandItem>
                  )
                })}
              </CommandGroup>
            </>
          ) : null}
        </CommandList>

        <div
          className={cn(
            "text-muted-foreground flex items-center gap-4 border-t px-3 py-2 text-[11px]",
          )}
        >
          <span>
            <Kbd>↑</Kbd> <Kbd>↓</Kbd> to move
          </span>
          <span>
            <Kbd>↵</Kbd> to open
          </span>
          <span className="ml-auto hidden sm:inline">
            Only what your roles and your institution&rsquo;s plan allow
          </span>
        </div>
      </CommandDialog>
    </>
  )
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="border-border bg-card rounded border px-1 py-px font-sans text-[10px] font-semibold">
      {children}
    </kbd>
  )
}

/** Every module, for the launcher app, which is not "inside" one. */
export const ALL_MODULE_KEYS = MODULES.map((m) => m.key)
