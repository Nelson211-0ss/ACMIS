import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Users } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings, listAllUsers } from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import { UsersTable } from "./table";

export const metadata: Metadata = { title: "Users" };

export default async function AdminUsersPage() {
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

  const rows = await listAllUsers();

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">Users</h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Every student, staff member and applicant the university has a
          record of, in one directory.
        </p>
      </div>

      <Card>
        <CardHeader
          icon={Users}
          title="Directory"
          description={`${rows.length} people · applicants are read-only here — there is no account status to change until they enrol`}
        />
        <div className="px-4 py-4 sm:px-5">
          <UsersTable rows={rows} currentStaffId={staff.id} />
        </div>
      </Card>
    </div>
  );
}
