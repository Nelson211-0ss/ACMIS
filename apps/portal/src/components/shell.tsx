import * as Icons from "lucide-react"
import type { ReactNode } from "react"

import type { WhoAmI } from "@acmis/api-client"
import { AppShell, type NavSection } from "@acmis/ui/components/app-shell"

import { MODULE_KEY, MODULE_NAME } from "@/lib/config"

export function PortalShell({
  user,
  institution,
  currentPath,
  children,
}: {
  user: WhoAmI
  institution: { name: string; short_name: string; crest_url: string | null } | null
  currentPath: string
  children: ReactNode
}) {
  const sections: NavSection[] = [
    {
      items: [
        { href: "/", label: "Overview", icon: <Icons.Home /> },
        { href: "/courses", label: "My courses", icon: <Icons.BookOpen /> },
        { href: "/assessments", label: "Tests & assignments", icon: <Icons.FileQuestion /> },
        { href: "/results", label: "Results", icon: <Icons.Award /> },
        { href: "/calendar", label: "Calendar", icon: <Icons.CalendarDays /> },
        { href: "/library", label: "Library", icon: <Icons.Library /> },
      ],
    },
    {
      title: "Administration",
      items: [
        { href: "/registration", label: "Registration", icon: <Icons.ClipboardList /> },
        { href: "/fees", label: "Fees", icon: <Icons.Wallet /> },
        { href: "/record", label: "My record", icon: <Icons.User /> },
        { href: "/exam-cards", label: "Exam cards", icon: <Icons.Ticket /> },
        { href: "/id-card", label: "Campus ID", icon: <Icons.IdCard /> },
        { href: "/attendance", label: "Attendance", icon: <Icons.UserCheck /> },
        { href: "/requests", label: "Requests", icon: <Icons.FileText /> },
      ],
    },
    {
      title: "Guild",
      items: [{ href: "/elections", label: "Elections", icon: <Icons.Vote /> }],
    },
  ]

  return (
    <AppShell
      moduleKey={MODULE_KEY}
      moduleName={MODULE_NAME}
      institutionName={institution?.name ?? user.tenant_name}
      institutionShortName={institution?.short_name}
      crestUrl={institution?.crest_url}
      sections={sections}
      currentPath={currentPath}
      // The tab bar's default — the first four nav items — is wrong for a
      // student. Nav order is written for the drawer, where related things sit
      // together; the four screens a student actually alternates between on a
      // phone are what they owe, what they must do, when, and what they got.
      // Fees is the ninth nav item and the second thing they open.
      primaryNav={[
        { href: "/", label: "Overview", icon: <Icons.Home /> },
        { href: "/fees", label: "Fees", icon: <Icons.Wallet /> },
        { href: "/registration", label: "Registration", icon: <Icons.ClipboardList /> },
        { href: "/results", label: "Results", icon: <Icons.Award /> },
      ]}
      user={{ display_name: user.display_name, kind: user.kind }}
    >
      {children}
    </AppShell>
  )
}
