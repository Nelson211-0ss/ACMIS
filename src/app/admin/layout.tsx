import Link from "next/link";
import { redirect } from "next/navigation";
import { Wordmark } from "@/components/brand";
import { AdminSidebarNav } from "@/components/admin-nav";
import { ADMIN_NAV } from "@/lib/admin-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { Badge } from "@/components/ui/badge";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings } from "@/lib/data/repo";
import { can, STAFF_ROLE_LABELS } from "@/lib/permissions";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  const items = ADMIN_NAV.filter(
    (item) => !item.permission || can(staff.staffRole, item.permission, settings),
  );

  return (
    <div className="min-h-dvh lg:flex">
      {/* Same navy rail as the student portal — this is the same app in a
          more powerful mode, not a different product. */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-line bg-sidebar lg:sticky lg:top-0 lg:flex lg:h-dvh">
        <div className="border-b border-sidebar-line px-4 py-4">
          <Wordmark href="/admin" tone="dark" />
        </div>
        <div className="border-b border-sidebar-line px-4 py-2.5">
          <Badge tone="gold">Admin mode</Badge>
        </div>
        <div className="flex-1 overflow-y-auto scroll-thin">
          <AdminSidebarNav staffRole={staff.staffRole} settings={settings} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 rounded-b-sm border-b border-sidebar-line bg-sidebar lg:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <Wordmark href="/admin" tone="dark" />
            <div className="flex shrink-0 items-center gap-1">
              <ThemeToggle tone="dark" />
              <Link href="/admin" aria-label="Admin overview" className="p-1">
                <Badge tone="gold">Admin</Badge>
              </Link>
            </div>
          </div>
        </header>

        <div className="hidden border-b border-line bg-surface px-6 py-2 lg:sticky lg:top-0 lg:z-10 lg:block lg:rounded-b-sm">
          <div className="flex items-center gap-x-3 gap-y-1.5 text-[13px]">
            <span className="font-medium text-ink">
              {STAFF_ROLE_LABELS[staff.staffRole]}
            </span>
            <span className="text-line-strong" aria-hidden>
              /
            </span>
            <span className="text-muted">Super admin dashboard</span>
            <ThemeToggle className="ml-auto" />
            <UserMenu
              subject={splitStaffName(staff.name, staff.email)}
              href="/admin"
              className="border-l border-line pl-2"
            />
          </div>
        </div>

        {/* Phone: an inline nav strip since there is no bottom-tab equivalent for admin. */}
        <nav aria-label="Admin sections" className="scroll-thin overflow-x-auto border-b border-line bg-surface px-3 py-2 lg:hidden">
          <ul className="flex gap-1.5">
            {items.map((item) => (
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

function splitStaffName(name: string, email: string) {
  const [firstName, ...rest] = name.split(" ");
  return { firstName, lastName: rest.join(" "), identifier: email };
}
