import localFont from "next/font/local";

/**
 * Inter, self-hosted — the three weights the design actually uses (400/500/600,
 * no bold, no italic), Latin subset only. Files came from Cloudflare's cdnjs
 * mirror of Fontsource (github.com/fontsource/font-files, OFL-1.1), fetched
 * once and committed here rather than loaded live: one request per weight,
 * cached forever, no third-party request from a visitor's browser, no extra
 * DNS lookup on a first 2G page load. Together the three files are about the
 * same size as the "one downloaded display face" the old system-font-only
 * setup was built to avoid — this trades that budget for consistent
 * rendering across devices instead of spending it on decoration.
 */
export const inter = localFont({
  src: [
    { path: "./fonts/inter-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/inter-latin-500-normal.woff2", weight: "500", style: "normal" },
    { path: "./fonts/inter-latin-600-normal.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-inter",
  display: "swap",
  fallback: [
    "ui-sans-serif",
    "system-ui",
    "-apple-system",
    "Segoe UI",
    "Roboto",
    "Noto Sans",
    "Helvetica Neue",
    "Arial",
    "sans-serif",
  ],
});
