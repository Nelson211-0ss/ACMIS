import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame, Meter } from "@acmis/ui/components/chart-frame"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { date, humaniseStatus, number } from "@acmis/ui/lib/format"

import { AssessmentShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * The examinations office dashboard.
 *
 * Organised around the approval chain, because that is the actual state of the
 * world in a results season: sheets sitting at each stage, and the ones past
 * their deadline. "How many marks are entered" is far less useful than "how
 * many sheets are stuck at moderation".
 */
export default async function AssessmentOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, semester] = await Promise.all([
    client.public.institution().catch(() => null),
    client.reference.currentSemester().catch(() => null),
  ])

  const sheets = await client.assessment
    .markSheets({ semester_id: semester?.id, limit: 200 })
    .catch(() => null)

  const items = sheets?.items ?? []
  const byStatus = new Map<string, number>()
  for (const sheet of items) {
    byStatus.set(sheet.status, (byStatus.get(sheet.status) ?? 0) + 1)
  }

  const today = new Date()
  const overdue = items.filter(
    (s) =>
      s.due_on !== null &&
      new Date(s.due_on) < today &&
      !["senate_approved", "published"].includes(s.status),
  )
  const published = byStatus.get("published") ?? 0
  const candidates = items.reduce((sum, s) => sum + s.student_count, 0)
  const entered = items.reduce((sum, s) => sum + s.entered_count, 0)

  // The chain, in order. Rendering the pipeline in its real order is the whole
  // point — sorted by count it would tell you the same numbers and none of
  // the story.
  const CHAIN = [
    ["draft", "With examiners"],
    ["submitted", "Submitted"],
    ["moderated", "Moderated"],
    ["board_approved", "Department board"],
    ["faculty_approved", "Faculty board"],
    ["senate_approved", "Senate"],
    ["published", "Released"],
  ] as const

  return (
    <AssessmentShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.ClipboardCheck />}
        title="Assessment"
        description={
          semester
            ? `${semester.name}${
                semester.results_due_on
                  ? ` · results due ${date(semester.results_due_on, institution?.locale)}`
                  : ""
              }. A mark reaches a transcript only after moderation, a department board, a faculty board and Senate.`
            : "No current semester is set."
        }
      />

      <StatRow>
        <StatTile
          label="Mark sheets"
          value={number(items.length)}
          emphasis
          icon={<Icons.ClipboardCheck className="size-4" />}
        />
        <StatTile
          label="Past deadline"
          value={number(overdue.length)}
          icon={<Icons.AlarmClock className="size-4" />}
          deltaIsGood={false}
          footnote="Not yet Senate-approved and past the due date"
        />
        <StatTile
          label="Released"
          value={number(published)}
          icon={<Icons.Send className="size-4" />}
          footnote="Visible to students"
        />
        <StatTile
          label="Candidates"
          value={number(candidates)}
          icon={<Icons.Users className="size-4" />}
          footnote={`${number(entered)} marks entered`}
        />
      </StatRow>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame
          title="Where results are in the chain"
          subtitle="Mark sheets at each approval stage, in the order they pass through."
          series={[{ key: "sheets", label: "Mark sheets", slot: 1 }]}
          footnote="A pile at one stage is where the season is actually stuck. Sheets do not skip stages: a sheet cannot reach Senate without a department board having seen it."
          table={
            <table className="tabular w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                    Stage
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Sheets
                  </th>
                </tr>
              </thead>
              <tbody>
                {CHAIN.map(([status, label]) => (
                  <tr key={status} className="border-b last:border-0">
                    <td className="py-1.5 pr-3">{label}</td>
                    <td className="py-1.5 text-right">{number(byStatus.get(status) ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          {items.length > 0 ? (
            <BarRows
              rows={CHAIN.map(([status, label]) => ({
                label,
                value: byStatus.get(status) ?? 0,
              }))}
              formatValue={(v) => number(v)}
            />
          ) : (
            <p className="text-muted-foreground py-6 text-center text-sm">
              No mark sheets have been generated for this semester.
            </p>
          )}
        </ChartFrame>

        <div className="bg-card shadow-card space-y-4 rounded-lg p-4">
          <div>
            <h3 className="text-base font-semibold">Mark entry</h3>
            <p className="text-muted-foreground mt-1 text-sm">
              A sheet cannot be submitted while any candidate is unmarked — enter a mark or record
              an absence.
            </p>
          </div>
          <Meter
            label="Candidates marked"
            value={entered}
            max={candidates || 1}
            formatValue={(v) => number(v)}
          />
          {overdue.length > 0 ? (
            <div className="border-t pt-3">
              <p className="text-warning-foreground text-sm font-medium">
                {overdue.length} sheet{overdue.length === 1 ? "" : "s"} past the deadline
              </p>
              <ul className="mt-2 space-y-1">
                {overdue.slice(0, 5).map((sheet) => (
                  <li key={sheet.id} className="flex items-baseline justify-between gap-2 text-xs">
                    <a
                      href={`/mark-sheets/${sheet.id}`}
                      className="hover:text-module truncate font-mono"
                    >
                      {sheet.course_offering_id.slice(0, 8)}
                    </a>
                    <span className="text-muted-foreground shrink-0">
                      {humaniseStatus(sheet.status)} · due {date(sheet.due_on, institution?.locale)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </AssessmentShell>
  )
}
