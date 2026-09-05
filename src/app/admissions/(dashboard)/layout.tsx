import Link from "next/link";
import { redirect } from "next/navigation";
import { ClipboardCheck } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { AdmissionsSidebarNav } from "@/components/admissions-nav";
import { ADMISSIONS_NAV } from "@/lib/admissions-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings } from "@/lib/data/repo";
import { can, STAFF_ROLE_LABELS } from "@/lib/permissions";

/**
 * The Admissions Office's own portal — a separate shell from /admin, not a
 * filtered corner of it. Signing in here (at /admissions/login) is a
 * separate front door, and everything under this layout assumes the visitor
 * is here to run admissions, nothing else.
 */
export default async function AdmissionsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const staff = await currentStaff();
  if (!staff) redirect("/admissions/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_admissions", settings)) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <Callout tone="warning" title="Restricted">
          Your account ({STAFF_ROLE_LABELS[staff.staffRole]}) does not have
          admissions office access.
        </Callout>
      </div>
    );
  }

  return (
    <div className="min-h-dvh lg:flex">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-line bg-sidebar lg:sticky lg:top-0 lg:flex lg:h-dvh">
        <div className="px-4 pb-3 pt-4">
          <Wordmark href="/admissions" tone="dark" />
        </div>
        <div className="flex items-center gap-1.5 px-4 pb-3">
          <ClipboardCheck className="h-3.5 w-3.5 text-gold-500" aria-hidden />
          <Badge tone="gold">Admissions Office</Badge>
        </div>
        <div className="flex-1 overflow-y-auto scroll-thin">
          <AdmissionsSidebarNav />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 rounded-b-sm border-b border-sidebar-line bg-sidebar lg:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <Wordmark href="/admissions" tone="dark" />
            <div className="flex shrink-0 items-center gap-1">
              <ThemeToggle tone="dark" />
              <Link href="/admissions" aria-label="Applications queue" className="p-1">
                <Badge tone="gold">Admissions</Badge>
              </Link>
            </div>
          </div>
        </header>

        <div className="hidden border-b border-line bg-surface px-6 py-2 lg:sticky lg:top-0 lg:z-10 lg:block lg:rounded-b-sm">
          <div className="flex items-center gap-x-3 gap-y-1.5 text-[13px]">
            <span className="font-medium text-ink">{STAFF_ROLE_LABELS[staff.staffRole]}</span>
            <span className="text-line-strong" aria-hidden>
              /
            </span>
            <span className="text-muted">Admissions Office</span>
            <ThemeToggle className="ml-auto" />
            <UserMenu
              subject={{ firstName: staff.name.split(" ")[0], lastName: staff.name.split(" ").slice(1).join(" "), identifier: staff.email }}
              href="/admissions"
              className="border-l border-line pl-2"
            />
          </div>
        </div>

        <nav aria-label="Admissions sections" className="scroll-thin overflow-x-auto border-b border-line bg-surface px-3 py-2 lg:hidden">
          <ul className="flex gap-1.5">
            {ADMISSIONS_NAV.map((item) => (
              <li key={item.href} className="shrink-0">
                <Link
                  href={item.href}
                  className="flex items-center gap-1.5 rounded border border-line-strong px-2.5 py-1.5 text-[12.5px] font-medium text-ink-soft transition-colors hover:border-brand-300 hover:text-ink"
                >
                  <item.icon className="h-3.5 w-3.5" aria-hidden />
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <main id="main" className="min-w-0 flex-1 px-4 py-5 sm:px-6 lg:pb-8">
          {children}
        </main>
      </div>
    </div>
  );
}
