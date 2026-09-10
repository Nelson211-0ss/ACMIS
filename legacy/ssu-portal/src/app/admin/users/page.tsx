import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { KeyRound, UserPlus, Users } from "lucide-react";
import Link from "next/link";
import { Card, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings, listAllUsers, listStaff } from "@/lib/data/repo";
import { can, STAFF_ROLES } from "@/lib/permissions";
import type { StaffRole } from "@/lib/types";
import { createStaffUser } from "./actions";
import { AddStaffForm } from "./add-staff-form";
import { RoleOverview } from "./role-overview";
import { UsersTable } from "./table";

export const metadata: Metadata = { title: "Users" };

export default async function AdminUsersPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_users", settings)) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include user management. Ask a
        super administrator to grant it on the Roles &amp; permissions page.
      </Callout>
    );
  }

  const [rows, allStaff] = await Promise.all([listAllUsers(), listStaff()]);

  // How many accounts sit on each role, so the overview below states a fact
  // rather than a guess.
  const counts = STAFF_ROLES.reduce(
    (acc, role) => {
      acc[role] = allStaff.filter((s) => s.staffRole === role).length;
      return acc;
    },
    {} as Record<StaffRole, number>,
  );

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">Users</h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Every student, staff member and applicant the university has a
          record of, in one directory.
        </p>
      </div>

      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
              <KeyRound className="h-[18px] w-[18px] shrink-0 text-brand-700" aria-hidden />
              Roles and what they grant
            </h2>
            <p className="mt-1 text-[13px] text-muted">
              Every staff account holds exactly one role, and the role decides
              the permissions.
            </p>
          </div>
          <Link
            href="/admin/roles"
            className="text-[13px] font-medium text-brand-700 underline decoration-brand-300 underline-offset-2 hover:decoration-brand-700"
          >
            Edit permissions
          </Link>
        </div>
        <div className="mt-4">
          <RoleOverview settings={settings} counts={counts} />
        </div>
      </section>

      <form action={createStaffUser}>
        <Card>
          <CardHeader
            icon={UserPlus}
            title="Add a staff member"
            description="Creates a dashboard account. Students and applicants arrive through admissions, not from here."
          />
          <AddStaffForm
            canGrantSuperAdmin={staff.staffRole === "super_admin"}
            error={error}
          />
        </Card>
      </form>

      <Card>
        <CardHeader
          icon={Users}
          title="Directory"
          description={`${rows.length} people · applicants are read-only here — there is no account status to change until they enrol`}
        />
        <div className="px-4 py-4 sm:px-5">
          <UsersTable rows={rows} currentStaffId={staff.id} settings={settings} />
        </div>
      </Card>
    </div>
  );
}
