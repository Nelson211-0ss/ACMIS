import Link from "next/link";
import { redirect } from "next/navigation";
import { Presentation, Stamp } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings } from "@/lib/data/repo";
import { can, STAFF_ROLE_LABELS } from "@/lib/permissions";

/**
 * A lecturer's whole business here is one thing — their own courses — so
 * unlike /admin or /admissions this gets no sidebar, just the same identity
 * strip every other shell uses. See src/app/apply/layout.tsx for the same
 * "header only" shape.
 */
export default async function TeachingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  // Two different people live here: a lecturer who enters marks, and a head of
  // department who signs them off. The head does NOT hold manage_results — the
  // point of the role is that they do not grade — so gating on that one
  // permission alone would lock them out of the approvals queue.
  const mayTeach = can(staff.staffRole, "manage_results", settings);
  const mayApprove = can(staff.staffRole, "approve_results", settings);

  if (!mayTeach && !mayApprove) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <Callout tone="warning" title="Restricted">
          Your account ({STAFF_ROLE_LABELS[staff.staffRole]}) does not have
          teaching access.
        </Callout>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 rounded-b-sm border-b border-line bg-surface">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Wordmark href="/teaching" />
          <div className="flex shrink-0 items-center gap-2">
            {mayTeach ? (
              <Link
                href="/teaching"
                className="hidden rounded px-2.5 py-1.5 text-[13px] font-medium text-ink-soft transition-colors hover:bg-sunken sm:inline-flex"
              >
                My courses
              </Link>
            ) : null}
            {mayApprove ? (
              <Link
                href="/teaching/approvals"
                className="inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-[13px] font-medium text-ink-soft transition-colors hover:bg-sunken"
              >
                <Stamp className="h-4 w-4" aria-hidden />
                <span className="hidden sm:inline">Approvals</span>
              </Link>
            ) : null}
            <Badge tone="gold" className="hidden sm:inline-flex">
              <Presentation className="h-3 w-3" aria-hidden />
              Teaching
            </Badge>
            <ThemeToggle />
            <UserMenu
              subject={{
                firstName: staff.name.split(" ")[0],
                lastName: staff.name.split(" ").slice(1).join(" "),
                identifier: staff.email,
              }}
              href="/teaching"
            />
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-4 py-5 sm:px-6">
        {children}
      </main>
    </div>
  );
}
