"use server";

import { redirect } from "next/navigation";
import { startSession } from "@/lib/auth";
import { hashPassword, randomToken, sign } from "@/lib/crypto";
import {
  consumePasswordReset,
  createApplicantAccount,
  createPasswordReset,
  findCredentialByEmail,
  findPasswordReset,
  logAudit,
  setPasswordHash,
} from "@/lib/data/repo";

/** Long enough to matter, short enough that people will actually pick one. */
const MIN_PASSWORD = 10;
const RESET_TTL_MINUTES = 60;

function passwordProblem(password: string, confirm: string): string | null {
  if (password.length < MIN_PASSWORD) {
    return `Use at least ${MIN_PASSWORD} characters. A short phrase you will remember beats a short word you will not.`;
  }
  if (password !== confirm) return "The two passwords do not match.";
  return null;
}

// --- Applicant self-registration ---------------------------------------------

export type RegisterState = { error?: string } | undefined;

export async function register(
  _prev: RegisterState,
  formData: FormData,
): Promise<RegisterState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const confirm = String(formData.get("confirm") ?? "");

  if (!email) return { error: "Enter your email address." };

  const problem = passwordProblem(password, confirm);
  if (problem) return { error: problem };

  const result = await createApplicantAccount(email, await hashPassword(password));
  if ("error" in result) return { error: result.error };

  await logAudit(result.account.email, "Created an applicant account");
  await startSession({ role: "applicant", subjectId: result.account.id });
  redirect("/apply");
}

// --- Forgot password ---------------------------------------------------------

/**
 * The token is HMAC'd before storage, so the row cannot be used to walk into
 * an account — same reason a password is hashed. Only the copy in the link
 * works, and only once.
 */
function tokenHashOf(token: string): string {
  return sign(`reset:${token}`);
}

export type ForgotState = { sent?: boolean; devLink?: string; error?: string } | undefined;

export async function requestPasswordReset(
  _prev: ForgotState,
  formData: FormData,
): Promise<ForgotState> {
  const email = String(formData.get("email") ?? "").trim();
  if (!email) return { error: "Enter your email address." };

  const credential = await findCredentialByEmail(email);

  // Always the same answer, whether or not the address is known. Saying "no
  // such account" would turn this form into a way to test which people hold
  // accounts here.
  if (!credential) return { sent: true };

  const token = randomToken();
  await createPasswordReset({
    tokenHash: tokenHashOf(token),
    subjectKind: credential.kind,
    subjectId: credential.id,
    expiresAt: new Date(Date.now() + RESET_TTL_MINUTES * 60_000).toISOString(),
  });
  await logAudit(credential.email, "Requested a password reset");

  // There is no mail service wired up. In development the link is shown on
  // screen so the flow can actually be walked; in production it is withheld,
  // and connecting an email provider is the remaining piece of work.
  const link = `/reset-password?token=${encodeURIComponent(token)}`;
  return process.env.NODE_ENV === "production"
    ? { sent: true }
    : { sent: true, devLink: link };
}

// --- Reset password ----------------------------------------------------------

export type ResetState = { error?: string } | undefined;

export async function resetPassword(
  _prev: ResetState,
  formData: FormData,
): Promise<ResetState> {
  const token = String(formData.get("token") ?? "");
  const password = String(formData.get("password") ?? "");
  const confirm = String(formData.get("confirm") ?? "");

  if (!token) return { error: "This reset link is missing its token." };

  const problem = passwordProblem(password, confirm);
  if (problem) return { error: problem };

  const hash = tokenHashOf(token);
  const reset = await findPasswordReset(hash);
  if (!reset) {
    return {
      error: "This reset link has expired or has already been used. Request a new one.",
    };
  }

  const written = await setPasswordHash(
    reset.subjectKind,
    reset.subjectId,
    await hashPassword(password),
  );
  if (!written) return { error: "That account no longer exists." };

  await consumePasswordReset(hash);
  await logAudit(reset.subjectId, "Reset their password");

  redirect("/login?reset=1");
}
