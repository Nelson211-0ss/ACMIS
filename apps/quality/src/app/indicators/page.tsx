import * as Icons from "lucide-react"

import type { QualityIndicatorRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge } from "@acmis/ui/components/status-badge"
import { date } from "@acmis/ui/lib/format"

import { QualityShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Indicators" }

/**
 * Measured indicators against their targets.
 *
 * The target is stored beside each value rather than looked up, so a
 * historical breach stays a breach after the target moves. Comparing last
 * year's number against this year's target is how an institution talks itself
 * out of a finding.
 */
export default async function IndicatorsPage({
  searchParams,
}: {
  searchParams: Promise<{ below?: string; code?: string; cursor?: string }>
}) {
  const { below, code, cursor } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.quality.indicators({
      below_target_only: below === "1",
      code,
      cursor,
      limit: 50,
      with_total: true,
    }),
  ])

  const columns: Array<Column<QualityIndicatorRow>> = [
    { key: "name", header: "Indicator", render: (row) => row.name },
    {
      key: "value",
      header: "Value",
      numeric: true,
      render: (row) => <span className="tabular-nums">{row.value.toFixed(2)}</span>,
    },
    {
      key: "target",
      header: "Target",
      numeric: true,
      render: (row) =>
        row.target !== null ? (
          <span className="text-muted-foreground tabular-nums">{row.target.toFixed(2)}</span>
        ) : (
          <span className="text-muted-foreground">none set</span>
        ),
    },
    {
      key: "performance",
      header: "Against target",
      render: (row) =>
        row.performance === "below" ? (
          <StatusBadge tone="danger">below</StatusBadge>
        ) : row.performance === "above" ? (
          <StatusBadge tone="success">above</StatusBadge>
        ) : row.performance === "at" ? (
          <StatusBadge tone="info">at target</StatusBadge>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "working",
      header: "From",
      secondary: true,
      render: (row) =>
        row.numerator !== null && row.denominator !== null ? (
          <span className="text-muted-foreground text-xs tabular-nums">
            {row.numerator} / {row.denominator}
          </span>
        ) : (
          "—"
        ),
    },
    {
      key: "computed",
      header: "Computed",
      secondary: true,
      render: (row) => date(row.computed_at),
    },
  ]

  return (
    <QualityShell user={user} institution={institution} currentPath="/indicators">
      <PageHeader
        icon={<Icons.Gauge />}
        title="Indicators"
        description="Aggregate measures, readable by any member of staff — they carry no personal data and are more useful the more widely they are read."
      />

      <nav className="flex gap-2 text-sm" aria-label="Filter">
        <a
          href="/indicators"
          className={
            below === "1"
              ? "border-input rounded-md border px-3 py-1.5"
              : "bg-primary text-primary-foreground rounded-md px-3 py-1.5"
          }
        >
          Everything
        </a>
        <a
          href="/indicators?below=1"
          className={
            below === "1"
              ? "bg-primary text-primary-foreground rounded-md px-3 py-1.5"
              : "border-input rounded-md border px-3 py-1.5"
          }
        >
          Below target
        </a>
      </nav>

      <DataTable
        caption="Quality indicators"
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="flex justify-between gap-3">
              <span className="font-medium">{row.name}</span>
              <span className="tabular-nums">{row.value.toFixed(2)}</span>
            </div>
            <div className="text-muted-foreground text-xs">
              target {row.target?.toFixed(2) ?? "—"} · {row.performance ?? "unknown"}
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.Gauge />}
            title="No indicators computed"
            reason="An indicator is one measured value for one period and one scope, with the method that produced it recorded beside it."
          />
        }
      />

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/indicators?${new URLSearchParams({
                ...(below === "1" ? { below: "1" } : {}),
                ...(code ? { code } : {}),
                cursor: page.meta.next_cursor,
              })}`
            : undefined
        }
      />

      <p className="text-muted-foreground text-xs">
        An indicator whose derivation nobody recorded is argued about instead of acted on, so each
        row keeps its numerator, its denominator and a method note.
      </p>
    </QualityShell>
  )
}
