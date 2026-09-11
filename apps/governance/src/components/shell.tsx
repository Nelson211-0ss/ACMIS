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
export function GovernanceShell({
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
        ...(has("audit:read", "governance:oversight")
          ? [{ href: "/audit", label: "Audit trail", icon: <Icons.ScrollText /> }]
          : []),
      ],
    },
    {
      title: "Access review",
      items: [
        ...(has("audit:read", "governance:oversight")
          ? [{ href: "/denials", label: "Denials", icon: <Icons.ShieldAlert /> }]
          : []),
        ...(has("audit:read", "governance:oversight")
          ? [{ href: "/access-log", label: "Who looked", icon: <Icons.Eye /> }]
          : []),
        ...(has("policy:admin")
          ? [{ href: "/policies", label: "Authorization policies", icon: <Icons.Gavel /> }]
          : []),
      ],
    },
    {
      title: "Reporting",
      items: [
        ...(has("reporting:run")
          ? [{ href: "/reports", label: "Reports", icon: <Icons.BarChart3 /> }]
          : []),
        ...(has("reporting:submit_statutory")
          ? [{ href: "/returns", label: "Statutory returns", icon: <Icons.Building2 /> }]
          : []),
        ...(has("governance:oversight")
          ? [{ href: "/data-requests", label: "Data requests", icon: <Icons.UserSearch /> }]
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
