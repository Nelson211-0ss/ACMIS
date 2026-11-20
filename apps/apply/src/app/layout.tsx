import type { Metadata, Viewport } from "next"

import { ThemeProvider } from "@acmis/ui/components/theme-provider"
import { fontVariables } from "@acmis/ui/lib/fonts"

import { MODULE_NAME } from "@/lib/config"

import "./globals.css"

export const metadata: Metadata = {
  title: { default: MODULE_NAME, template: `%s · ${MODULE_NAME}` },
  description: "Apply to study — create an application account and track your application.",
  // The one app in the system a member of the public is meant to reach, and
  // still not one a search engine should index: every URL below the landing
  // screen is somebody's half-finished application.
  robots: { index: false, follow: false },
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
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
