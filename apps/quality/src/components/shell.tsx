import * as Icons from "lucide-react"
import type { ReactNode } from "react"

import type { WhoAmI } from "@acmis/api-client"
import { AppShell, type NavSection } from "@acmis/ui/components/app-shell"
import { ModuleLauncher } from "@acmis/ui/components/module-launcher"

import { MODULE_KEY, MODULE_NAME } from "@/lib/config"

/**
 * The quality office's chrome.
 *
 * Ordered by how often the pages are opened, not by importance: teaching
 * delivery is looked at weekly, evaluations once a semester, audits once a
 * year. A nav ordered by the institution's org chart puts the annual thing
 * first and the weekly thing fourth.
 */
export function QualityShell({
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
        { href: "/delivery", label: "Teaching delivery", icon: <Icons.CalendarCheck /> },
        { href: "/attendance", label: "Attendance", icon: <Icons.UserCheck /> },
      ],
    },
    {
      title: "Feedback",
      items: [
        { href: "/evaluations", label: "Course evaluations", icon: <Icons.MessagesSquare /> },
        ...(has("quality:admin")
          ? [{ href: "/instruments", label: "Questionnaires", icon: <Icons.ListChecks /> }]
          : []),
        { href: "/observations", label: "Observations", icon: <Icons.Eye /> },
      ],
    },
    {
      title: "Assurance",
      items: [
        ...(has("quality:review", "quality:admin", "audit:read")
          ? [
              { href: "/audits", label: "Audits", icon: <Icons.ClipboardList /> },
              { href: "/indicators", label: "Indicators", icon: <Icons.Gauge /> },
            ]
          : []),
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
