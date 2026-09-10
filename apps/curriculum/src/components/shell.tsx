import * as Icons from "lucide-react"
import type { ReactNode } from "react"

import type { WhoAmI } from "@acmis/api-client"
import { AppShell, type NavSection } from "@acmis/ui/components/app-shell"
import { ModuleLauncher } from "@acmis/ui/components/module-launcher"

import { MODULE_KEY, MODULE_NAME } from "@/lib/config"

/**
 * This app's chrome.
 *
 * The nav is data and is filtered by permission — not as a security boundary
 * (the API is that) but because a menu of links that all refuse is worse than
 * a short menu.
 */
export function CurriculumShell({
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
  const has = (...codes: string[]) => codes.some((c) => user.permissions.includes(c))

  const sections: NavSection[] = [
    {
      items: [
        { href: "/", label: "Overview", icon: <Icons.LayoutDashboard /> },
        { href: "/programmes", label: "Programmes", icon: <Icons.BookOpen /> },
        { href: "/courses", label: "Courses", icon: <Icons.FileText /> },
      ],
    },
    {
      title: "Approval",
      items: [
        ...(has("curriculum:author", "curriculum:recommend", "curriculum:approve") ? [{ href: "/versions", label: "Curriculum versions", icon: <Icons.GitBranch /> }] : []),
        ...(has("curriculum:recommend", "curriculum:approve") ? [{ href: "/approvals", label: "Awaiting approval", icon: <Icons.Stamp /> }] : []),
      ],
    },
    {
      title: "Delivery",
      items: [
        { href: "/offerings", label: "Course offerings", icon: <Icons.CalendarRange /> },
        ...(has("timetable:manage") ? [{ href: "/timetable", label: "Timetable", icon: <Icons.Clock /> }] : []),
      ],
    },
  ]

  return (
    <AppShell
      moduleKey={MODULE_KEY}
      moduleName={MODULE_NAME}
      institutionName={institution?.name ?? user.tenant_name}
      institutionShortName={institution?.short_name}
      crestUrl={institution?.crest_url}
      sections={sections.filter((s) => s.items.length > 0)}
      currentPath={currentPath}
      user={{
        display_name: user.display_name,
        kind: user.kind,
        is_impersonated: user.is_impersonated,
      }}
      launcher={
        <ModuleLauncher allowed={user.modules} currentModule={MODULE_KEY} kind={user.kind} />
      }
    >
      {children}
    </AppShell>
  )
}
