import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { BarRows, ChartFrame } from "@acmis/ui/components/chart-frame"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { money, number } from "@acmis/ui/lib/format"

import { FinanceShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Overview" }

/**
 * The bursary dashboard.
 *
 * Leads with unmatched money, because that is the queue nobody else will
 * work. A deposit with a mistyped student number is real money that has
 * arrived and cannot be applied; every day it sits there is a student who
 * believes they have paid and a registration that will be blocked.
 */
export default async function FinanceOverview() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const period = new Date().toISOString().slice(0, 7)
  const [institution, unmatched, overdue, trial] = await Promise.all([
    client.public.institution().catch(() => null),
    client.finance.unmatchedPayments({ limit: 100 }).catch(() => null),
    client.finance.invoices({ overdue_only: true, limit: 100, with_total: true }).catch(() => null),
    client.finance.trialBalance(period).catch(() => null),
  ])

  const currency = institution?.currency ?? "UGX"
  const unmatchedTotal = (unmatched?.items ?? []).reduce((sum, p) => sum + p.amount_minor, 0)
  const overdueTotal = (overdue?.items ?? []).reduce((sum, i) => sum + i.balance_minor, 0)

  return (
    <FinanceShell user={user} institution={institution} currentPath="/">
      <PageHeader
        icon={<Icons.Landmark />}
        title="Finance"
        description="Every movement is a balanced pair of ledger entries. A student's balance is a sum over those entries — the cached figure is only a cache, and the reconciliation asserts the two agree."
      />

      <StatRow>
        <StatTile
          label="Unmatched money"
          value={money(unmatchedTotal, currency, institution?.locale)}
          emphasis
          icon={<Icons.HelpCircle className="size-4" />}
          footnote={`${number(unmatched?.items.length ?? 0)} deposits that arrived without a usable reference`}
          deltaIsGood={false}
        />
        <StatTile
          label="Overdue"
          value={money(overdueTotal, currency, institution?.locale)}
          icon={<Icons.AlarmClock className="size-4" />}
          footnote={`${number(overdue?.meta.total ?? 0)} invoices past their due date`}
          deltaIsGood={false}
        />
        <StatTile
          label="Ledger"
          value={trial?.balanced ? "Balanced" : "Out of balance"}
          icon={
            trial?.balanced ? (
              <Icons.CheckCircle2 className="size-4" />
            ) : (
              <Icons.AlertTriangle className="size-4" />
            )
          }
          footnote={
            trial
              ? `${number(trial.accounts.length)} accounts this period`
              : "No entries this period"
          }
        />
        <StatTile
          label="Period"
          value={period}
          icon={<Icons.Calendar className="size-4" />}
          footnote="A closed period rejects new postings"
        />
      </StatRow>

      {trial && !trial.balanced ? (
        <p
          role="alert"
          className="border-destructive/40 bg-destructive/10 text-destructive rounded-lg border px-4 py-3 text-sm"
        >
          <strong className="font-semibold">The ledger does not balance</strong> for {period}: the
          entries sum to {money(trial.total_minor, currency, institution?.locale)} rather than zero.
          Posting refuses unbalanced transactions, so this is a defect rather than a rounding
          difference. Do not close the period.
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        {trial && trial.accounts.length > 0 ? (
          <ChartFrame
            title={`Trial balance · ${period}`}
            subtitle="Signed totals by account. Debits positive, credits negative; the whole set sums to zero."
            series={[{ key: "balance", label: "Balance", slot: 1 }]}
            footnote="One signed column rather than two, which is what makes 'does this balance' a single sum rather than a comparison between two nullable figures."
            table={
              <table className="tabular w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                      Account
                    </th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                      Balance
                    </th>
                    <th scope="col" className="py-1.5 text-right font-medium">
                      Entries
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {trial.accounts.map((account) => (
                    <tr key={account.account_code} className="border-b last:border-0">
                      <td className="py-1.5 pr-3 font-mono text-xs">{account.account_code}</td>
                      <td className="py-1.5 pr-3 text-right">
                        {money(account.balance_minor, currency, institution?.locale)}
                      </td>
                      <td className="py-1.5 text-right">{number(account.entries)}</td>
                    </tr>
                  ))}
                  <tr className="border-t-2 font-semibold">
                    <td className="py-1.5 pr-3">Total</td>
                    <td className="py-1.5 pr-3 text-right">
                      {money(trial.total_minor, currency, institution?.locale)}
                    </td>
                    <td className="py-1.5" />
                  </tr>
                </tbody>
              </table>
            }
          >
            <BarRows
              rows={trial.accounts.map((account) => ({
                label: account.account_code.replace(/^\d+-/, ""),
                value: Math.abs(account.balance_minor),
                hint: `${account.account_code}: ${money(account.balance_minor, currency, institution?.locale)}`,
              }))}
              formatValue={(v) => money(v, currency, institution?.locale)}
            />
          </ChartFrame>
        ) : null}

        <div className="bg-card shadow-card rounded-lg p-4">
          <h3 className="text-base font-semibold">Money waiting to be identified</h3>
          <p className="text-muted-foreground mt-1 text-sm">
            Recorded against an unapplied-receipts account until someone decides whose it is. The
            decision is audited with the deciding officer&rsquo;s name, because it is a judgement
            and sometimes a wrong one.
          </p>
          {(unmatched?.items.length ?? 0) === 0 ? (
            <p className="text-success mt-4 text-sm font-medium">
              Nothing outstanding — every payment is attributed.
            </p>
          ) : (
            <>
              <ul className="mt-3 divide-y">
                {(unmatched?.items ?? []).slice(0, 6).map((payment) => (
                  <li key={payment.id} className="flex items-start justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="tabular text-sm font-medium">
                        {money(payment.amount_minor, payment.currency, institution?.locale)}
                      </p>
                      <p className="text-muted-foreground truncate text-xs">
                        {payment.payer_name ?? "unknown payer"}
                        {payment.payer_narrative ? ` · "${payment.payer_narrative}"` : ""}
                      </p>
                    </div>
                    <a
                      href={`/unmatched#${payment.id}`}
                      className="text-module shrink-0 text-xs font-medium underline"
                    >
                      Identify
                    </a>
                  </li>
                ))}
              </ul>
              <a
                href="/unmatched"
                className="text-module mt-3 inline-block text-xs font-medium underline"
              >
                Work the full queue ({number(unmatched?.items.length ?? 0)})
              </a>
            </>
          )}
        </div>
      </div>
    </FinanceShell>
  )
}
