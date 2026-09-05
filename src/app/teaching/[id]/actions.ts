"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { currentStaff } from "@/lib/auth";
import {
  CURRENT_YEAR,
  getCourse,
  getCourseRoster,
  getSystemSettings,
  logAudit,
  setCourseResultsPublished,
  upsertResult,
} from "@/lib/data/repo";
import { can } from "@/lib/permissions";

async function requireManageResults() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");
  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_results", settings)) redirect("/login");
  return staff;
}

/** A lecturer only grades their own courses — a super admin can act on any. */
function requireOwnsCourse(
  staff: { id: string; staffRole: string },
  course: { lecturerStaffId?: string },
) {
  if (staff.staffRole === "super_admin") return;
  if (course.lecturerStaffId !== staff.id) redirect("/teaching");
}

/**
 * Save every mark entered on the roster in one submit — a lecturer grades a
 * whole class in one sitting, not one student form at a time.
 */
export async function saveMarks(courseId: string, formData: FormData): Promise<void> {
  const actor = await requireManageResults();

  const course = await getCourse(courseId);
  if (!course) redirect("/teaching");
  requireOwnsCourse(actor, course);

  const roster = await getCourseRoster(courseId);
  let saved = 0;

  for (const { student } of roster) {
    const courseworkRaw = formData.get(`coursework-${student.id}`);
    const examRaw = formData.get(`exam-${student.id}`);
    // A blank pair of boxes means "not marked yet" — skip it rather than
    // writing a zero that would misreport as an actual fail.
    if (courseworkRaw === null || examRaw === null) continue;
    if (String(courseworkRaw).trim() === "" || String(examRaw).trim() === "") continue;

    const coursework = Math.max(0, Math.min(40, Number(courseworkRaw)));
    const exam = Math.max(0, Math.min(60, Number(examRaw)));
    if (!Number.isFinite(coursework) || !Number.isFinite(exam)) continue;

    await upsertResult({
      studentId: student.id,
      courseId,
      academicYear: CURRENT_YEAR,
      semester: course.semester,
      coursework,
      exam,
    });
    saved += 1;
  }

  await logAudit(actor.name, `Entered marks for ${saved} student(s)`, course.code);
  revalidatePath(`/teaching/${courseId}`);
}

export async function publishCourseResults(courseId: string, formData: FormData): Promise<void> {
  const actor = await requireManageResults();

  const course = await getCourse(courseId);
  if (!course) redirect("/teaching");
  requireOwnsCourse(actor, course);

  const published = String(formData.get("published") ?? "true") === "true";

  const count = await setCourseResultsPublished(courseId, CURRENT_YEAR, course.semester, published);
  await logAudit(
    actor.name,
    `${published ? "Published" : "Withdrew"} results for ${count} student(s)`,
    course.code,
  );
  revalidatePath(`/teaching/${courseId}`);
  revalidatePath("/teaching");
  revalidatePath("/portal");
  revalidatePath("/portal/results");
}
