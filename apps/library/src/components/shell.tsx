import * as Icons from "lucide-react"
import type { ReactNode } from "react"

import type { WhoAmI } from "@acmis/api-client"
import { AppShell, type NavSection } from "@acmis/ui/components/app-shell"
import { ModuleLauncher } from "@acmis/ui/components/module-launcher"

import { MODULE_KEY, MODULE_NAME } from "@/lib/config"

/**
 * The library's chrome.
 *
 * The nav splits the way the desk does, and the way the permissions do:
 * circulation, the catalogue, and acquisitions are three jobs held by
 * different people. A circulation assistant sees the desk and nothing else,
 * which is the shortest useful menu in the system.
 */
export function LibraryShell({
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
        { href: "/catalogue", label: "Catalogue", icon: <Icons.Search /> },
      ],
    },
    {
      title: "Circulation",
      items: [
        ...(has("library:circulate", "library:admin")
          ? [
              { href: "/desk", label: "Issue & return", icon: <Icons.ScanLine /> },
              { href: "/loans", label: "Loans", icon: <Icons.BookMarked /> },
              { href: "/members", label: "Members", icon: <Icons.Users /> },
              { href: "/fines", label: "Fines", icon: <Icons.Receipt /> },
            ]
          : []),
      ],
    },
    {
      title: "Collection",
      items: [
        ...(has("library:catalogue", "library:admin")
          ? [{ href: "/cataloguing", label: "Cataloguing", icon: <Icons.Library /> }]
          : []),
        ...(has("library:acquisitions", "library:admin")
          ? [
              { href: "/acquisitions", label: "Acquisitions", icon: <Icons.PackagePlus /> },
              { href: "/e-resources", label: "E-resources", icon: <Icons.Globe /> },
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
