"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import {
  addFeeItem,
  getStudent,
  getSystemSettings,
  logAudit,
  settlePayment,
} from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import { ssp } from "@/lib/format";
import type { Permission } from "@/lib/types";

async function requirePermission(permission: Permission) {
  const staff = await currentStaff();
  if (!staff) redirect("/login");
  const settings = await getSystemSettings();
  if (!can(staff.staffRole, permission, settings)) redirect("/admin");
  return staff;
}

/**
 * Clear or reject one bank deposit slip.
 *
 * Both outcomes are audited by name. A confirmation releases a student's
 * results and registration, and a rejection is the kind of decision somebody
 * will come to the bursary window to argue about — neither should be
 * anonymous.
 */
export async function decidePayment(formData: FormData): Promise<void> {
  const actor = await requirePermission("verify_payments");

  const paymentId = String(formData.get("paymentId") ?? "");
  const outcome = String(formData.get("outcome") ?? "");
  if (outcome !== "confirmed" && outcome !== "failed") {
    redirect("/admin/finance?error=" + encodeURIComponent("Unknown decision."));
  }

  const payment = await settlePayment(paymentId, outcome);
  if (!payment) {
    redirect(
      "/admin/finance?error=" +
        encodeURIComponent("That payment has already been decided."),
    );
  }

  const student = await getStudent(payment.studentId);
  await logAudit(
    actor.name,
    outcome === "confirmed"
      ? `Confirmed a ${ssp(payment.amountSSP)} deposit slip (${payment.reference})`
      : `Rejected a ${ssp(payment.amountSSP)} deposit slip (${payment.reference})`,
    student ? `${student.firstName} ${student.lastName}` : payment.studentId,
  );

  revalidatePath("/admin/finance");
  // The student's own finance page and anything gated on a blocking balance.
  revalidatePath("/portal", "layout");
}

/** A correction, waiver or extra charge against one student's account. */
export async function addCharge(formData: FormData): Promise<void> {
  const actor = await requirePermission("manage_fees");

  const studentId = String(formData.get("studentId") ?? "");
  const description = String(formData.get("description") ?? "").trim();
  const amountRaw = Number(formData.get("amountSSP"));
  const dueDate = String(formData.get("dueDate") ?? "");
  const blocking = formData.has("blocking");

  const student = await getStudent(studentId);
  if (!student) {
    redirect("/admin/finance?error=" + encodeURIComponent("Choose a student."));
  }
  if (!description) {
    redirect(
      "/admin/finance?error=" + encodeURIComponent("Describe what the charge is for."),
    );
  }
  // A negative amount is the whole point of a waiver, so only zero and
  // nonsense are rejected.
  if (!Number.isFinite(amountRaw) || amountRaw === 0) {
    redirect(
      "/admin/finance?error=" +
        encodeURIComponent("Enter an amount. Use a negative number for a waiver."),
    );
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dueDate)) {
    redirect("/admin/finance?error=" + encodeURIComponent("Enter a due date."));
  }

  await addFeeItem({
    studentId,
    description,
    amountSSP: Math.round(amountRaw),
    dueDate,
    blocking,
    semester: student.currentSemester,
  });

  await logAudit(
    actor.name,
    `${amountRaw < 0 ? "Waived" : "Charged"} ${ssp(Math.abs(Math.round(amountRaw)))} — ${description}`,
    `${student.firstName} ${student.lastName}`,
  );

  revalidatePath("/admin/finance");
  revalidatePath("/portal", "layout");
}
