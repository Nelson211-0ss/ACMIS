"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { ADMIN_NAV } from "@/lib/admin-nav";
import { can } from "@/lib/permissions";
import type { StaffRole, SystemSettings } from "@/lib/types";

function useIsActive() {
  const pathname = usePathname();
  return (href: string) =>
    href === "/admin" ? pathname === href : pathname.startsWith(href);
}

/**
 * Same visual language as the student portal's SidebarNav — same app,
 * elevated mode.
 *
 * Takes `staffRole` + `settings` rather than a pre-filtered item list: a
 * Server Component cannot hand a Client Component a prop containing icon
 * component references (they are functions, and functions cannot cross that
 * boundary), so the nav list and the permission filter both have to live in
 * this client module — the same reason PORTAL_NAV lives inside
 * portal-nav.tsx instead of being passed in.
 */
export function AdminSidebarNav({
  staffRole,
  settings,
}: {
  staffRole: StaffRole;
  settings: SystemSettings;
}) {
  const isActive = useIsActive();
  const items = ADMIN_NAV.filter((item) => !item.permission || can(staffRole, item.permission, settings));

  return (
    <nav aria-label="Admin sections" className="px-2 py-3">
      <ul className="space-y-0.5">
        {items.map(({ href, label, icon: Icon }) => {
          const active = isActive(href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex items-center gap-3 rounded px-3 py-2.5 text-[13.5px] transition-colors",
                  active
                    ? "bg-sidebar-active font-semibold text-sidebar-ink-strong"
                    : "font-medium text-sidebar-ink hover:bg-sidebar-active/55 hover:text-sidebar-ink-strong",
                )}
              >
                {active ? (
                  <span
                    className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r bg-gold-500"
                    aria-hidden
                  />
                ) : null}
                <Icon className="h-[17px] w-[17px] shrink-0" aria-hidden />
                <span className="truncate">{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
