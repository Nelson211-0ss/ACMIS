import { redirect } from "next/navigation";
import { LogOut } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { BottomTabs, SidebarNav } from "@/components/portal-nav";
import { OfflineBanner } from "@/components/offline-form";
import { Badge } from "@/components/ui/badge";
import { currentStudent } from "@/lib/auth";
import { institution } from "@/lib/institution";
import { initials } from "@/lib/format";
import { programmeById } from "@/lib/data/reference";
import { signOut } from "@/app/login/actions";

export default async function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const student = await currentStudent();
  if (!student) redirect("/login");

  const programme = programmeById(student.programmeId);

  return (
    <div className="min-h-dvh lg:flex">
      {/* Desktop rail. Flat navy, hairline divider, no gradient. */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-line bg-sidebar lg:sticky lg:top-0 lg:flex lg:h-dvh">
        <div className="border-b border-sidebar-line px-4 py-4">
          <Wordmark href="/portal" tone="dark" />
        </div>

        <div className="flex-1 overflow-y-auto scroll-thin">
          <SidebarNav />
        </div>

        <div className="border-t border-sidebar-line p-3">
          <div className="mb-2.5 flex items-center gap-2.5 px-1">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-700 text-[13px] font-semibold text-white">
              {initials(student.firstName, student.lastName)}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-medium text-sidebar-ink-strong">
                {student.firstName} {student.lastName}
              </span>
              <span className="nums block truncate text-[11.5px] text-sidebar-ink">
                {student.studentNumber}
              </span>
            </span>
          </div>
          <form action={signOut}>
            <button
              type="submit"
              className="flex w-full items-center gap-2.5 rounded-[--radius] px-3 py-2 text-[13px] font-medium text-sidebar-ink transition-colors hover:bg-sidebar-active hover:text-sidebar-ink-strong"
            >
              <LogOut className="h-4 w-4" aria-hidden />
              Sign out
            </button>
          </form>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Phone header. Navy so the brand reads the same on both layouts. */}
        <header className="sticky top-0 z-20 border-b border-sidebar-line bg-sidebar lg:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <Wordmark href="/portal" tone="dark" />
            <a
              href="/portal/profile"
              aria-label="My profile"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-700 text-[13px] font-semibold text-white"
            >
              {initials(student.firstName, student.lastName)}
            </a>
          </div>
        </header>

        {/* Desktop context strip: who you are and where you are in the degree. */}
        <div className="hidden border-b border-line bg-surface px-6 py-3 lg:block">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px]">
            <span className="font-medium text-ink">{programme?.name}</span>
            <span className="text-line-strong" aria-hidden>
              /
            </span>
            <span className="text-muted">
              Year {student.yearOfStudy}, Semester {student.currentSemester}
            </span>
            <span className="text-line-strong" aria-hidden>
              /
            </span>
            <span className="text-muted">{institution.academicYear}</span>
            <Badge tone={student.status === "active" ? "green" : "gold"} className="ml-auto">
              {student.status === "active" ? "Registered" : student.status}
            </Badge>
          </div>
        </div>

        <OfflineBanner />

        {/* pb-20 clears the fixed phone tab bar. */}
        <main id="main" className="min-w-0 flex-1 px-4 py-5 pb-20 sm:px-6 lg:pb-8">
          {children}
        </main>
      </div>

      <BottomTabs />
    </div>
  );
}
