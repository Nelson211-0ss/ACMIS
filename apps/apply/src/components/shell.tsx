import * as Icons from "lucide-react"
import type { ReactNode } from "react"

import type { WhoAmI } from "@acmis/api-client"
import { AppShell, type NavSection } from "@acmis/ui/components/app-shell"

import { MODULE_KEY, MODULE_NAME } from "@/lib/config"

/**
 * The applicant's chrome.
 *
 * Three destinations, and that is the whole of it. Every other app in ACMIS
 * is a tool somebody was trained on; this one is used once, by a person with
 * no training, who may be doing it on a borrowed phone at the end of a queue.
 * A rail of fourteen links would be a worse answer here even if there were
 * fourteen things to link to.
 *
 * No `ModuleLauncher`: an applicant is granted exactly one module, and the
 * launcher already returns nothing when there is only one — but it is left
 * out rather than relied upon, because a control that renders nothing is
 * still a prop that has to be read to know it renders nothing.
 */
export function ApplyShell({
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
        { href: "/", label: "My applications", icon: <Icons.FileText /> },
        { href: "/apply", label: "Start an application", icon: <Icons.FilePlus /> },
        { href: "/account", label: "My details", icon: <Icons.User /> },
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
      sections={sections}
      currentPath={currentPath}
      allowedModules={user.modules}
      user={{
        display_name: user.display_name,
        kind: user.kind,
        is_impersonated: user.is_impersonated,
      }}
    >
      {children}
    </AppShell>
  )
}
