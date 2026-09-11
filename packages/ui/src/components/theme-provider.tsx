"use client"

import { ThemeProvider as NextThemes } from "next-themes"
import type { ReactNode } from "react"

/**
 * Makes the dark palette reachable.
 *
 * `globals.css` has carried a complete `.dark` block since the design system
 * was written — every neutral, every semantic pair and a separately validated
 * chart ramp, all contrast-checked against the dark surface rather than
 * flipped from the light values. None of it had ever rendered: nothing mounted
 * a provider, so no `.dark` class was ever put on `<html>` and the whole block
 * was dead CSS.
 *
 * `attribute="class"` is required, not a preference — `globals.css` declares
 * `@custom-variant dark (&:is(.dark *))` and the module accents key off
 * `.dark [data-module="…"]`, so a `data-theme` attribute would leave the
 * accents on their light values against a dark surface.
 *
 * `defaultTheme="system"` because the OS choice is one the user already made,
 * and the apps' `viewport.themeColor` already answers `prefers-color-scheme`.
 * The toggle exists for the case the OS gets wrong: a registry office with the
 * blinds open at 3pm, where the machine is in dark mode and the screen is
 * unreadable.
 *
 * `disableTransitionOnChange` stops every surface, border and chart fill in
 * the tree from animating its colour at once when the theme flips, which on a
 * dashboard of forty bordered elements reads as a fault rather than a
 * transition.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemes attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      {children}
    </NextThemes>
  )
}
