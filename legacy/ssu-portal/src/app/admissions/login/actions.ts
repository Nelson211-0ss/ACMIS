"use server";

import { redirect } from "next/navigation";
import { startSession } from "@/lib/auth";
import { verifyPassword } from "@/lib/crypto";
import { findCredentialByEmail, getStaff, getSystemSettings, logAudit } from "@/lib/data/repo";
import { DEMO_ACCOUNTS, DEMO_PASSWORD } from "@/lib/demo-accounts";
import { can } from "@/lib/permissions";

/**
 * The Admissions Office's own front door.
 *
 * A separate sign-in from the general staff/student one at `/login` — this
 * one only recognises staff with admissions access, so a registrar bookmarks
 * one clean URL instead of the whole-institution staff screen.
 *
 * The password is checked here exactly as it is at /login, and for the same
 * reason the errors stay vague: a precise "no such account" turns either
 * sign-in page into a way to enumerate who works here.
 */
export type SignInState = { error?: string } | undefined;

const DUMMY_HASH =
  "scrypt$65536$8$1$00000000000000000000000000000000$0000000000000000000000000000000000000000000000000000000000000000";

export async function signInAdmissions(
  _prev: SignInState,
  formData: FormData,
): Promise<SignInState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!email || !password) {
    return { error: "Enter your work email address and password." };
  }

  const credential = await findCredentialByEmail(email);
  const ok = await verifyPassword(password, credential?.passwordHash ?? DUMMY_HASH);

  if (!credential || !ok || credential.kind !== "staff") {
    return { error: "That email address and password do not match a staff account." };
  }
  if (!credential.active) {
    return { error: "This staff account is suspended. Contact a super administrator." };
  }

  const staff = await getStaff(credential.id);
  if (!staff) {
    return { error: "That email address and password do not match a staff account." };
  }

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_admissions", settings)) {
    return {
      error:
        "This account does not have admissions office access. Use the general staff sign-in instead.",
    };
  }

  await startSession({ role: "admin", subjectId: staff.id });
  await logAudit(staff.name, "Signed in to the Admissions Office");
  redirect("/admissions");
}

/**
 * One-click entry to the seeded registrar account.
 *
 * Goes through `signInAdmissions` with real credentials rather than minting a
 * session outright — a shortcut that skipped the password would undo the
 * check above.
 */
export async function signInAdmissionsDemo(): Promise<void> {
  const demo = new FormData();
  demo.set("email", DEMO_ACCOUNTS.registrar.email);
  demo.set("password", DEMO_PASSWORD);

  const result = await signInAdmissions(undefined, demo);
  if (result?.error) {
    redirect(`/admissions/login?error=${encodeURIComponent(result.error)}`);
  }
}
