import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { number } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "My courses" }

/**
 * The courses a student is registered for this semester, with their notes.
 *
 * Built from the registration rather than from anything the student picks,
 * because registration is the thing that actually grants access to material —
 * `learning.student-access` refuses a read for a course they are not
 * registered for, and showing a course here that the API would refuse is a
 * dead end.
 */
export default async function CoursesPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester, record] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
    client.students.myRecord().catch(() => null),
  ])

  const student = record?.data
  const primary = student?.programmes.find((p) => p.is_primary)

  // Registration for the current semester is what lists the courses. Opened
  // read-only here: `openRegistration` is idempotent and returns the existing
  // row, so this does not create anything for a student who has not started.
  const registration =
    student && semester
      ? await client.students.openRegistration(student.id, semester.id).catch(() => null)
      : null

  const courses = registration?.courses ?? []

  return (
    <PortalShell user={user} institution={institution} currentPath="/courses">
      <PageHeader
        icon={<Icons.BookOpen />}
        title="My courses"
        description={
          semester
            ? `${semester.name} · ${number(courses.length)} course${courses.length === 1 ? "" : "s"} registered, ${number(registration?.total_credits ?? 0)} credit units`
            : "No current semester."
        }
      />

      {courses.length === 0 ? (
        <EmptyState
          title="You are not registered for any courses this semester"
          reason={
            registration
              ? "Your registration is open but has no courses on it yet. Add them from the registration page — course notes and tests become available once you are registered."
              : "Enrol for the semester first, then register your courses. Notes and online tests both follow registration."
          }
          action={
            <a
              href="/registration"
              className="bg-primary text-primary-foreground hover:bg-primary/90 inline-block min-h-11 rounded-md px-4 py-2.5 text-sm font-medium"
            >
              Go to registration
            </a>
          }
          icon={<Icons.BookOpen className="size-8" />}
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {courses.map((course) => (
            <li key={course.id}>
              <a
                href={`/courses/${course.course_offering_id}`}
                className="bg-card shadow-card block h-full rounded-lg p-4 transition-colors"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-mono text-xs">{course.course_offering_id.slice(0, 8)}</span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {number(course.credit_units)} CU
                  </span>
                </div>
                <p className="mt-2 text-sm font-medium capitalize">
                  {course.category.replace(/_/g, " ")}
                </p>
                {course.is_retake ? (
                  <p className="text-warning-foreground mt-1 text-xs">
                    Retake · attempt {course.attempt_number}
                  </p>
                ) : null}
                <p className="text-module mt-3 text-xs font-medium">
                  Notes, recordings and tests →
                </p>
              </a>
            </li>
          ))}
        </ul>
      )}

      {primary ? (
        <p className="text-muted-foreground text-xs leading-relaxed">
          Your course list comes from your curriculum version, not from a general catalogue — which
          is why a course another student can take may not appear for you. Registration is also what
          makes notes and tests available: material is refused for a course you are not registered
          for.
        </p>
      ) : null}
    </PortalShell>
  )
}
