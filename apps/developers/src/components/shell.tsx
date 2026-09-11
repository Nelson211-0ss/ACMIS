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
export function DevelopersShell({
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
        { href: "/clients", label: "API clients", icon: <Icons.Boxes /> },
        { href: "/keys", label: "Keys", icon: <Icons.KeyRound /> },
      ],
    },
    {
      title: "Integrations",
      items: [
        { href: "/webhooks", label: "Webhooks", icon: <Icons.Webhook /> },
        ...(has("interop:manage_tools")
          ? [{ href: "/lti", label: "LTI tools", icon: <Icons.Puzzle /> }]
          : []),
        { href: "/logs", label: "Request logs", icon: <Icons.Terminal /> },
      ],
    },
    {
      title: "Reference",
      items: [
        { href: "/reference", label: "API reference", icon: <Icons.BookOpen /> },
        { href: "/events", label: "Event catalogue", icon: <Icons.Radio /> },
        { href: "/standards", label: "Standards", icon: <Icons.Award /> },
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
