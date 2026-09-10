import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame } from "@acmis/ui/components/chart-frame"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { money, number } from "@acmis/ui/lib/format"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * The library dashboard.
 *
 * Leads with overdues and expiring subscriptions, which are the two things
 * here that get worse while nobody looks: an overdue becomes an uncollectable
 * fine, and a subscription that lapses mid-semester is discovered by students.
 */
export default async function LibraryOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, overdue, unpaidFines, expiring, acquisitions, membersInDebt] =
    await Promise.all([
      client.public.institution().catch(() => null),
      client.library.loans({ overdue_only: true, limit: 20, with_total: true }).catch(() => null),
      client.library.fines({ unpaid_only: true, limit: 50, with_total: true }).catch(() => null),
      client.library.eResources({ expiring_days: 90 }).catch(() => []),
      client.library
        .acquisitions({ limit: 50, with_total: true })
        .catch(() => null),
      client.library.members({ with_debt: true, limit: 1, with_total: true }).catch(() => null),
    ])

  const owed = (unpaidFines?.items ?? []).reduce((sum, f) => sum + f.amount_minor, 0)
  const notYetOnTheShelf = (acquisitions?.items ?? []).filter(
    (row) => !["catalogued", "declined", "cancelled"].includes(row.status),
  )
  const currency = institution?.currency ?? "UGX"

  const byReason = new Map<string, number>()
  for (const fine of unpaidFines?.items ?? []) {
    byReason.set(fine.reason, (byReason.get(fine.reason) ?? 0) + fine.amount_minor)
  }

  return (
    <LibraryShell user={user} institution={institution} currentPath="/">
      <PageHeader
        title="Library"
        description="The catalogue is what the institution wants known; who borrowed what is not. Circulation records are readable at the desk and by the reader, and by nobody else — not a head of department, and not a report."
      />

      {expiring.length > 0 ? (
        <section
          role="alert"
          className="border-destructive/40 bg-destructive/10 rounded-lg border p-4"
        >
          <h2 className="text-destructive flex items-center gap-2 text-sm font-semibold">
            <Icons.AlertTriangle className="size-4" aria-hidden />
            {expiring.length} subscription{expiring.length === 1 ? "" : "s"} lapsing within
            three months
          </h2>
          <ul className="mt-2 space-y-1 text-sm">
            {expiring.slice(0, 4).map((row) => (
              <li key={row.id} className="flex justify-between gap-4">
                <span>
                  {row.name} <span className="text-muted-foreground">· {row.provider}</span>
                </span>
                <span className="text-muted-foreground tabular-nums">
                  {new Date(row.expires_on).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-2 text-xs">
            A subscription that expires during term is discovered by students.
          </p>
        </section>
      ) : null}

      <StatRow>
        <StatTile
          label="Overdue"
          value={number(overdue?.meta.total ?? overdue?.items.length ?? 0)}
          footnote="Items past their due date"
          icon={<Icons.Clock />}
          emphasis={(overdue?.items.length ?? 0) > 0}
        />
        <StatTile
          label="Fines outstanding"
          value={money(owed, currency)}
          footnote={`${number(unpaidFines?.meta.total ?? 0)} charges unpaid`}
          icon={<Icons.Receipt />}
        />
        <StatTile
          label="Readers owing"
          value={number(membersInDebt?.meta.total ?? 0)}
          footnote="Blocked from borrowing again"
          icon={<Icons.UserX />}
        />
        <StatTile
          label="Ordered, not shelved"
          value={number(notYetOnTheShelf.length)}
          footnote="Requested titles still to arrive"
          icon={<Icons.PackageSearch />}
        />
      </StatRow>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartFrame
          title="What the fines are for"
          subtitle="Overdues are a nudge; losses are the collection shrinking."
          footnote={
            byReason.size === 0 ? "No unpaid charges." : undefined
          }
        >
          <BarRows
            rows={[...byReason.entries()]
              .sort((a, b) => b[1] - a[1])
              .map(([reason, amount]) => ({
                label: reason.replace(/_/g, " "),
                value: amount,
              }))}
            formatValue={(value) => money(value, currency)}
          />
        </ChartFrame>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Longest overdue</h2>
          <ul className="divide-border divide-y text-sm">
            {(overdue?.items ?? []).slice(0, 6).map((loan) => {
              const days = Math.max(
                0,
                Math.round(
                  (Date.now() - new Date(loan.due_on).getTime()) / 86_400_000,
                ),
              )
              return (
                <li key={loan.id} className="flex items-baseline justify-between gap-4 py-2">
                  <span className="min-w-0">
                    <span className="block truncate">{loan.title ?? "—"}</span>
                    <span className="text-muted-foreground font-mono text-xs">
                      {loan.accession_number ?? ""} {loan.membership_number ?? ""}
                    </span>
                  </span>
                  <span className="text-muted-foreground shrink-0 tabular-nums">
                    {days} day{days === 1 ? "" : "s"} · {money(days * loan.fine_per_day_minor, currency)}
                  </span>
                </li>
              )
            })}
            {(overdue?.items ?? []).length === 0 ? (
              <li className="text-muted-foreground py-2">Nothing overdue.</li>
            ) : null}
          </ul>
          <p className="text-muted-foreground text-xs">
            The accrued figure is capped by the loan policy, so a book out for a year
            does not owe a year of fines.
          </p>
        </section>
      </div>
    </LibraryShell>
  )
}
