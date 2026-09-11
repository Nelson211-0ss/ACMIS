import * as Icons from "lucide-react"

import type { CourseEvaluationRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, number } from "@acmis/ui/lib/format"

import { QualityShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Course evaluations" }

/**
 * Evaluation runs.
 *
 * `is_reportable` is the column that matters: below the threshold nothing is
 * shown to anybody, because a breakdown of four responses names the
 * dissenter. The row says so explicitly rather than showing an empty result,
 * so nobody reads "too few to report" as "nobody answered".
 */
export default async function EvaluationsPage({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>
}) {
  const { cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, threshold, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.quality.reportingThreshold().catch(() => ({
      minimum_responses: 5,
      reason: "",
    })),
    client.quality.evaluations({ cursor, limit: 50, with_total: true }),
  ])
  const rows = page.items

  const columns: Array<Column<CourseEvaluationRow>> = [
    {
      key: "offering",
      header: "Offering",
      render: (row) => (
        <a className="font-mono text-xs underline" href={`/evaluations/${row.id}`}>
          {row.course_offering_id.slice(0, 8)}
        </a>
      ),
    },
    {
      key: "closes",
      header: "Closed",
      secondary: true,
      render: (row) => date(row.closes_at),
    },
    {
      key: "responses",
      header: "Responses",
      numeric: true,
      render: (row) => `${number(row.response_count)} / ${number(row.invited_count)}`,
    },
    {
      key: "rate",
      header: "Rate",
      numeric: true,
      secondary: true,
      render: (row) =>
        row.invited_count > 0
          ? `${((row.response_count / row.invited_count) * 100).toFixed(0)}%`
          : "—",
    },
    {
      key: "reportable",
      header: "Reportable",
      render: (row) =>
        row.is_reportable ? (
          <StatusBadge tone="success">yes</StatusBadge>
        ) : (
          <StatusBadge tone="neutral" dot={false}>
            below {threshold.minimum_responses}
          </StatusBadge>
        ),
    },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <StatusBadge tone={toneForStatus(row.status)}>{humaniseStatus(row.status)}</StatusBadge>
      ),
    },
  ]

  return (
    <QualityShell user={user} institution={institution} currentPath="/evaluations">
      <PageHeader
        icon={<Icons.MessagesSquare />}
        title="Course evaluations"
        description="Anonymous within a window, sealed until after the marking deadline. Nothing links a response to the student who wrote it — not even a hashed identifier, because a hash over a class of thirty is reversible by anyone who can list it."
      />

      <section className="bg-muted/40 space-y-2 rounded-lg border p-4 text-sm">
        <h2 className="flex items-center gap-2 font-semibold">
          <Icons.ShieldCheck className="size-4" aria-hidden />
          Why some evaluations show nothing
        </h2>
        <p className="text-muted-foreground text-xs">
          {threshold.reason ||
            `Fewer than ${threshold.minimum_responses} responses cannot be broken down without identifying the respondents.`}
        </p>
        <p className="text-muted-foreground text-xs">
          The invitation list records <em>that</em> a student answered and never what they said. The
          two live in different tables with no key between them, and the response table is
          append-only in the database — so nobody can add a column later to work backwards.
        </p>
      </section>

      <DataTable
        caption="Evaluation runs"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        empty={
          <EmptyState
            icon={<Icons.MessagesSquare />}
            title="No evaluations yet"
            reason="An evaluation runs a published questionnaire over one course offering, within a window that opens after teaching ends and closes before results are released."
          />
        }
      />

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/evaluations?cursor=${encodeURIComponent(page.meta.next_cursor)}`
            : undefined
        }
      />
    </QualityShell>
  )
}
