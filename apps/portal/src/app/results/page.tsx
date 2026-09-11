import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { humaniseStatus, number } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Results" }

/**
 * A student's released results.
 *
 * Only released ones ever appear — an unreleased mark is provisional, may still
 * be moderated up or down, and showing it produces an argument the institution
 * cannot win. The page says so, because "why can't I see my marks" is otherwise
 * the most common query a registry gets.
 */
export default async function ResultsPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, results, record] = await Promise.all([
    client.public.institution().catch(() => null),
    client.assessment.myResults().catch(() => []),
    client.students.myRecord().catch(() => null),
  ])

  const primary = record?.data.programmes.find((p) => p.is_primary)
  const counted = results.filter((r) => !r.is_superseded)

  return (
    <PortalShell user={user} institution={institution} currentPath="/results">
      <PageHeader
        icon={<Icons.Award />}
        title="Results"
        description="Only results that Senate has approved and released appear here. A mark you have been told informally is provisional until it is on this page."
      />

      {primary ? (
        <section className="bg-card shadow-card grid grid-cols-2 gap-4 rounded-lg p-4 sm:grid-cols-4">
          <Figure label="CGPA" value={primary.cgpa !== null ? primary.cgpa.toFixed(2) : "—"} />
          <Figure label="Credits earned" value={number(primary.credits_earned)} />
          <Figure label="Credits required" value={number(primary.credits_required)} />
          <Figure label="Standing" value={humaniseStatus(primary.progression_status)} />
        </section>
      ) : null}

      {primary && primary.outstanding_retakes > 0 ? (
        <p className="border-warning/40 bg-warning/10 text-warning-foreground rounded-lg border px-4 py-3 text-sm">
          You have {primary.outstanding_retakes} outstanding retake
          {primary.outstanding_retakes === 1 ? "" : "s"}. Your award cannot be classified until they
          are cleared.
        </p>
      ) : null}

      {results.length === 0 ? (
        <EmptyState
          title="No released results yet"
          reason="Marks appear once they have passed moderation, a department board, a faculty board and Senate. That is deliberately slow: it is what makes a mark defensible."
          icon={<Icons.Award className="size-8" />}
        />
      ) : (
        <div className="tabular overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <caption className="sr-only">Your released course results</caption>
            <thead>
              <tr className="border-b">
                <th scope="col" className="px-3 py-2 text-left text-xs font-medium uppercase">
                  Course
                </th>
                <th scope="col" className="px-3 py-2 text-right text-xs font-medium uppercase">
                  CU
                </th>
                <th scope="col" className="px-3 py-2 text-right text-xs font-medium uppercase">
                  Mark
                </th>
                <th scope="col" className="px-3 py-2 text-center text-xs font-medium uppercase">
                  Grade
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-medium uppercase">
                  Outcome
                </th>
              </tr>
            </thead>
            <tbody>
              {results.map((result) => (
                <tr
                  key={result.id}
                  className={
                    result.is_superseded
                      ? "text-muted-foreground border-b last:border-0"
                      : "border-b last:border-0"
                  }
                >
                  <td className="px-3 py-2.5">
                    <span className="font-mono text-xs">{result.course_code}</span>
                    <span className="ml-2">{result.course_title}</span>
                    {result.is_retake ? (
                      <span className="text-warning-foreground ml-2 text-xs">
                        retake {result.attempt_number}
                      </span>
                    ) : null}
                    {result.is_superseded ? (
                      <span className="ml-2 text-xs italic">superseded by a later attempt</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 text-right">{result.credit_units}</td>
                  <td className="px-3 py-2.5 text-right font-medium">
                    {result.final_mark?.toFixed(1) ?? "—"}
                  </td>
                  <td className="px-3 py-2.5 text-center font-medium">{result.grade ?? "—"}</td>
                  <td className="px-3 py-2.5">
                    <StatusBadge tone={toneForStatus(result.outcome)} dot={false}>
                      {humaniseStatus(result.outcome)}
                    </StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {results.length > 0 ? (
        <p className="text-muted-foreground text-xs leading-relaxed">
          {number(counted.length)} of {number(results.length)} attempts count toward your CGPA. A
          failed attempt is shown alongside the retake that replaced it — your transcript records
          what happened, not only the best outcome. If you believe a mark is wrong, an appeal must
          be lodged within the window your institution sets, which runs from the release date rather
          than from when you saw it.
        </p>
      ) : null}
    </PortalShell>
  )
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="tabular mt-0.5 text-2xl font-semibold">{value}</p>
    </div>
  )
}
