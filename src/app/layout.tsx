import type { Metadata, Viewport } from "next";
import { institution } from "@/lib/institution";
import { accentStyleTag, themeInitScript } from "@/lib/theme";
import { getSystemSettings } from "@/lib/data/repo";
import { inter } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: `${institution.short} Portal`,
    template: `%s · ${institution.short} Portal`,
  },
  description: `Student portal and admissions application portal for ${institution.name}, ${institution.city}.`,
  applicationName: `${institution.short} Portal`,
  formatDetection: { telephone: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Zoom stays available — students read marksheets on 5-inch screens.
  maximumScale: 5,
  themeColor: "#0e4c77",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const settings = await getSystemSettings();

  return (
    // The theme script writes to <html> before React hydrates, so the class
    // list legitimately differs from what the server rendered.
    <html lang="en" suppressHydrationWarning className={inter.variable}>
      <head>
        <style dangerouslySetInnerHTML={{ __html: accentStyleTag(settings.appearance.accent) }} />
      </head>
      <body className="min-h-dvh">
        <script
          dangerouslySetInnerHTML={{ __html: themeInitScript(settings.appearance.defaultMode) }}
        />
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-brand-700 focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
