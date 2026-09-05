"use server";

import { redirect } from "next/navigation";
import { DEMO_ACCOUNTS, endSession, startSession, type Role } from "@/lib/auth";
import { getStaffByEmail, getStudentByEmail } from "@/lib/data/repo";

/**
 * Mock sign-in. No password is checked — see the warning in src/lib/auth.ts.
 *
 * Returned state is a plain object rather than a thrown error so the form can
 * re-render with a message instead of hitting the error boundary.
 */
export type SignInState = { error?: string } | undefined;

export async function signIn(
  _prev: SignInState,
  formData: FormData,
): Promise<SignInState> {
  const email = String(formData.get("email") ?? "").trim();
  if (!email) return { error: "Enter your email address or student number." };

  const staff = await getStaffByEmail(email);
  if (staff) {
    if (staff.status !== "active") {
      return { error: "This staff account has been suspended. Contact a super administrator." };
    }
    await startSession({ role: "admin", subjectId: staff.id });
    redirect("/admin");
  }

  const student = await getStudentByEmail(email);
  if (student) {
    await startSession({ role: "student", subjectId: student.id });
    redirect("/portal");
  }

  // Anyone who is not a seeded student or staff member is treated as an
  // applicant, so the admissions flow can be walked without creating an
  // account first.
  await startSession({ role: "applicant", subjectId: "usr-applicant" });
  redirect("/apply");
}

const DEMO_REDIRECT: Record<Role, string> = {
  student: "/portal",
  applicant: "/apply",
  admin: "/admin",
};

/** One-click entry to a seeded account, offered on the sign-in screen. */
export async function signInAsDemo(formData: FormData): Promise<void> {
  const role = String(formData.get("role") ?? "") as Role;
  const account = DEMO_ACCOUNTS[role] ?? DEMO_ACCOUNTS.applicant;
  await startSession({ role: account.role, subjectId: account.subjectId });
  redirect(DEMO_REDIRECT[account.role]);
}

export async function signOut(): Promise<void> {
  await endSession();
  redirect("/");
}
