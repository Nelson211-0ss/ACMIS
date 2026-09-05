import Link from "next/link";
import { redirect } from "next/navigation";
import { Wordmark } from "@/components/brand";
import { BottomTabs, SidebarNav } from "@/components/portal-nav";
import { OfflineBanner } from "@/components/offline-form";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { currentStudent } from "@/lib/auth";
import { institution } from "@/lib/institution";
import { programmeById } from "@/lib/data/reference";

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
        <div className="px-4 pb-3 pt-4">
          <Wordmark href="/portal" tone="dark" />
        </div>

        {/* Identity and sign-out now live top right — see the context strip. */}
        <div className="flex-1 overflow-y-auto scroll-thin">
          <SidebarNav />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Phone header. Navy so the brand reads the same on both layouts. */}
        <header className="sticky top-0 z-20 rounded-b-sm border-b border-sidebar-line bg-sidebar lg:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <Wordmark href="/portal" tone="dark" />
            <div className="flex shrink-0 items-center gap-1">
              <ThemeToggle tone="dark" />
              <Link href="/portal/profile" aria-label="My profile">
                <Avatar
                  firstName={student.firstName}
                  lastName={student.lastName}
                  photoUrl={student.photoUrl}
                />
              </Link>
            </div>
          </div>
        </header>

        {/* Desktop context strip: who you are and where you are in the degree. */}
        <div className="hidden border-b border-line bg-surface px-6 py-2 lg:sticky lg:top-0 lg:z-10 lg:block lg:rounded-b-sm">
          <div className="flex items-center gap-x-3 gap-y-1.5 text-[13px]">
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
            <ThemeToggle />
            <UserMenu
              subject={{ ...student, identifier: student.studentNumber }}
              className="border-l border-line pl-2"
            />
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
