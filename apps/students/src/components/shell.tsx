import * as Icons from "lucide-react"
import type { ReactNode } from "react"

import type { WhoAmI } from "@acmis/api-client"
import { AppShell, type NavSection } from "@acmis/ui/components/app-shell"
import { ModuleLauncher } from "@acmis/ui/components/module-launcher"

import { MODULE_KEY, MODULE_NAME } from "@/lib/config"

export function StudentsShell({
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
        { href: "/students", label: "Students", icon: <Icons.Users /> },
      ],
    },
    {
      title: "Life-cycle",
      items: [
        { href: "/registration", label: "Registration", icon: <Icons.ClipboardList /> },
        ...(has("student:approve_status")
          ? [{ href: "/status-changes", label: "Status changes", icon: <Icons.ArrowLeftRight /> }]
          : []),
        ...(has("student:manage")
          ? [{ href: "/clearance", label: "Clearance", icon: <Icons.CheckSquare /> }]
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
