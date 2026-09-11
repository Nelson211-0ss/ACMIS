"use client"

import * as Icons from "lucide-react"
import { useTheme } from "next-themes"
import { useEffect, useState } from "react"

import { cn } from "@acmis/ui/lib/utils"

/**
 * Light / dark / follow-the-OS, in the header.
 *
 * Three states in one control rather than a two-state switch, because "follow
 * the OS" is a real answer and a binary toggle cannot express it — once a user
 * touches a binary switch they are pinned to whichever value they picked, and
 * the machine going dark at dusk no longer reaches the app.
 *
 * ## The flash, and why the icon starts blank
 *
 * `useTheme()` cannot know the resolved theme during server render or the
 * first client pass: the answer lives in `localStorage` and in a media query,
 * neither of which exist on the server. Rendering the icon before mount
 * therefore guesses, and a wrong guess is a visible flip of the icon a beat
 * after the page settles — on the one control whose whole job is to say what
 * the current state is.
 *
 * So the button reserves its space and renders no icon until mounted. The
 * layout does not shift, and the icon appears once it can be right. This is
 * also why the label is derived after the mount check rather than from
 * `theme` directly.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme, systemTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  // system -> light -> dark -> system. The cycle starts at the OS rather than
  // ending there, so a user who taps once to escape a dark room lands on
  // light, which is the thing they wanted.
  const next = theme === "system" ? "light" : theme === "light" ? "dark" : "system"

  const resolved = theme === "system" ? systemTheme : theme
  const label = !mounted
    ? "Change theme"
    : theme === "system"
      ? `Theme: following your system (${resolved ?? "light"}). Switch to light.`
      : theme === "light"
        ? "Theme: light. Switch to dark."
        : "Theme: dark. Follow your system."

  const Icon =
    theme === "system" ? Icons.MonitorSmartphone : resolved === "dark" ? Icons.Moon : Icons.Sun

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      title={label}
      aria-label={label}
      className={cn(
        // 44px on a phone, 36px from `sm` where a pointer is likelier.
        "hover:bg-muted text-muted-foreground hover:text-foreground grid size-11 shrink-0 place-items-center rounded-md transition-colors sm:size-9",
        className,
      )}
    >
      {mounted ? <Icon className="size-4" aria-hidden /> : <span className="size-4" />}
    </button>
  )
}
