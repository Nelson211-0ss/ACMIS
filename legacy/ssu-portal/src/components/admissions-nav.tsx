"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { ADMISSIONS_NAV } from "@/lib/admissions-nav";

function useIsActive() {
  const pathname = usePathname();
  return (href: string) => {
    if (href === "/admissions") {
      // A review sits at /admissions/[id] — a dynamic child of the queue —
      // but /admissions/schemes is a sibling section, not a child of it.
      return pathname === "/admissions" || (pathname.startsWith("/admissions/") && !pathname.startsWith("/admissions/schemes"));
    }
    return pathname.startsWith(href);
  };
}

/** The Admissions Office's own two-item rail — nothing else lives in this portal. */
export function AdmissionsSidebarNav() {
  const isActive = useIsActive();

  return (
    <nav aria-label="Admissions sections" className="px-2 py-3">
      <ul className="space-y-0.5">
        {ADMISSIONS_NAV.map(({ href, label, icon: Icon }) => {
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
                <span
                  className={cn(
                    "absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r bg-gold-500 transition-transform duration-200 motion-reduce:transition-none",
                    active ? "scale-y-100" : "scale-y-0",
                  )}
                  aria-hidden
                />
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
