import type { AccentKey } from "./types";

/**
 * Theme plumbing shared by the server layout and the client toggle.
 *
 * Deliberately a plain module rather than part of theme-toggle.tsx: exports of
 * a "use client" file reach a server component as client-reference proxies, so
 * the init script would arrive as an object instead of a string.
 */

export const THEME_KEY = "ssu-theme";

/**
 * Runs before first paint so a student who chose dark never sees a white
 * flash. Inlined ahead of React — see src/app/layout.tsx.
 *
 * A visitor's own choice (in `localStorage`) always wins. Only a first-time
 * visitor falls through to `defaultMode`, which a super administrator sets on
 * the Appearance page — "system" defers to the browser's own preference,
 * same as before that setting existed.
 */
export function themeInitScript(defaultMode: "system" | "light" | "dark"): string {
  const fallback =
    defaultMode === "dark"
      ? "true"
      : defaultMode === "light"
        ? "false"
        : 'window.matchMedia("(prefers-color-scheme: dark)").matches';
  return `try{var t=localStorage.getItem("${THEME_KEY}");var dark=t==="dark"||(t===null&&(${fallback}));if(dark){document.documentElement.classList.add("dark")}}catch(e){}`;
}

/**
 * Accent presets a super administrator can switch the whole site to. Each
 * overrides the two brand tokens that actually read as "the accent colour" —
 * `--brand-700` (primary buttons, links, icon chips) and `--brand-300` (the
 * dark-sidebar highlight) — with the light and dark-mode values it needs in
 * each theme. The gold token is never touched: per the design notes in
 * globals.css it is reserved for the national-flag star and honours, not an
 * arbitrary brand colour.
 */
export const ACCENT_PALETTES: Record<
  AccentKey,
  { label: string; light: { 700: string; 300: string }; dark: { 700: string; 300: string } }
> = {
  nile: {
    label: "Nile blue (default)",
    light: { 700: "#0e4c77", 300: "#94bed8" },
    dark: { 700: "#8ccbee", 300: "#2c6f9c" },
  },
  forest: {
    label: "Forest green",
    light: { 700: "#166534", 300: "#86efac" },
    dark: { 700: "#86efac", 300: "#166534" },
  },
  amethyst: {
    label: "Amethyst",
    light: { 700: "#5b21b6", 300: "#c4b5fd" },
    dark: { 700: "#c4b5fd", 300: "#5b21b6" },
  },
  slate: {
    label: "Slate",
    light: { 700: "#334155", 300: "#cbd5e1" },
    dark: { 700: "#cbd5e1", 300: "#334155" },
  },
};

/**
 * `!important` is deliberate here: this is a single, isolated override layer
 * sitting on top of the design system's own light/dark blocks, not a normal
 * component style, and cascade order against a stylesheet Next.js controls
 * the placement of is not something worth relying on.
 */
export function accentStyleTag(accent: AccentKey): string {
  const p = ACCENT_PALETTES[accent];
  return `:root{--brand-700:${p.light[700]} !important;--brand-300:${p.light[300]} !important}.dark{--brand-700:${p.dark[700]} !important;--brand-300:${p.dark[300]} !important}`;
}
