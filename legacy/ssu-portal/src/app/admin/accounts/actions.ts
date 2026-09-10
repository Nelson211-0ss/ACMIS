"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import { randomToken, sign } from "@/lib/crypto";
import {
  createPasswordReset,
  findCredentialByEmail,
  getSystemSettings,
  logAudit,
  setStaffStatus,
  setStudentStatus,
} from "@/lib/data/repo";
import { can } from "@/lib/permissions";

const RESET_TTL_MINUTES = 60;

async function requireAccountRecovery() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");
  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_accounts", settings)) redirect("/admin");
  return staff;
}

/**
 * Issue a reset link on someone's behalf.
 *
 * IT support never sees or sets the password itself — it mints the same
 * single-use link the "forgot password" form would, and the account holder
 * chooses their own. That keeps a helpdesk from being able to sign in as a
 * student and, just as importantly, keeps them from having to be trusted not
 * to.
 */
export async function issueResetLink(formData: FormData): Promise<void> {
  const actor = await requireAccountRecovery();
  const email = String(formData.get("email") ?? "").trim();

  const credential = await findCredentialByEmail(email);
  if (!credential) {
    redirect(
      "/admin/accounts?error=" +
        encodeURIComponent("No student, applicant or staff account uses that address."),
    );
  }

  const token = randomToken();
  await createPasswordReset({
    tokenHash: sign(`reset:${token}`),
    subjectKind: credential.kind,
    subjectId: credential.id,
    expiresAt: new Date(Date.now() + RESET_TTL_MINUTES * 60_000).toISOString(),
  });

  await logAudit(actor.name, "Issued a password reset link", credential.email);
  revalidatePath("/admin/accounts");

  // No mail service is wired up, so the link comes back to the helpdesk to
  // read out or send on. Once email is connected this should send instead of
  // display — a link on screen is one shoulder away from being someone else's.
  redirect(
    `/admin/accounts?issued=${encodeURIComponent(credential.email)}&token=${encodeURIComponent(token)}`,
  );
}

/** Unlock a suspended account, or suspend one that is being misused. */
export async function setAccountStatus(formData: FormData): Promise<void> {
  const actor = await requireAccountRecovery();

  const kind = String(formData.get("kind") ?? "");
  const id = String(formData.get("id") ?? "");
  const status = String(formData.get("status") ?? "");

  if (kind === "staff") {
    if (id === actor.id) {
      redirect(
        "/admin/accounts?error=" +
          encodeURIComponent("You cannot change your own account's status."),
      );
    }
    if (status !== "active" && status !== "suspended") {
      redirect("/admin/accounts?error=" + encodeURIComponent("Unknown status."));
    }
    const staff = await setStaffStatus(id, status);
    if (staff) {
      await logAudit(actor.name, `Set staff account to "${status}"`, staff.name);
    }
  } else if (kind === "student") {
    if (status !== "active" && status !== "suspended") {
      redirect("/admin/accounts?error=" + encodeURIComponent("Unknown status."));
    }
    const student = await setStudentStatus(id, status);
    if (student) {
      await logAudit(
        actor.name,
        `Set student account to "${status}"`,
        `${student.firstName} ${student.lastName}`,
      );
    }
  }

  revalidatePath("/admin/accounts");
  revalidatePath("/admin/users");
}
