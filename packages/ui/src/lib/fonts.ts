import { Inter, JetBrains_Mono } from "next/font/google"

/**
 * The two faces, loaded once and shared by every app.
 *
 * Sans for everything and mono for identifiers. No serif: these are working
 * screens read all day on cheap panels, and a serif at 13px on a 1366×768
 * office monitor is harder to scan, not more authoritative.
 *
 * `variable` rather than `className` because the CSS variables are what
 * `globals.css` maps onto `--font-sans` and `--font-mono`. Each app puts both
 * variables on `<html>` and the design system does the rest.
 *
 * `display: "swap"` on both: these apps are used on slow connections in campus
 * computer labs, and a blocking font load means a registrar stares at a blank
 * screen. A brief flash of a fallback face is the better trade, which is why
 * both stacks below name real fallbacks.
 */

export const inter = Inter({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-inter",
  // `cv11` gives the single-storey 'a' and `ss01` the open digits; both are
  // set in `globals.css` and only work if the features ship.
  axes: ["opsz"],
})

export const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains-mono",
})

/** Put on `<html>`. Every app's root layout uses exactly this. */
export const fontVariables = [inter.variable, jetbrainsMono.variable].join(" ")
