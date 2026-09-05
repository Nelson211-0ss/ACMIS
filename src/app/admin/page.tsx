import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowUpRight, ClipboardCheck, GraduationCap, Inbox, Presentation, UserPlus, Wallet } from "lucide-react";
import { Card, CardBody, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ADMIN_NAV } from "@/lib/admin-nav";
import { currentStaff } from "@/lib/auth";
import { getAdminOverview, getSystemSettings } from "@/lib/data/repo";
import { can, STAFF_ROLE_LABELS } from "@/lib/permissions";
import { ssp } from "@/lib/format";

export const metadata: Metadata = { title: "Admin overview" };

export default async function AdminOverviewPage() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const [stats, settings] = await Promise.all([getAdminOverview(), getSystemSettings()]);

  const items = ADMIN_NAV.filter(
    (item) => item.href !== "/admin" && (!item.permission || can(staff.staffRole, item.permission, settings)),
  );

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          System overview
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Signed in as {staff.name} · {STAFF_ROLE_LABELS[staff.staffRole]}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={GraduationCap} label="Students" value={stats.totalStudents} note="Enrolled and active" />
        <Stat icon={UserPlus} label="Applicants" value={stats.totalApplicants} note="Have started an application" />
        <Stat
          icon={Inbox}
          label="Applications pending"
          value={stats.pendingApplications}
          note="Submitted, under review or interview"
        />
        <Stat
          icon={Wallet}
          label="Fees outstanding"
          value={ssp(stats.outstandingFeesSSP)}
          note="Across all students, this year"
        />
      </div>

      <Card>
        <CardBody className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px]">
          <span className="font-semibold text-ink">System status</span>
          <span className="flex items-center gap-1.5 text-muted">
            Maintenance mode
            <Badge tone={settings.maintenanceMode ? "gold" : "green"}>
              {settings.maintenanceMode ? "On" : "Off"}
            </Badge>
          </span>
          <span className="flex items-center gap-1.5 text-muted">
            Registration
            <Badge tone={settings.registrationOpen ? "green" : "neutral"}>
              {settings.registrationOpen ? "Open" : "Closed"}
            </Badge>
          </span>
          <span className="flex items-center gap-1.5 text-muted">
            Applications
            <Badge tone={settings.applicationsOpen ? "green" : "neutral"}>
              {settings.applicationsOpen ? "Open" : "Closed"}
            </Badge>
          </span>
        </CardBody>
      </Card>

      {/* Separate portals, not more items in the grid below — each department
          signs in and works at its own URL. */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Link href="/admissions">
          <Card interactive className="h-full">
            <CardBody className="flex items-center gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-brand-200 bg-brand-50">
                <ClipboardCheck className="h-[18px] w-[18px] text-brand-700" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13.5px] font-medium text-ink">Admissions Office</span>
                <span className="block text-[12px] text-muted">
                  Its own dashboard — schemes, applications, decisions
                </span>
              </span>
              <ArrowUpRight className="h-4 w-4 shrink-0 text-faint" aria-hidden />
            </CardBody>
          </Card>
        </Link>
        <Link href="/teaching">
          <Card interactive className="h-full">
            <CardBody className="flex items-center gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-brand-200 bg-brand-50">
                <Presentation className="h-[18px] w-[18px] text-brand-700" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13.5px] font-medium text-ink">Teaching</span>
                <span className="block text-[12px] text-muted">
                  Its own dashboard — courses, rosters, marks and publishing
                </span>
              </span>
              <ArrowUpRight className="h-4 w-4 shrink-0 text-faint" aria-hidden />
            </CardBody>
          </Card>
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <Link key={item.href} href={item.href}>
            <Card interactive className="h-full">
              <CardBody className="flex items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-brand-200 bg-brand-50">
                  <item.icon className="h-[18px] w-[18px] text-brand-700" aria-hidden />
                </span>
                <span className="min-w-0 flex-1 text-[13.5px] font-medium text-ink">
                  {item.label}
                </span>
                <ArrowUpRight className="h-4 w-4 shrink-0 text-faint" aria-hidden />
              </CardBody>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
