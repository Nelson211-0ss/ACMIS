import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"

import { LearningShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "My teaching" }

/**
 * A lecturer's landing page.
 *
 * Scoped to the offerings they are actually allocated to teach, which is the
 * same thing that grants them mark entry — see `assessment.mark-entry`. A
 * department-wide list is noise to someone with three courses, and the
 * allocation is the authoritative answer to "whose courses are these".
 */
export default async function MyTeachingPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
  ])

  // `mine_only` filters to the caller's teaching allocation server-side.
  const sheets = await client.assessment
    .markSheets({ mine_only: true, limit: 20, semester_id: semester?.id })
    .catch(() => null)

  const outstanding = (sheets?.items ?? []).filter(
    (s) => s.status === "draft" || s.status === "returned",
  )
  const missingMarks = outstanding.reduce((sum, s) => sum + s.missing_count, 0)

  return (
    <LearningShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.GraduationCap />}
        title="My teaching"
        description={
          semester
            ? `${semester.name}. Only the courses you are allocated to teach appear here — the teaching allocation is what grants mark entry, and it lapses with the contract.`
            : "No current semester is set."
        }
      />

      <StatRow>
        <StatTile
          label="Courses allocated"
          value={sheets?.items.length ?? 0}
          emphasis
          icon={<Icons.BookOpen className="size-4" />}
        />
        <StatTile
          label="Mark sheets open"
          value={outstanding.length}
          icon={<Icons.FileEdit className="size-4" />}
          footnote="Draft or returned to you"
        />
        <StatTile
          label="Marks outstanding"
          value={missingMarks}
          icon={<Icons.AlertCircle className="size-4" />}
          footnote="A sheet cannot be submitted with any candidate unmarked"
          deltaIsGood={false}
        />
        <StatTile
          label="With the boards"
          value={
            (sheets?.items ?? []).filter((s) =>
              ["submitted", "moderated", "board_approved", "faculty_approved"].includes(s.status),
            ).length
          }
          icon={<Icons.Users className="size-4" />}
          footnote="Submitted and moving through approval"
        />
      </StatRow>

      {sheets && sheets.items.length > 0 ? (
        <section>
          <h2 className="text-lg font-semibold">Your courses this semester</h2>
          <ul className="mt-3 space-y-2">
            {sheets.items.map((sheet) => (
              <li
                key={sheet.id}
                className="bg-card shadow-card flex flex-wrap items-center justify-between gap-3 rounded-lg p-3"
              >
                <div className="min-w-0">
                  <p className="font-mono text-xs">{sheet.course_offering_id.slice(0, 8)}</p>
                  <p className="text-muted-foreground text-xs">
                    {sheet.entered_count} of {sheet.student_count} marks entered
                    {sheet.missing_count > 0 ? ` · ${sheet.missing_count} outstanding` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href={`/spaces?offering=${sheet.course_offering_id}`}
                    className="hover:bg-muted rounded-md border px-2.5 py-1.5 text-xs font-medium"
                  >
                    Course space
                  </a>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <EmptyState
          title="No courses allocated to you this semester"
          reason="Mark entry and course-space authoring both follow the teaching allocation. If you are teaching a course that is not listed, ask your head of department to record the allocation — it is what grants the authority, so nothing here works without it."
          icon={<Icons.BookOpen className="size-8" />}
        />
      )}
    </LearningShell>
  )
}
