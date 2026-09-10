import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Fees" }

/**
 * A student's own fee account.
 *
 * Answers the three questions a student actually has, in that order: how much
 * do I owe, when is it due, and what happens if I am late. The last one is on
 * the page rather than in a handbook because a student who first learns about
 * a surcharge from their balance has already lost the argument about it.
 */
export default async function FeesPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, record, statement, penalties, plans, reminders, rules] =
    await Promise.all([
      client.public.institution().catch(() => null),
      client.students.myRecord().catch(() => null),
      client.finance.myStatement().catch(() => null),
      client.finance.penalties({ limit: 20 }).catch(() => null),
      client.finance.paymentPlans({ limit: 10 }).catch(() => null),
      client.finance.reminders({ limit: 10 }).catch(() => null),
      client.finance.latePaymentRules().catch(() => []),
    ])

  const currency = institution?.currency ?? "UGX"
  const student = record?.data
  const blocks = student
    ? await client.finance.blocks(student.id).catch(() => null)
    : null

  const activePlan = (plans?.items ?? []).find((row) => row.status === "active")
  const rule = rules.find((row) => row.status === "approved") ?? rules[0]
  const charges = (penalties?.items ?? []).filter((row) => row.status !== "reversed")

  return (
    <PortalShell user={user} institution={institution} currentPath="/fees">
      <PageHeader
        title="Fees"
        description="Recomputed from the ledger every time this page loads rather than read from a cache, because it is the number you are asked to act on."
      />

      <StatRow>
        <StatTile
          label="Outstanding"
          value={money(statement?.balance_minor, currency)}
          footnote="Your own portion, after any sponsor share"
          icon={<Icons.Wallet />}
          emphasis={(statement?.balance_minor ?? 0) > 0}
        />
        <StatTile
          label="Invoiced"
          value={money(statement?.total_invoiced_minor, currency)}
          footnote="Everything raised to date"
          icon={<Icons.FileText />}
        />
        <StatTile
          label="Paid"
          value={money(statement?.total_paid_minor, currency)}
          footnote="Receipts posted and matched"
          icon={<Icons.CircleCheck />}
        />
        <StatTile
          label="Waived"
          value={money(statement?.total_waived_minor, currency)}
          footnote="Bursary, scholarship or hardship"
          icon={<Icons.HeartHandshake />}
        />
      </StatRow>

      {blocks?.blocked ? (
        <section className="border-warning/40 bg-warning/10 rounded-lg border p-4">
          <h2 className="text-warning-foreground flex items-center gap-2 text-sm font-semibold">
            <Icons.TriangleAlert className="size-4" aria-hidden />
            {blocks.blocks.length === 1
              ? "One thing is blocked by arrears"
              : `${blocks.blocks.length} things are blocked by arrears`}
          </h2>
          <ul className="mt-2 space-y-2 text-sm">
            {blocks.blocks.map((block) => (
              <li key={`${block.gate}-${block.invoice}`}>
                <span className="font-medium">{humaniseStatus(block.gate)}</span> —
                invoice <span className="font-mono text-xs">{block.invoice}</span>,{" "}
                {block.days_overdue} days overdue.
                <span className="text-muted-foreground block text-xs">
                  Clears when: {block.clears_when}
                  {block.waivable
                    ? " — a payment plan agreed before the block bites also lifts it."
                    : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {activePlan ? (
        <section className="border-success/30 bg-success/10 rounded-lg border p-4">
          <h2 className="text-success flex items-center gap-2 text-sm font-semibold">
            <Icons.Handshake className="size-4" aria-hidden />
            You have an agreed payment plan
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            While you keep to it you are not treated as late: no surcharge is
            applied and nothing is blocked, whatever the invoice due date says.
            {activePlan.missed_count > 0
              ? ` You have missed ${activePlan.missed_count} instalment${activePlan.missed_count === 1 ? "" : "s"}.`
              : ""}
          </p>
          <ul className="mt-3 space-y-1 text-sm">
            {activePlan.instalments.map((instalment) => (
              <li
                key={instalment.id}
                className="flex flex-wrap items-baseline justify-between gap-x-4"
              >
                <span>
                  Instalment {instalment.sequence}
                  <span className="text-muted-foreground ml-2 text-xs">
                    due {date(instalment.due_on)}
                  </span>
                </span>
                <span className="flex items-center gap-3">
                  <span className="tabular">{money(instalment.amount_minor, currency)}</span>
                  <StatusBadge tone={toneForStatus(instalment.status)} dot={false}>
                    {humaniseStatus(instalment.status)}
                  </StatusBadge>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {statement && statement.invoices.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Invoices</h2>
          <div className="tabular overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">Every invoice raised on your account</caption>
              <thead>
                <tr className="border-b">
                  <th scope="col" className="px-3 py-2 text-left text-xs font-medium uppercase">
                    Invoice
                  </th>
                  <th scope="col" className="px-3 py-2 text-left text-xs font-medium uppercase">
                    Due
                  </th>
                  <th scope="col" className="px-3 py-2 text-right text-xs font-medium uppercase">
                    Total
                  </th>
                  <th scope="col" className="px-3 py-2 text-right text-xs font-medium uppercase">
                    Sponsor
                  </th>
                  <th scope="col" className="px-3 py-2 text-right text-xs font-medium uppercase">
                    Balance
                  </th>
                </tr>
              </thead>
              <tbody>
                {statement.invoices.map((invoice) => (
                  <tr key={invoice.id} className="border-b last:border-0">
                    <td className="px-3 py-2.5">
                      <span className="font-mono text-xs">{invoice.number}</span>
                      <span className="text-muted-foreground ml-2 text-xs">
                        {humaniseStatus(invoice.kind)}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {date(invoice.due_on)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {money(invoice.total_minor, currency)}
                    </td>
                    <td className="text-muted-foreground px-3 py-2.5 text-right">
                      {invoice.sponsor_portion_minor
                        ? money(invoice.sponsor_portion_minor, currency)
                        : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right font-medium">
                      {money(invoice.balance_minor, currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <EmptyState
          icon={<Icons.Wallet className="size-8" />}
          title="Nothing on your account yet"
          reason="A semester invoice appears here once it is raised from the published fee structure for your programme and sponsorship."
        />
      )}

      {statement && statement.payments.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Payments received</h2>
          <ul className="divide-border divide-y text-sm">
            {statement.payments.map((payment) => (
              <li
                key={payment.id}
                className="flex flex-wrap items-baseline justify-between gap-x-4 py-2"
              >
                <span className="min-w-0">
                  <span className="tabular font-medium">
                    {money(payment.amount_minor, currency)}
                  </span>
                  <span className="text-muted-foreground ml-2 text-xs">
                    {humaniseStatus(payment.method)} · ref{" "}
                    <span className="font-mono">{payment.reference}</span>
                    {payment.receipt_number ? ` · receipt ${payment.receipt_number}` : ""}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-3">
                  <span className="text-muted-foreground text-xs">
                    {date(payment.value_date)}
                  </span>
                  <StatusBadge tone={toneForStatus(payment.status)} dot={false}>
                    {humaniseStatus(payment.status)}
                  </StatusBadge>
                </span>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground text-xs leading-relaxed">
            A bank deposit that does not appear here is usually one whose
            reference could not be matched to a student number. Take the slip to
            the bursary rather than paying again.
          </p>
        </section>
      ) : null}

      {charges.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Late payment surcharges</h2>
          <ul className="divide-border divide-y text-sm">
            {charges.map((charge) => (
              <li
                key={charge.id}
                className="flex flex-wrap items-baseline justify-between gap-x-4 py-2"
              >
                <span>
                  <span className="tabular font-medium">
                    {money(charge.amount_minor, currency)}
                  </span>
                  <span className="text-muted-foreground ml-2 text-xs">
                    {charge.days_overdue} day{charge.days_overdue === 1 ? "" : "s"} past
                    due
                    {charge.percent_applied !== null
                      ? ` · ${charge.percent_applied}% of ${money(charge.balance_at_charge_minor, currency)}`
                      : ""}
                  </span>
                </span>
                <span className="text-muted-foreground shrink-0 text-xs">
                  {date(charge.charged_on)}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground text-xs leading-relaxed">
            The arithmetic is shown because you are entitled to check it. If a
            payment had already been made when a charge was applied, ask the
            bursary to reverse it — reversals are recorded, not erased.
          </p>
        </section>
      ) : null}

      {rule ? (
        <section className="bg-muted/40 space-y-2 rounded-lg border p-4">
          <h2 className="text-sm font-semibold">The late-payment terms</h2>
          <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-xs leading-relaxed">
            <li>{rule.grace_days} days&rsquo; grace after the due date.</li>
            <li>
              Then{" "}
              {rule.charge_basis === "percentage"
                ? `${rule.charge_percent}% of the outstanding balance`
                : money(rule.charge_flat_minor, currency)}
              {rule.recurrence !== "once" ? `, ${humaniseStatus(rule.recurrence)}` : ""}
              {rule.charge_cap_minor
                ? `, capped at ${money(rule.charge_cap_minor, currency)}`
                : ""}
              .
            </li>
            {rule.blocks_registration_after_days ? (
              <li>Registration is blocked after {rule.blocks_registration_after_days} days.</li>
            ) : null}
            {rule.blocks_exam_card_after_days ? (
              <li>
                An examination card is refused after {rule.blocks_exam_card_after_days} days.
              </li>
            ) : null}
            {rule.blocks_results_after_days ? (
              <li>Results are withheld after {rule.blocks_results_after_days} days.</li>
            ) : null}
            {rule.is_waivable ? (
              <li>
                Hardship is considered. Ask the dean of students about a payment
                plan <em>before</em> a block applies, not after.
              </li>
            ) : null}
          </ul>
        </section>
      ) : null}

      {(reminders?.items ?? []).length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Reminders we have sent you</h2>
          <ul className="divide-border divide-y text-sm">
            {(reminders?.items ?? []).map((notice) => (
              <li key={notice.id} className="py-2">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                  <span className="font-medium">Level {notice.level} reminder</span>
                  <span className="text-muted-foreground text-xs">
                    {date(notice.sent_on)} · {humaniseStatus(notice.channel)}
                    {notice.sent_to_sponsor ? " · copied to your sponsor" : ""}
                  </span>
                </div>
                {notice.consequence_stated ? (
                  <p className="text-muted-foreground mt-0.5 text-xs">
                    {notice.consequence_stated}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </PortalShell>
  )
}
