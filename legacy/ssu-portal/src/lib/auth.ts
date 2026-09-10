import { cookies } from "next/headers";
import { getApplicantAccount, getStaff, getStudent } from "./data/repo";
import { sign, verifySignature } from "./crypto";
import type { ApplicantAccount, StaffUser, Student } from "./types";

/**
 * Session cookie: `<base64url(role:subjectId:expiry)>.<hmac>`.
 *
 * The signature is the whole point. Before it, the cookie was plain text, so
 * anyone could set `ssu_session=admin:staff-1` in devtools and be a super
 * administrator — no password, no forgery needed. The payload is still
 * readable (it is not encrypted, and does not need to be: a role and an id
 * are not secrets), but it can no longer be altered without the server key.
 *
 * The payload is base64url-encoded rather than written raw because a cookie
 * value goes through percent-encoding on the way out: raw `:` separators come
 * back as `%3A` and the split silently fails to find any fields. base64url
 * has no characters that survive a round trip differently, so what is signed
 * is exactly what is verified.
 *
 * Sessions carry their own expiry rather than trusting the cookie's maxAge,
 * which the client controls.
 *
 * Still missing for a real deployment: server-side session revocation (a
 * stolen cookie stays valid until it expires), rate limiting, and 2FA.
 */

const COOKIE = "ssu_session";
const SESSION_HOURS = 12;

export type Role = "student" | "applicant" | "admin";

export interface Session {
  role: Role;
  /** Student id for students, applicant account id for applicants, staff id for admins. */
  subjectId: string;
}

const ROLES: Role[] = ["student", "applicant", "admin"];

export async function currentSession(): Promise<Session | null> {
  const raw = (await cookies()).get(COOKIE)?.value;
  if (!raw) return null;

  const dot = raw.lastIndexOf(".");
  if (dot < 1) return null;

  const encoded = raw.slice(0, dot);
  const signature = raw.slice(dot + 1);
  // Verify against the encoded form — the exact bytes that were signed.
  if (!verifySignature(encoded, signature)) return null;

  let payload: string;
  try {
    payload = Buffer.from(encoded, "base64url").toString("utf8");
  } catch {
    return null;
  }

  const [role, subjectId, expiresAt] = payload.split(":");
  if (!ROLES.includes(role as Role) || !subjectId || !expiresAt) return null;
  if (Number(expiresAt) < Date.now()) return null;

  return { role: role as Role, subjectId };
}

export async function startSession(session: Session): Promise<void> {
  const expiresAt = Date.now() + SESSION_HOURS * 60 * 60 * 1000;
  const payload = `${session.role}:${session.subjectId}:${expiresAt}`;
  const encoded = Buffer.from(payload, "utf8").toString("base64url");

  (await cookies()).set(COOKIE, `${encoded}.${sign(encoded)}`, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_HOURS * 60 * 60,
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(COOKIE);
}

/** Returns null rather than redirecting, so callers choose the response. */
export async function currentStudent(): Promise<Student | null> {
  const session = await currentSession();
  if (session?.role !== "student") return null;
  const student = await getStudent(session.subjectId);
  // A suspended student keeps their record but loses the portal.
  if (student?.status === "suspended") return null;
  return student;
}

/** Returns null rather than redirecting, so callers choose the response. */
export async function currentStaff(): Promise<StaffUser | null> {
  const session = await currentSession();
  if (session?.role !== "admin") return null;
  const staff = await getStaff(session.subjectId);
  if (staff?.status !== "active") return null;
  return staff;
}

/** Returns null rather than redirecting, so callers choose the response. */
export async function currentApplicant(): Promise<ApplicantAccount | null> {
  const session = await currentSession();
  if (session?.role !== "applicant") return null;
  const account = await getApplicantAccount(session.subjectId);
  if (account?.status !== "active") return null;
  return account;
}
