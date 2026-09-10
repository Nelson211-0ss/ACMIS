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
export function AssessmentShell({
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
        { href: "/mark-sheets", label: "Mark sheets", icon: <Icons.ClipboardCheck /> },
      ],
    },
    {
      title: "Boards",
      items: [
        ...(has("results:moderate") ? [{ href: "/moderation", label: "Moderation", icon: <Icons.Scale /> }] : []),
        ...(has("results:board_approve", "results:faculty_approve") ? [{ href: "/boards", label: "Boards of examiners", icon: <Icons.Users /> }] : []),
        ...(has("results:senate_approve") ? [{ href: "/releases", label: "Results release", icon: <Icons.Send /> }] : []),
      ],
    },
    {
      title: "Awards",
      items: [
        ...(has("award:prepare", "award:confer") ? [{ href: "/graduation", label: "Graduation lists", icon: <Icons.GraduationCap /> }] : []),
        ...(has("transcript:issue") ? [{ href: "/transcripts", label: "Transcripts", icon: <Icons.FileText /> }] : []),
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
