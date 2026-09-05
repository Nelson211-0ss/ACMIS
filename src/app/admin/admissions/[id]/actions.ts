"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import {
  getSystemSettings,
  logAudit,
  recordDecision,
  setDocumentStatus,
} from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import type { ApplicationStatus } from "@/lib/types";

const DECISION_STATUSES: ApplicationStatus[] = [
  "submitted",
  "under_review",
  "interview",
  "admitted",
  "waitlisted",
  "rejected",
];

async function requireManageAdmissions() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");
  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_admissions", settings)) redirect("/admin");
  return staff;
}

export async function saveDecision(applicationId: string, formData: FormData): Promise<void> {
  const actor = await requireManageAdmissions();

  const statusRaw = String(formData.get("status") ?? "");
  const status = DECISION_STATUSES.includes(statusRaw as ApplicationStatus)
    ? (statusRaw as ApplicationStatus)
    : "under_review";
  const message = String(formData.get("message") ?? "").trim();
  const programmeId = String(formData.get("programmeId") ?? "") || undefined;

  const application = await recordDecision(applicationId, status, message, programmeId);
  if (application) {
    await logAudit(actor.name, `Recorded admissions decision: ${status}`, application.reference);
  }

  revalidatePath(`/admin/admissions/${applicationId}`);
  revalidatePath("/admin/admissions");
  // The applicant sees their decision on the same review page they submitted from.
  revalidatePath(`/apply/${applicationId}`, "layout");
  revalidatePath("/apply");
}

export async function changeDocumentStatus(applicationId: string, formData: FormData): Promise<void> {
  const actor = await requireManageAdmissions();

  const documentId = String(formData.get("documentId") ?? "");
  const statusRaw = String(formData.get("status") ?? "");
  const status = statusRaw === "verified" || statusRaw === "rejected" ? statusRaw : "pending";

  const application = await setDocumentStatus(applicationId, documentId, status);
  if (application) {
    await logAudit(actor.name, `Marked a document "${status}"`, application.reference);
  }
  revalidatePath(`/admin/admissions/${applicationId}`);
}
