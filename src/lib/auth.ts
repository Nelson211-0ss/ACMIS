import { cookies } from "next/headers";
import { getStaff, getStudent } from "./data/repo";
import type { StaffUser, Student } from "./types";

/**
 * Mock session.
 *
 * A signed cookie holding a role and a subject id. There is no password check
 * and no signature — this is a development stand-in so the portal is walkable
 * end to end. Replace with Auth.js before this touches a real student record;
 * the call sites (`currentSession`, `requireStudent`, `requireApplicant`) are
 * the only surface that has to keep working. See README "Replacing mock auth".
 */

const COOKIE = "ssu_session";

export type Role = "student" | "applicant" | "admin";

export interface Session {
  role: Role;
  /** Student id for students, applicant account id for applicants, staff id for admins. */
  subjectId: string;
}

/** The seeded accounts offered on the login screen. */
export const DEMO_ACCOUNTS = {
  student: { role: "student" as const, subjectId: "stu-1", label: "Achol Majok — continuing student" },
  applicant: { role: "applicant" as const, subjectId: "usr-applicant", label: "Emmanuel Wani — applicant" },
  admin: { role: "admin" as const, subjectId: "staff-1", label: "Grace Lueth — super administrator" },
} as const;

const ROLES: Role[] = ["student", "applicant", "admin"];

export async function currentSession(): Promise<Session | null> {
  const raw = (await cookies()).get(COOKIE)?.value;
  if (!raw) return null;
  const [role, subjectId] = raw.split(":");
  if (!ROLES.includes(role as Role) || !subjectId) return null;
  return { role: role as Role, subjectId };
}

export async function startSession(session: Session): Promise<void> {
  (await cookies()).set(COOKIE, `${session.role}:${session.subjectId}`, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(COOKIE);
}

/** Returns null rather than redirecting, so callers choose the response. */
export async function currentStudent(): Promise<Student | null> {
  const session = await currentSession();
  if (session?.role !== "student") return null;
  return getStudent(session.subjectId);
}

/** Returns null rather than redirecting, so callers choose the response. */
export async function currentStaff(): Promise<StaffUser | null> {
  const session = await currentSession();
  if (session?.role !== "admin") return null;
  const staff = await getStaff(session.subjectId);
  if (staff?.status !== "active") return null;
  return staff;
}
