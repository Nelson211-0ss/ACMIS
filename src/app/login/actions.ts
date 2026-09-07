"use server";

import { redirect } from "next/navigation";
import { endSession, startSession } from "@/lib/auth";
import { verifyPassword } from "@/lib/crypto";
import { findCredentialByEmail, getStaff, logAudit } from "@/lib/data/repo";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, type DemoAccountKey } from "@/lib/demo-accounts";
import type { StaffRole } from "@/lib/types";

/** Where a staff member lands after signing in — their own desk if they have
 *  one, otherwise the general admin panel. */
const STAFF_LANDING: Partial<Record<StaffRole, string>> = {
  registrar: "/admissions",
  lecturer: "/teaching",
  head_of_department: "/teaching/approvals",
  bursar: "/admin/finance",
  it_support: "/admin/accounts",
};

export type SignInState = { error?: string } | undefined;

/**
 * Sign-in, with the password actually checked.
 *
 * Two things this deliberately does not do:
 *
 * 1. Say which half was wrong. "No account with that email" tells an attacker
 *    which addresses are worth guessing passwords for, and tells anyone who
 *    can reach the login page whether a given person is enrolled here.
 * 2. Skip the hash when the email is unknown. Returning early would make a
 *    miss measurably faster than a wrong password, which is the same
 *    disclosure by a stopwatch — so an unknown email is checked against a
 *    dummy hash and takes the same ~150ms.
 *
 * Still missing before this faces the internet: rate limiting and lockout.
 */
const DUMMY_HASH =
  "scrypt$65536$8$1$00000000000000000000000000000000$0000000000000000000000000000000000000000000000000000000000000000";

export async function signIn(
  _prev: SignInState,
  formData: FormData,
): Promise<SignInState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!email || !password) {
    return { error: "Enter your email address and password." };
  }

  const credential = await findCredentialByEmail(email);
  const ok = await verifyPassword(password, credential?.passwordHash ?? DUMMY_HASH);

  if (!credential || !ok) {
    return { error: "That email address and password do not match an account." };
  }
  if (!credential.passwordHash) {
    return {
      error:
        "This account has no password yet. Use “Forgot password” to set one.",
    };
  }
  if (!credential.active) {
    return {
      error: "This account is suspended. Contact the IT helpdesk to restore it.",
    };
  }

  if (credential.kind === "staff") {
    const staff = await getStaff(credential.id);
    await startSession({ role: "admin", subjectId: credential.id });
    await logAudit(staff?.name ?? credential.email, "Signed in");
    redirect(staff ? (STAFF_LANDING[staff.staffRole] ?? "/admin") : "/admin");
  }

  if (credential.kind === "student") {
    await startSession({ role: "student", subjectId: credential.id });
    redirect("/portal");
  }

  await startSession({ role: "applicant", subjectId: credential.id });
  redirect("/apply");
}

export async function signInAsDemo(formData: FormData): Promise<void> {
  const requested = String(formData.get("role") ?? "") as DemoAccountKey;
  const key: DemoAccountKey = requested in DEMO_ACCOUNTS ? requested : "applicant";

  const demo = new FormData();
  demo.set("email", DEMO_ACCOUNTS[key].email);
  demo.set("password", DEMO_PASSWORD);

  // Goes through the same password check as a typed sign-in; `signIn`
  // redirects on success, so anything returned here is a real failure.
  const result = await signIn(undefined, demo);
  if (result?.error) redirect(`/login?error=${encodeURIComponent(result.error)}`);
}

export async function signOut(): Promise<void> {
  await endSession();
  redirect("/");
}
