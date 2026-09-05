"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import { createScheme, getSystemSettings, logAudit, setSchemeStatus } from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import type { SchemeStatus } from "@/lib/types";

async function requireManageAdmissions() {
  const staff = await currentStaff();
  if (!staff) redirect("/admissions/login");
  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_admissions", settings)) redirect("/admissions/login");
  return staff;
}

export async function createSchemeAction(formData: FormData): Promise<void> {
  const actor = await requireManageAdmissions();

  const name = String(formData.get("name") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();
  const opensAt = String(formData.get("opensAt") ?? "");
  const closesAt = String(formData.get("closesAt") ?? "");
  const resultsBy = String(formData.get("resultsBy") ?? "");
  const semesterStarts = String(formData.get("semesterStarts") ?? "");
  const applicationFeeSSP = Number(formData.get("applicationFeeSSP") ?? 0);
  const programmeIds = formData.getAll("programmeIds").map(String);

  if (!name || !code || !opensAt || !closesAt || programmeIds.length === 0) {
    // A hand-crafted form request missing required fields is simply dropped —
    // the real form always fills these in, and this route has no untrusted
    // public caller.
    redirect("/admissions/schemes");
  }

  const scheme = await createScheme({
    name,
    code,
    description,
    opensAt,
    closesAt,
    resultsBy,
    semesterStarts,
    applicationFeeSSP: Number.isFinite(applicationFeeSSP) ? Math.max(0, applicationFeeSSP) : 0,
    programmeIds,
  });

  await logAudit(actor.name, "Created an admission scheme (draft)", scheme.name);
  revalidatePath("/admissions/schemes");
}

export async function setSchemeStatusAction(formData: FormData): Promise<void> {
  const actor = await requireManageAdmissions();

  const id = String(formData.get("id") ?? "");
  const status = String(formData.get("status") ?? "") as SchemeStatus;

  const scheme = await setSchemeStatus(id, status);
  if (scheme) {
    await logAudit(actor.name, `Set scheme status to "${status}"`, scheme.name);
  }
  revalidatePath("/admissions/schemes");
  revalidatePath("/apply");
}
