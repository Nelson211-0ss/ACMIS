import * as Icons from "lucide-react"

import type { ObservationRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus } from "@acmis/ui/lib/format"

import { QualityShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Observations" }

/**
 * Teaching observations.
 *
 * Developmental by default and readable by the person observed. One
 * commissioned for a decision *about* them is a different document with a
 * different readership, and the flag says which — blurring that line stops
 * staff volunteering for observation, and a scheme nobody volunteers for
 * observes nothing.
 */
export default async function ObservationsPage({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>
}) {
  const { cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.quality.observations({ mine_only: true, cursor, limit: 50, with_total: true }),
  ])

  const columns: Array<Column<ObservationRow>> = [
    { key: "observed", header: "Observed", render: (row) => date(row.observed_on) },
    {
      key: "purpose",
      header: "Purpose",
      render: (row) => (
        <span className="flex items-center gap-2">
          {humaniseStatus(row.purpose)}
          {row.is_developmental ? (
            <StatusBadge tone="info" dot={false}>
              developmental
            </StatusBadge>
          ) : (
            <StatusBadge tone="warning" dot={false}>
              on record
            </StatusBadge>
          )}
        </span>
      ),
    },
    {
      key: "score",
      header: "Overall",
      numeric: true,
      render: (row) =>
        row.overall_score !== null ? (
          <span className="tabular-nums">{row.overall_score.toFixed(2)}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "actions",
      header: "Agreed actions",
      secondary: true,
      render: (row) => row.agreed_actions ?? "—",
    },
    {
      key: "followup",
      header: "Follow-up",
      secondary: true,
      render: (row) => (row.follow_up_due_on ? date(row.follow_up_due_on) : "—"),
    },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <StatusBadge tone={toneForStatus(row.status)}>
          {humaniseStatus(row.status)}
        </StatusBadge>
      ),
    },
  ]

  return (
    <QualityShell user={user} institution={institution} currentPath="/observations">
      <PageHeader
        title="Observations"
        description="Yours, and the ones you wrote. A developmental observation belongs to the member of staff observed and is not evidence in a decision about them."
      />

      <DataTable
        caption="Teaching observations"
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="flex justify-between gap-3">
              <span className="font-medium">{humaniseStatus(row.purpose)}</span>
              <span className="tabular-nums">
                {row.overall_score?.toFixed(2) ?? "—"}
              </span>
            </div>
            <div className="text-muted-foreground text-xs">
              {date(row.observed_on)} · {humaniseStatus(row.status)}
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.Eye />}
            title="No observations"
            reason="A peer or a quality officer sits in on a class, scores it against the rubric, and shares it with the person observed — who responds before it closes."
          />
        }
      />

      {page.items.some((row) => row.areas_to_develop) ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">What was agreed</h2>
          {page.items
            .filter((row) => row.strengths || row.areas_to_develop)
            .slice(0, 3)
            .map((row) => (
              <article key={row.id} className="bg-card space-y-2 rounded-lg border p-4">
                <header className="text-muted-foreground flex items-baseline justify-between text-xs">
                  <span>{date(row.observed_on)}</span>
                  <span>{humaniseStatus(row.purpose)}</span>
                </header>
                {row.strengths ? (
                  <p className="text-sm">
                    <span className="font-medium">Strengths. </span>
                    {row.strengths}
                  </p>
                ) : null}
                {row.areas_to_develop ? (
                  <p className="text-sm">
                    <span className="font-medium">To develop. </span>
                    {row.areas_to_develop}
                  </p>
                ) : null}
                {row.observee_response ? (
                  <p className="text-muted-foreground border-l-2 pl-3 text-sm italic">
                    {row.observee_response}
                  </p>
                ) : null}
              </article>
            ))}
        </section>
      ) : null}

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/observations?cursor=${encodeURIComponent(page.meta.next_cursor)}`
            : undefined
        }
      />
    </QualityShell>
  )
}
