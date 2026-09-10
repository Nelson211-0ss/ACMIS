"use server";

import { revalidatePath } from "next/cache";
import { currentStudent } from "@/lib/auth";
import { getCourse, getFeeSummary, getSystemSettings, setRegistration } from "@/lib/data/repo";

export type RegistrationState =
  | { ok: true; message: string; rejected: Array<{ code: string; reason: string }> }
  | { ok: false; message: string }
  | undefined;

/**
 * Save a semester's course registration.
 *
 * Two gates, in this order: a blocking fee balance stops registration
 * outright, then per-course prerequisites are checked in the repository.
 * Courses that fail a prerequisite are reported back rather than dropped
 * silently, so the student knows why their choice did not take.
 */
export async function saveRegistration(
  _prev: RegistrationState,
  formData: FormData,
): Promise<RegistrationState> {
  const student = await currentStudent();
  if (!student) return { ok: false, message: "Your session has expired. Sign in again." };

  const settings = await getSystemSettings();
  if (!settings.registrationOpen) {
    return { ok: false, message: "The registrar has closed course registration for now." };
  }

  const fees = await getFeeSummary(student.id);
  if (fees.blockingBalance > 0) {
    return {
      ok: false,
      message:
        "Registration is blocked while tuition is outstanding. Clear the balance on the Fees page, then try again.",
    };
  }

  const selected = formData.getAll("courses").map(String);
  const { registered, rejected } = await setRegistration(student, selected);

  revalidatePath("/portal/registration");
  revalidatePath("/portal/timetable");
  revalidatePath("/portal");

  const named = await Promise.all(
    rejected.map(async (r) => ({
      code: (await getCourse(r.courseId))?.code ?? r.courseId,
      reason: r.reason,
    })),
  );

  return {
    ok: true,
    message: `${registered.length} course${registered.length === 1 ? "" : "s"} registered for Semester ${student.currentSemester}.`,
    rejected: named,
  };
}
