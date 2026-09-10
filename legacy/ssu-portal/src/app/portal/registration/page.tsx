import type { Metadata } from "next";
import { redirect } from "next/navigation";
import Link from "next/link";
import { BookOpen } from "lucide-react";
import { Callout } from "@/components/ui/callout";
import { Card, CardHeader } from "@/components/ui/card";
import { currentStudent } from "@/lib/auth";
import { institution } from "@/lib/institution";
import {
  getAvailableCourses,
  getCourseCodes,
  getFeeSummary,
  getPassedCourseIds,
  getRegisteredCourseIds,
  getSystemSettings,
} from "@/lib/data/repo";
import { ssp } from "@/lib/format";
import { saveRegistration } from "./actions";
import { RegistrationForm } from "./form";

export const metadata: Metadata = { title: "Course registration" };

/** Faculty cap on credit hours per semester. */
const MAX_CREDITS = 21;

export default async function RegistrationPage() {
  const student = await currentStudent();
  if (!student) redirect("/login");

  const [available, registered, passed, fees, settings] = await Promise.all([
    getAvailableCourses(student),
    getRegisteredCourseIds(student.id),
    getPassedCourseIds(student.id),
    getFeeSummary(student.id),
    getSystemSettings(),
  ]);

  const passedSet = new Set(passed);
  const registeredSet = new Set(registered);

  const rows = await Promise.all(
    available.map(async (course) => ({
      course,
      registered: registeredSet.has(course.id),
      missingPrerequisites: await getCourseCodes(
        course.prerequisites.filter((id) => !passedSet.has(id)),
      ),
    })),
  );

  const blocked = fees.blockingBalance > 0;
  const closedByRegistrar = !settings.registrationOpen;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Course registration
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          {institution.academicYear} · Year {student.yearOfStudy}, Semester{" "}
          {student.currentSemester}. Compulsory courses are registered for you;
          choose your electives up to {MAX_CREDITS} credit hours.
        </p>
      </div>

      {closedByRegistrar || blocked ? (
        <>
          {closedByRegistrar ? (
            <Callout tone="info" title="Registration is closed">
              The registrar has closed course registration for now. Check back
              once it reopens for {institution.academicYear}.
            </Callout>
          ) : (
            <Callout tone="error" title="Registration is blocked">
              <p>
                {ssp(fees.blockingBalance)} of tuition and examination fees is
                outstanding. Registration reopens as soon as the bursary confirms
                your payment.
              </p>
              <Link
                href="/portal/finance"
                className="mt-2 inline-block font-semibold underline underline-offset-2"
              >
                Go to fees and payments
              </Link>
            </Callout>
          )}

          {/* Read-only view so the student can still see what they will take. */}
          <Card>
            <CardHeader
              icon={BookOpen}
              title="Courses for this semester"
              description="Shown for reference. You cannot change these until the balance is cleared."
            />
            <ul className="divide-y divide-line">
              {rows.map(({ course }) => (
                <li
                  key={course.id}
                  className="flex items-baseline gap-3 px-4 py-3 sm:px-5"
                >
                  <span className="nums w-[68px] shrink-0 text-[13px] font-semibold text-brand-700">
                    {course.code}
                  </span>
                  <span className="min-w-0 flex-1 text-[13.5px] text-ink">
                    {course.title}
                  </span>
                  <span className="nums shrink-0 text-[12.5px] text-muted">
                    {course.creditHours} CH
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </>
      ) : (
        <RegistrationForm
          action={saveRegistration}
          rows={rows}
          maxCredits={MAX_CREDITS}
          semester={student.currentSemester}
        />
      )}
    </div>
  );
}
