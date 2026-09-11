import localFont from "next/font/local"
import { JetBrains_Mono } from "next/font/google"

/**
 * The three faces, loaded once and shared by every app.
 *
 * The pairing is the Foundation's — the same Vistol Sans / Overpass
 * combination the Jdiobe STEM admin dashboards run on — so a registrar who
 * moves between the Foundation's tools and ACMIS is not crossing a visual
 * border. Both are self-hosted rather than fetched from Google: these apps are
 * used in campus labs on metered links, and a third-party font host is also a
 * third-party request on a screen that is otherwise entirely first-party.
 *
 * ## Which face does what
 *
 * - **Vistol Sans** is the interface: nav, labels, form fields, prose, table
 *   cells that hold words. It is a humanist grotesque that stays legible at
 *   13px on the cheap panels these screens are read on all day.
 * - **Overpass** is headings and *figures*. The heading half is the
 *   Foundation's own rule — weight rather than a second voice carries the
 *   contrast. The figures half is not cosmetic: see below.
 * - **JetBrains Mono** is anything a human reads aloud digit by digit —
 *   student numbers, receipt references, API keys — where a 0/O or 1/l
 *   confusion is a support call.
 *
 * ## Why numbers are set in Overpass
 *
 * `globals.css` has always asked for `font-variant-numeric: tabular-nums` on
 * tables and on `.tabular`, because a bursar scanning 400 fee balances needs
 * the thousands column to be a column. That request is a no-op unless the face
 * actually ships tabular figures, and Vistol does not — it has one proportional
 * set, no `tnum` feature, and digit advances that range from 498 to 545 units.
 * Asking for tabular figures in Vistol therefore looks like it works and
 * silently does nothing, which is the worst kind of failure for a ledger.
 *
 * Overpass does ship `tnum`, and it maps every digit to a uniform 1232-unit
 * advance. So `--font-numeric` points at Overpass and `globals.css` routes
 * table figures and `.tabular` to it. Mixing a numeric face into a table of
 * Vistol labels is deliberate and is what makes the column align.
 *
 * ## Loading
 *
 * `variable` rather than `className`, because the CSS variables are what
 * `globals.css` maps onto `--font-sans`, `--font-display`, `--font-numeric`
 * and `--font-mono`. Each app puts all of them on `<html>` via
 * `fontVariables` and the design system does the rest.
 *
 * `display: "swap"` throughout: a blocking font load on a slow campus
 * connection means a registrar stares at a blank screen, and a brief flash of
 * a fallback face is the better trade. Which is why every stack below names
 * real fallbacks rather than trailing off into `sans-serif`.
 */

/**
 * Six static weights rather than all nine the family ships.
 *
 * 300 (Light) and 900 (Black) have no role in a dashboard — nothing here is
 * set lighter than regular, and 800 is already the heaviest a page title
 * goes — and the italic set is one file because the interface italicises
 * roughly one thing: a quoted value inside an explanation. Dropping those
 * three is ~64 KB off every cold load across thirteen apps.
 */
export const vistol = localFont({
  src: [
    { path: "../fonts/VistolSans-Regular.woff2", weight: "400", style: "normal" },
    { path: "../fonts/VistolSans-Italic.woff2", weight: "400", style: "italic" },
    { path: "../fonts/VistolSans-Medium.woff2", weight: "500", style: "normal" },
    { path: "../fonts/VistolSans-SemiBold.woff2", weight: "600", style: "normal" },
    { path: "../fonts/VistolSans-Bold.woff2", weight: "700", style: "normal" },
    { path: "../fonts/VistolSans-ExtraBold.woff2", weight: "800", style: "normal" },
  ],
  variable: "--font-vistol",
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
})

/**
 * One variable file covering 100–900, subset to Latin plus Latin Extended-A
 * and the currency block — 63 KB instead of 315 KB, and wide enough for every
 * name, programme title and currency symbol these apps render.
 *
 * Vistol heads the fallback list rather than a generic sans, so a character
 * outside the subset drops to the interface face instead of to whatever the
 * machine happens to have.
 */
export const overpass = localFont({
  src: "../fonts/Overpass-Variable.woff2",
  weight: "100 900",
  style: "normal",
  variable: "--font-overpass",
  display: "swap",
  fallback: ["var(--font-vistol)", "ui-sans-serif", "system-ui", "sans-serif"],
})

export const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains-mono",
})

/** Put on `<html>`. Every app's root layout uses exactly this. */
export const fontVariables = [
  vistol.variable,
  overpass.variable,
  jetbrainsMono.variable,
].join(" ")
