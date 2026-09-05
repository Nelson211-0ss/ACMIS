"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  CalendarDays,
  GraduationCap,
  LayoutDashboard,
  UserRound,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";

interface NavItem {
  href: string;
  label: string;
  /** Shorter label for the phone tab bar. */
  short: string;
  icon: LucideIcon;
}

export const PORTAL_NAV: NavItem[] = [
  { href: "/portal", label: "Dashboard", short: "Home", icon: LayoutDashboard },
  { href: "/portal/registration", label: "Course registration", short: "Courses", icon: BookOpen },
  { href: "/portal/results", label: "Results & transcript", short: "Results", icon: GraduationCap },
  { href: "/portal/finance", label: "Fees & payments", short: "Fees", icon: Wallet },
  { href: "/portal/timetable", label: "Timetable", short: "Timetable", icon: CalendarDays },
  { href: "/portal/profile", label: "My profile", short: "Profile", icon: UserRound },
];

/** `/portal` must match exactly; every other route matches its subtree. */
function useIsActive() {
  const pathname = usePathname();
  return (href: string) =>
    href === "/portal" ? pathname === href : pathname.startsWith(href);
}

/** Desktop rail. Navy fill, gold marker on the active row. */
export function SidebarNav() {
  const isActive = useIsActive();
  return (
    <nav aria-label="Portal sections" className="px-2 py-3">
      <ul className="space-y-0.5">
        {PORTAL_NAV.map(({ href, label, icon: Icon }) => {
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

/**
 * Phone tab bar. Fixed to the bottom because thumbs live there, and because a
 * hamburger drawer costs a tap and a JS bundle for no benefit.
 */
export function BottomTabs() {
  const isActive = useIsActive();
  // Profile is reachable from the header avatar, so it is dropped here to keep
  // five comfortable targets across a 360px screen.
  const tabs = PORTAL_NAV.filter((i) => i.href !== "/portal/profile");
  return (
    <nav
      aria-label="Portal sections"
      className="fixed inset-x-0 bottom-0 z-30 rounded-t-sm border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      <ul className="flex">
        {tabs.map(({ href, short, icon: Icon }) => {
          const active = isActive(href);
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium transition-colors",
                  active ? "text-brand-700" : "text-muted",
                )}
              >
                {active ? (
                  <span className="absolute inset-x-3 top-0 h-[2px] bg-gold-500" aria-hidden />
                ) : null}
                <Icon className="h-[19px] w-[19px]" aria-hidden />
                <span>{short}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
