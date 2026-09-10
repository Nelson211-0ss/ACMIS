import * as Icons from "lucide-react"
import type { ReactNode } from "react"

import type { WhoAmI } from "@acmis/api-client"
import { AppShell, type NavSection } from "@acmis/ui/components/app-shell"
import { ModuleLauncher } from "@acmis/ui/components/module-launcher"

import { MODULE_KEY, MODULE_NAME } from "@/lib/config"

export function LearningShell({
  user,
  institution,
  currentPath,
  counts,
  children,
}: {
  user: WhoAmI
  institution: { name: string; short_name: string; crest_url: string | null } | null
  currentPath: string
  counts?: { marking?: number; review?: number }
  children: ReactNode
}) {
  const has = (...codes: string[]) => codes.some((c) => user.permissions.includes(c))

  const sections: NavSection[] = [
    {
      items: [
        { href: "/", label: "My teaching", icon: <Icons.LayoutDashboard /> },
        { href: "/spaces", label: "Course spaces", icon: <Icons.FolderOpen /> },
      ],
    },
    {
      title: "Assessment",
      items: [
        {
          href: "/assessments",
          label: "Tests & quizzes",
          icon: <Icons.FileQuestion />,
          badge: counts?.marking,
        },
        ...(has("learning:manage_banks", "learning:teach")
          ? [{ href: "/banks", label: "Question banks", icon: <Icons.Library /> }]
          : []),
        ...(has("learning:review_paper")
          ? [
              {
                href: "/review",
                label: "Papers to review",
                icon: <Icons.ShieldCheck />,
                badge: counts?.review,
              },
            ]
          : []),
      ],
    },
    {
      title: "Students",
      items: [
        ...(has("learning:read_engagement")
          ? [{ href: "/engagement", label: "Engagement", icon: <Icons.Activity /> }]
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
