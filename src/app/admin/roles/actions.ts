"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings, logAudit, updateSystemSettings } from "@/lib/data/repo";
import { ALL_PERMISSIONS, can } from "@/lib/permissions";
import type { Permission, StaffRole } from "@/lib/types";

const EDITABLE_ROLES: Exclude<StaffRole, "super_admin">[] = ["registrar", "bursar", "viewer"];

export async function saveRolePermissions(formData: FormData): Promise<void> {
  const actor = await currentStaff();
  if (!actor) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(actor.staffRole, "manage_roles", settings)) redirect("/admin");

  const rolePermissions = { ...settings.rolePermissions };
  for (const role of EDITABLE_ROLES) {
    rolePermissions[role] = ALL_PERMISSIONS.filter((permission) =>
      formData.has(`${role}::${permission}`),
    ) as Permission[];
  }

  await updateSystemSettings({ rolePermissions });
  await logAudit(actor.name, "Updated the role permission matrix");
  revalidatePath("/admin/roles");
  revalidatePath("/admin");
}
