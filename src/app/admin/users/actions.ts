"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import {
  getSystemSettings,
  logAudit,
  setStaffRole,
  setStaffStatus,
  setStudentStatus,
} from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import type { StaffRole, Student } from "@/lib/types";

async function requireManageUsers() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");
  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_users", settings)) redirect("/admin");
  return staff;
}

export async function changeStudentStatus(formData: FormData): Promise<void> {
  const actor = await requireManageUsers();
  const id = String(formData.get("id") ?? "");
  const status = String(formData.get("status") ?? "") as Student["status"];

  const student = await setStudentStatus(id, status);
  if (student) {
    await logAudit(actor.name, `Set student status to "${status}"`, `${student.firstName} ${student.lastName}`);
  }
  revalidatePath("/admin/users");
}

export async function changeStaffStatus(formData: FormData): Promise<void> {
  const actor = await requireManageUsers();
  const id = String(formData.get("id") ?? "");
  const status = String(formData.get("status") ?? "") as "active" | "suspended";

  // A super admin can be edited by another super admin, but never lock
  // themselves out with their own click — the row's controls are disabled in
  // the UI for the signed-in account, and this is the second line of defence.
  if (id === actor.id) redirect("/admin/users");

  const staff = await setStaffStatus(id, status);
  if (staff) await logAudit(actor.name, `Set staff status to "${status}"`, staff.name);
  revalidatePath("/admin/users");
}

export async function changeStaffRole(formData: FormData): Promise<void> {
  const actor = await requireManageUsers();
  const id = String(formData.get("id") ?? "");
  const staffRole = String(formData.get("staffRole") ?? "") as StaffRole;

  if (id === actor.id) redirect("/admin/users");

  const staff = await setStaffRole(id, staffRole);
  if (staff) await logAudit(actor.name, `Changed staff role to "${staffRole}"`, staff.name);
  revalidatePath("/admin/users");
}
