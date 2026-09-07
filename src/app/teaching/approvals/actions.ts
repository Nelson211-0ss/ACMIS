"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import {
  decideResultSubmission,
  getCourse,
  getResultSubmission,
  getSystemSettings,
  logAudit,
} from "@/lib/data/repo";
import { can } from "@/lib/permissions";

/**
 * Approve or return one course's marks.
 *
 * Approving publishes: `decideResultSubmission` flips the results to visible
 * as part of the same call, so there is no separate publish step anyone could
 * perform without a decision behind it.
 */
export async function decideApproval(formData: FormData): Promise<void> {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "approve_results", settings)) redirect("/teaching");

  const courseId = String(formData.get("courseId") ?? "");
  const outcome = String(formData.get("outcome") ?? "");
  const note = String(formData.get("note") ?? "").trim();

  if (outcome !== "approved" && outcome !== "returned") {
    redirect("/teaching/approvals?error=" + encodeURIComponent("Unknown decision."));
  }

  const course = await getCourse(courseId);
  if (!course) redirect("/teaching/approvals");

  // Whoever entered the marks does not get to sign them off, even if their
  // role would otherwise allow it — a super admin holds every permission, so
  // without this the one person who could do both ends is exactly the person
  // most able to. The second pair of eyes is the whole point of the step.
  const pending = await getResultSubmission(courseId);
  if (pending?.submittedBy === staff.id) {
    redirect(
      "/teaching/approvals?error=" +
        encodeURIComponent(
          "You submitted these marks, so you cannot also approve them. Ask another head of department.",
        ),
    );
  }

  const submission = await decideResultSubmission(
    courseId,
    staff.id,
    outcome,
    note || undefined,
  );
  if (!submission) {
    redirect(
      "/teaching/approvals?error=" +
        encodeURIComponent("That submission has already been decided."),
    );
  }

  await logAudit(
    staff.name,
    outcome === "approved"
      ? "Approved and published results"
      : `Returned results for correction${note ? `: ${note}` : ""}`,
    course.code,
  );

  revalidatePath("/teaching/approvals");
  revalidatePath(`/teaching/${courseId}`);
  revalidatePath("/portal/results");
  revalidatePath("/portal");
}
