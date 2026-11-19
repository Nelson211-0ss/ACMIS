"use client"

import { RotateCw } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState, useTransition } from "react"

import { cn } from "@acmis/ui/lib/utils"

/**
 * The one interactive leaf a server-rendered failure needs.
 *
 * A page that failed is a server component, so it cannot hold the handler
 * itself; this is the smallest thing that can. `router.refresh()` re-runs the
 * server render with the same props and swaps the result in — the person keeps
 * their scroll position and anything they had typed elsewhere on the page,
 * which a plain reload would throw away.
 *
 * It only ever appears where retrying could plausibly work. A permission
 * refusal does not get one: an affordance that cannot help is worse than none,
 * because a clerk will press it four times before asking anybody.
 */
export function RetryButton({
  label = "Try again",
  className,
}: {
  label?: string
  className?: string
}) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  // Counted rather than flagged: a second failure looks exactly like the
  // first, so without this the button appears to do nothing at all.
  const [tries, setTries] = useState(0)

  return (
    <span className="inline-flex flex-col items-center gap-1">
      <button
        type="button"
        disabled={pending}
        onClick={() => {
          setTries((n) => n + 1)
          startTransition(() => router.refresh())
        }}
        className={cn(
          "border-border bg-card hover:bg-muted inline-flex min-h-9 items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors disabled:opacity-60",
          className,
        )}
      >
        <RotateCw className={cn("size-3.5", pending && "animate-spin")} aria-hidden />
        {pending ? "Trying…" : label}
      </button>
      {tries >= 2 && !pending ? (
        <span className="text-muted-foreground text-[11px]">
          Still failing — worth telling support.
        </span>
      ) : null}
    </span>
  )
}
