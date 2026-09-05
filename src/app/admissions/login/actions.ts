"use server";

import { redirect } from "next/navigation";
import { startSession } from "@/lib/auth";
import { getStaffByEmail, getSystemSettings } from "@/lib/data/repo";
import { can } from "@/lib/permissions";

/**
 * The Admissions Office's own front door.
 *
 * A separate sign-in from the general staff/student one at `/login` — this
 * one only recognises staff with admissions access, so a registrar bookmarks
 * one clean URL instead of the whole-institution staff screen.
 */
export type SignInState = { error?: string } | undefined;

export async function signInAdmissions(
  _prev: SignInState,
  formData: FormData,
): Promise<SignInState> {
  const email = String(formData.get("email") ?? "").trim();
  if (!email) return { error: "Enter your work email address." };

  const staff = await getStaffByEmail(email);
  if (!staff) {
    return { error: "No staff account is registered with that email address." };
  }
  if (staff.status !== "active") {
    return { error: "This staff account has been suspended. Contact a super administrator." };
  }

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_admissions", settings)) {
    return {
      error:
        "This account does not have admissions office access. Use the general staff sign-in instead.",
    };
  }

  await startSession({ role: "admin", subjectId: staff.id });
  redirect("/admissions");
}

/** One-click entry to the seeded registrar account, offered on the sign-in screen. */
export async function signInAdmissionsDemo(): Promise<void> {
  await startSession({ role: "admin", subjectId: "staff-2" });
  redirect("/admissions");
}
