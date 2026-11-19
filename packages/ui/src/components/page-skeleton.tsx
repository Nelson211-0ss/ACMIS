import { Skeleton } from "@acmis/ui/components/skeleton"
import { cn } from "@acmis/ui/lib/utils"

/**
 * What a route renders while its data is in flight.
 *
 * ## Why these carry the chrome
 *
 * In this codebase the rail, the header and the module accent are rendered by
 * each *page* — `<FinanceShell>` wraps the page body — rather than by the
 * app's `layout.tsx`. A `loading.tsx` replaces everything from its own segment
 * downwards, so a skeleton containing only the page body would blank the rail
 * on every navigation and bring it back a moment later. The flash is worse
 * than the wait it was meant to cover.
 *
 * The chrome cannot move to the layout without a wider change: `AppShell`
 * needs `currentPath` to mark the active nav item, and a server layout has no
 * pathname. So the skeleton draws the chrome itself, at the same measurements
 * — a 16rem rail from `lg`, a 14 header — and the result is that nothing in
 * the frame moves when the page arrives. That is the only test these have to
 * pass.
 *
 * ## Why a bar is never a word
 *
 * The widths below are deliberately uneven and deliberately not derived from
 * anything. A skeleton that tries to spell out the content it is replacing
 * reads as a loaded page with the text missing, which is a worse lie than a
 * spinner. These read as "something goes here", which is the truth.
 */

function Bar({ className }: { className?: string }) {
  return <Skeleton className={cn("h-2 rounded-sm", className)} />
}

/**
 * The rail and header, at the measurements `AppShell` uses.
 *
 * Deliberately not reading the nav: a skeleton that knew the real labels would
 * be a navigation the person cannot click, which is more frustrating than one
 * they can see is not ready yet.
 */
export function ShellSkeleton({
  children,
  moduleKey,
}: {
  children: React.ReactNode
  /** Keeps the accent edge in the module's own hue while the page loads. */
  moduleKey?: string
}) {
  return (
    <div data-module={moduleKey} className="bg-background min-h-dvh" aria-busy="true">
      {/* One live region for the whole page. Thirty pulsing boxes announced
          individually is not information, it is noise. */}
      <p role="status" className="sr-only">
        Loading.
      </p>

      <div className="lg:grid lg:grid-cols-[16rem_1fr]">
        <aside className="bg-sidebar relative hidden border-r lg:sticky lg:top-0 lg:block lg:h-dvh">
          {/* The accent edge is known from the route, so it is drawn for real
              rather than greyed — it is the one thing on screen that already
              says which app you are in. */}
          <span aria-hidden className="bg-module absolute inset-y-0 left-0 w-[3px]" />
          <div className="flex h-14 items-center gap-2.5 border-b px-4">
            <Skeleton className="size-7 shrink-0 rounded" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <Bar className="w-24" />
              <Bar className="w-16" />
            </div>
          </div>
          <div className="space-y-5 px-2 py-4">
            <div className="space-y-2.5 px-2.5">
              <Bar className="w-20" />
              <Bar className="w-28" />
              <Bar className="w-24" />
            </div>
            <div className="space-y-2.5 px-2.5">
              <Bar className="w-16 opacity-70" />
              <Bar className="w-28" />
              <Bar className="w-20" />
            </div>
          </div>
        </aside>

        <div className="min-w-0">
          <header className="bg-background/95 sticky top-0 z-20 flex h-14 items-center gap-3 border-b px-3 sm:px-4">
            <Skeleton className="size-8 rounded-md lg:hidden" />
            <Skeleton className="h-5 w-24 rounded lg:hidden" />
            <div className="flex-1" />
            <Skeleton className="h-9 w-24 rounded-md" />
            <Skeleton className="size-9 rounded-md" />
          </header>
          <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6">{children}</main>
        </div>
      </div>
    </div>
  )
}

/** The `PageHeader` block: glyph chip, title, two lines of description. */
export function PageHeaderSkeleton({ actions = 0 }: { actions?: number }) {
  return (
    <div className="border-border/70 border-b pb-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <Skeleton className="mt-0.5 size-9 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2.5">
            <Skeleton className="h-6 w-56 rounded" />
            <Bar className="w-[28rem] max-w-full" />
            <Bar className="w-80 max-w-full" />
          </div>
        </div>
        {actions > 0 ? (
          <div className="flex shrink-0 gap-2">
            {Array.from({ length: actions }, (_, i) => (
              <Skeleton key={i} className="h-9 w-24 rounded-md" />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

/** One `StatTile`, at the tile's own minimum height so a row cannot shift. */
function TileSkeleton() {
  return (
    <div className="bg-card shadow-card flex h-full min-h-[5.5rem] flex-col rounded-lg p-3 sm:p-3.5">
      <Bar className="w-2/3" />
      <Skeleton className="mt-2.5 h-6 w-4/5 rounded" />
      <Bar className="mt-auto w-full pt-2" />
    </div>
  )
}

/**
 * A module overview: header, a row of tiles, then panels.
 *
 * Thirteen pages use this shape — one per module — and every one of them fans
 * out to three or four services before it returns a byte.
 */
export function OverviewSkeleton({
  tiles = 4,
  panels = 2,
  moduleKey,
}: {
  tiles?: number
  panels?: number
  moduleKey?: string
}) {
  return (
    <ShellSkeleton moduleKey={moduleKey}>
      <PageHeaderSkeleton />
      <div className="grid auto-rows-fr grid-cols-2 gap-2.5 sm:grid-cols-2 sm:gap-3 lg:grid-cols-4">
        {Array.from({ length: tiles }, (_, i) => (
          <TileSkeleton key={i} />
        ))}
      </div>
      <div className={cn("grid gap-4", panels > 1 && "lg:grid-cols-2")}>
        {Array.from({ length: panels }, (_, i) => (
          <div key={i} className="bg-card rounded-lg border p-4">
            <Skeleton className="h-4 w-40 rounded" />
            <Bar className="mt-2 w-64 max-w-full" />
            <div className="mt-4 space-y-2">
              {[82, 54, 68, 91, 47, 73].map((width, row) => (
                <div key={row} className="flex items-center gap-3">
                  <Bar className="w-24 shrink-0" />
                  <Skeleton className="h-5 rounded-sm" style={{ width: `${width}%` }} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </ShellSkeleton>
  )
}

/**
 * A list view: header, a filter row, then a table.
 *
 * `rows` should match the page size the route actually asks for. The point is
 * that the scrollbar is the right length before the data lands, so a list does
 * not jump under a cursor that is already moving towards a row.
 */
export function ListSkeleton({
  rows = 10,
  columns = 4,
  filters = true,
  moduleKey,
}: {
  rows?: number
  columns?: number
  filters?: boolean
  moduleKey?: string
}) {
  return (
    <ShellSkeleton moduleKey={moduleKey}>
      <PageHeaderSkeleton actions={1} />

      {filters ? (
        <div className="flex flex-wrap gap-2">
          <Skeleton className="h-9 min-w-48 flex-1 rounded-md" />
          <Skeleton className="h-9 w-32 rounded-md" />
          <Skeleton className="h-9 w-24 rounded-md" />
        </div>
      ) : null}

      {/* Cards below `sm`, a table from `sm` — the same split `DataTable`
          makes, so neither layout flashes the other on the way in. */}
      <div className="space-y-2 sm:hidden">
        {Array.from({ length: Math.min(rows, 6) }, (_, i) => (
          <div key={i} className="bg-card shadow-card space-y-2 rounded-lg p-3">
            <Skeleton className="h-4 w-40 rounded" />
            <Bar className="w-full" />
            <Bar className="w-2/3" />
          </div>
        ))}
      </div>

      <div className="hidden sm:block">
        <div className="border-border/70 flex gap-3 border-b px-3 py-2">
          {Array.from({ length: columns }, (_, i) => (
            <Bar key={i} className={cn("h-1.5", i === 0 ? "w-28" : "flex-1")} />
          ))}
        </div>
        {Array.from({ length: rows }, (_, row) => (
          <div
            key={row}
            className="border-border/50 flex items-center gap-3 border-b px-3 py-2.5 last:border-0"
          >
            {Array.from({ length: columns }, (_, col) => (
              <Bar
                key={col}
                className={cn(
                  col === 0 ? "w-28 shrink-0" : "flex-1",
                  // A table is mostly prose of uneven length; equal bars read
                  // as a spreadsheet and nothing in here is one.
                  col > 0 && (row + col) % 3 === 0 && "max-w-[70%]",
                )}
              />
            ))}
          </div>
        ))}
      </div>
    </ShellSkeleton>
  )
}

/**
 * One record: the trail, an identity block, status chips, then fields.
 *
 * The breadcrumbs are *not* drawn as bars. The route already knows them —
 * they came from the URL, not from a request — so greying them out would hide
 * information the browser has in hand, and they are the one thing that tells a
 * reader the page they are waiting for is the one they asked for.
 */
export function RecordSkeleton({
  trail,
  fields = 6,
  aside = true,
  moduleKey,
}: {
  /** Crumbs already known from the route. Rendered for real. */
  trail?: string[]
  fields?: number
  aside?: boolean
  moduleKey?: string
}) {
  return (
    <ShellSkeleton moduleKey={moduleKey}>
      {trail && trail.length > 0 ? (
        <nav
          aria-label="Breadcrumb"
          className="text-muted-foreground flex flex-wrap items-center gap-1.5 text-xs"
        >
          {trail.map((crumb, index) => (
            <span key={crumb} className="flex items-center gap-1.5">
              {index > 0 ? <span aria-hidden>/</span> : null}
              {crumb}
            </span>
          ))}
        </nav>
      ) : null}

      <div className="border-border/70 flex items-start gap-3 border-b pb-5">
        <Skeleton className="size-10 shrink-0 rounded-full" />
        <div className="min-w-0 flex-1 space-y-2.5">
          <Skeleton className="h-6 w-64 max-w-full rounded" />
          <Bar className="w-40" />
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-5 w-20 rounded-full" />
        <Skeleton className="h-5 w-16 rounded-full" />
        <Skeleton className="h-5 w-24 rounded-full" />
      </div>

      <div className={cn("grid gap-6", aside && "lg:grid-cols-[1.6fr_1fr]")}>
        <dl className="space-y-4">
          {Array.from({ length: fields }, (_, i) => (
            <div key={i} className="space-y-1.5">
              <Bar className="h-1.5 w-24" />
              <Skeleton className={cn("h-3.5 rounded", i % 2 ? "w-2/3" : "w-4/5")} />
            </div>
          ))}
        </dl>
        {aside ? (
          <div className="bg-card h-fit space-y-2.5 rounded-lg border p-4">
            <Skeleton className="h-4 w-32 rounded" />
            <Bar className="w-full" />
            <Bar className="w-5/6" />
            <Bar className="w-full" />
            <Skeleton className="mt-3 h-9 w-full rounded-md" />
          </div>
        ) : null}
      </div>
    </ShellSkeleton>
  )
}

/**
 * A grid of cards, for a page whose body is panels rather than a table.
 *
 * The student portal's home is this shape: a programme card, a fees card, a
 * results card. `columns` must match the page's own grid, or the one thing a
 * skeleton exists to prevent happens anyway.
 */
export function PanelsSkeleton({
  count = 6,
  columns = 3,
  moduleKey,
}: {
  count?: number
  columns?: 2 | 3
  moduleKey?: string
}) {
  return (
    <ShellSkeleton moduleKey={moduleKey}>
      <PageHeaderSkeleton />
      <div
        className={cn(
          "grid gap-4 sm:grid-cols-2",
          columns === 3 ? "lg:grid-cols-3" : "lg:grid-cols-2",
        )}
      >
        {Array.from({ length: count }, (_, i) => (
          <div key={i} className="bg-card shadow-card space-y-3 rounded-lg p-4">
            <Skeleton className="h-4 w-32 rounded" />
            <Skeleton className="h-7 w-20 rounded" />
            <Bar className="w-full" />
            <Bar className="w-4/5" />
          </div>
        ))}
      </div>
    </ShellSkeleton>
  )
}

/**
 * A page with no rail: sign-in, "not permitted", the exam runner.
 *
 * These render outside `AppShell`, so drawing the chrome here would invent a
 * rail that is about to vanish. The sign-in screen in particular is the one
 * page in the system a person may meet before they have an institution at
 * all, and a skeleton of somebody else's navigation is a strange thing to show
 * them.
 */
export function FormSkeleton({ rows = 2 }: { rows?: number }) {
  return (
    <div className="bg-background grid min-h-dvh place-items-center px-4 py-12" aria-busy="true">
      <p role="status" className="sr-only">
        Loading.
      </p>
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3">
          <Skeleton className="size-11 rounded-lg" />
          <Skeleton className="h-5 w-40 rounded" />
          <Bar className="w-56" />
        </div>
        <div className="bg-card shadow-raised space-y-4 rounded-xl p-6">
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className="space-y-2">
              <Bar className="h-1.5 w-20" />
              <Skeleton className="h-10 w-full rounded-lg" />
            </div>
          ))}
          <Skeleton className="h-10 w-full rounded-md" />
        </div>
      </div>
    </div>
  )
}

/**
 * The launcher, which is the one page that is not inside a module.
 *
 * It keeps Senate Blue rather than taking an accent — arriving there should
 * feel like arriving nowhere in particular — so this skeleton sets no
 * `data-module` either.
 */
export function LauncherSkeleton({ tiles = 6 }: { tiles?: number }) {
  return (
    <div className="bg-background min-h-dvh" aria-busy="true">
      <p role="status" className="sr-only">
        Loading.
      </p>
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-4 sm:px-6">
          <Skeleton className="size-9 shrink-0 rounded" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-48 max-w-full rounded" />
            <Bar className="w-32" />
          </div>
          <Skeleton className="size-9 rounded-md" />
        </div>
      </header>
      <main className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
        <div className="space-y-2">
          <Skeleton className="h-6 w-40 rounded" />
          <Bar className="w-80 max-w-full" />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: tiles }, (_, i) => (
            <div key={i} className="bg-card shadow-card space-y-2.5 rounded-lg p-4">
              <div className="flex items-center gap-2.5">
                <Skeleton className="size-9 shrink-0 rounded-lg" />
                <Skeleton className="h-4 w-28 rounded" />
              </div>
              <Bar className="w-full" />
              <Bar className="w-3/4" />
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}
