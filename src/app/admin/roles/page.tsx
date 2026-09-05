import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { KeyRound } from "lucide-react";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings } from "@/lib/data/repo";
import { ALL_PERMISSIONS, can, PERMISSION_LABELS, STAFF_ROLE_LABELS } from "@/lib/permissions";
import type { StaffRole } from "@/lib/types";
import { saveRolePermissions } from "./actions";

export const metadata: Metadata = { title: "Roles & permissions" };

const EDITABLE_ROLES: Exclude<StaffRole, "super_admin">[] = ["registrar", "bursar", "viewer"];

export default async function AdminRolesPage() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_roles", settings)) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include role management.
      </Callout>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Roles &amp; permissions
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          What each staff role can do in this dashboard. Super administrator is
          fixed at every permission and is not shown below — a role that could
          edit its own ceiling would not be a ceiling.
        </p>
      </div>

      <form action={saveRolePermissions}>
        <Card>
          <CardHeader icon={KeyRound} title="Permission matrix" />
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Permission</Th>
                  {EDITABLE_ROLES.map((role) => (
                    <Th key={role} className="text-center">
                      {STAFF_ROLE_LABELS[role]}
                    </Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ALL_PERMISSIONS.map((permission) => (
                  <Tr key={permission}>
                    <Td className="font-medium text-ink">{PERMISSION_LABELS[permission]}</Td>
                    {EDITABLE_ROLES.map((role) => (
                      <Td key={role} className="text-center">
                        <input
                          type="checkbox"
                          name={`${role}::${permission}`}
                          defaultChecked={settings.rolePermissions[role]?.includes(permission)}
                          className="h-4 w-4 accent-brand-700"
                          aria-label={`${STAFF_ROLE_LABELS[role]}: ${PERMISSION_LABELS[permission]}`}
                        />
                      </Td>
                    ))}
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
          <CardFooter>
            <Button type="submit" size="sm">
              Save permissions
            </Button>
          </CardFooter>
        </Card>
      </form>

      <Card>
        <CardBody className="text-[13px] leading-relaxed text-muted">
          Changes apply immediately: a staff member&rsquo;s sidebar and page access
          are computed from this matrix on every request, not cached at sign-in.
        </CardBody>
      </Card>
    </div>
  );
}
