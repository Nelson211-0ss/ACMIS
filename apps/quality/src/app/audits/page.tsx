import * as Icons from "lucide-react"

import type { QualityAuditRow } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { DataTable, Pagination, type Column } from "@acmis/ui/components/data-table"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus } from "@acmis/ui/lib/format"

import { QualityShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Audits" }

/**
 * Quality audits and their findings.
 *
 * Every major and minor finding carries an owner and a date — the API refuses
 * an audit whose findings have neither, because a finding with no owner is a
 * sentence in a report and nothing else. This page leads with the ones past
 * their date.
 */
export default async function AuditsPage({
  searchParams,
}: {
  searchParams: Promise<{ open?: string; cursor?: string }>
}) {
  const { open, cursor } = await searchParams
  const openOnly = open !== "0"
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.quality.audits({
      open_findings_only: openOnly,
      cursor,
      limit: 50,
      with_total: true,
    }),
  ])

  const today = new Date().toISOString().slice(0, 10)
  const overdue = page.items.flatMap((audit) =>
    (audit.findings as Array<Record<string, unknown>>)
      .filter(
        (finding) =>
          (finding.status ?? "open") === "open" &&
          typeof finding.due_on === "string" &&
          finding.due_on < today,
      )
      .map((finding) => ({ audit, finding })),
  )

  const columns: Array<Column<QualityAuditRow>> = [
    {
      key: "reference",
      header: "Reference",
      render: (row) => <span className="font-mono text-xs">{row.reference}</span>,
    },
    { key: "title", header: "Scope", render: (row) => row.title },
    {
      key: "kind",
      header: "Kind",
      secondary: true,
      render: (row) => humaniseStatus(row.kind),
    },
    {
      key: "conducted",
      header: "Conducted",
      secondary: true,
      render: (row) => (row.conducted_on ? date(row.conducted_on) : "—"),
    },
    {
      key: "findings",
      header: "Findings",
      numeric: true,
      render: (row) => (
        <span className="flex items-center justify-end gap-1.5">
          {row.major_findings > 0 ? (
            <StatusBadge tone="danger" dot={false}>
              {row.major_findings} major
            </StatusBadge>
          ) : null}
          {row.minor_findings > 0 ? (
            <StatusBadge tone="warning" dot={false}>
              {row.minor_findings} minor
            </StatusBadge>
          ) : null}
          {row.major_findings + row.minor_findings === 0 ? (
            <span className="text-muted-foreground">none</span>
          ) : null}
        </span>
      ),
    },
    {
      key: "open",
      header: "Open",
      numeric: true,
      render: (row) =>
        row.open_findings > 0 ? (
          <span className="font-medium tabular-nums">{row.open_findings}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "outcome",
      header: "Outcome",
      render: (row) =>
        row.overall_outcome ? (
          <StatusBadge tone={toneForStatus(row.status)}>{row.overall_outcome}</StatusBadge>
        ) : (
          <StatusBadge tone={toneForStatus(row.status)}>
            {humaniseStatus(row.status)}
          </StatusBadge>
        ),
    },
  ]

  return (
    <QualityShell user={user} institution={institution} currentPath="/audits">
      <PageHeader
        title="Audits"
        description="Internal, external and regulator reviews. The audited unit reads its own report and closes its own findings — an audit the unit cannot see is a report about them rather than a review with them."
      />

      {overdue.length > 0 ? (
        <section
          role="alert"
          className="border-destructive/40 bg-destructive/10 rounded-lg border p-4"
        >
          <h2 className="text-destructive flex items-center gap-2 text-sm font-semibold">
            <Icons.AlarmClock className="size-4" aria-hidden />
            {overdue.length} finding{overdue.length === 1 ? "" : "s"} past the date they
            were due to close
          </h2>
          <ul className="mt-2 space-y-1 text-sm">
            {overdue.slice(0, 4).map(({ audit, finding }, index) => (
              <li key={`${audit.id}-${index}`}>
                <span className="text-muted-foreground font-mono text-xs">
                  {audit.reference}/{String(finding.code ?? "")}
                </span>{" "}
                {String(finding.finding ?? "")}
                <span className="text-muted-foreground text-xs">
                  {" "}
                  — due {String(finding.due_on ?? "")}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <nav className="flex gap-2 text-sm" aria-label="Filter">
        <a
          href="/audits"
          className={
            openOnly
              ? "bg-primary text-primary-foreground rounded-md px-3 py-1.5"
              : "border-input rounded-md border px-3 py-1.5"
          }
        >
          With open findings
        </a>
        <a
          href="/audits?open=0"
          className={
            openOnly
              ? "border-input rounded-md border px-3 py-1.5"
              : "bg-primary text-primary-foreground rounded-md px-3 py-1.5"
          }
        >
          All
        </a>
      </nav>

      <DataTable
        caption="Quality audits"
        columns={columns}
        rows={page.items}
        rowKey={(row) => row.id}
        mobileCard={(row) => (
          <div className="space-y-1">
            <div className="font-medium">{row.title}</div>
            <div className="text-muted-foreground text-xs">
              {row.reference} · {row.open_findings} open of{" "}
              {row.major_findings + row.minor_findings}
            </div>
          </div>
        )}
        empty={
          <EmptyState
            icon={<Icons.ClipboardList />}
            title="No audits recorded"
            reason="An audit is of a unit or a programme, against a named standard, over a stated period."
          />
        }
      />

      <Pagination
        meta={page.meta}
        onNext={
          page.meta.next_cursor
            ? `/audits?${new URLSearchParams({
                ...(openOnly ? {} : { open: "0" }),
                cursor: page.meta.next_cursor,
              })}`
            : undefined
        }
      />
    </QualityShell>
  )
}
