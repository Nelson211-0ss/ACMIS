import type { Metadata, Viewport } from "next"

import { ThemeProvider } from "@acmis/ui/components/theme-provider"
import { fontVariables } from "@acmis/ui/lib/fonts"

import { MODULE_NAME } from "@/lib/config"

import "./globals.css"

export const metadata: Metadata = {
  title: { default: MODULE_NAME, template: `%s · ${MODULE_NAME}` },
  description: "ACMIS — Academic Management Information System",
  // These are internal administrative apps behind authentication. Indexing
  // them would only ever leak structure.
  robots: { index: false, follow: false },
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Registry staff work on cheap panels in bright rooms, and the theme follows
  // the OS so the choice they already made is respected.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fcfdfe" },
    { media: "(prefers-color-scheme: dark)", color: "#0c1017" },
  ],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={fontVariables} suppressHydrationWarning>
      <body className="min-h-dvh antialiased">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  )
}
