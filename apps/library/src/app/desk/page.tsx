import * as Icons from "lucide-react"
import { acmis, requireUser } from "@acmis/auth/server"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge } from "@acmis/ui/components/status-badge"
import { money } from "@acmis/ui/lib/format"

import { LibraryShell } from "@/components/shell"
import { APP } from "@/lib/config"

import { IssueForm, ReturnForm } from "./forms"

export const metadata = { title: "Issue & return" }

/**
 * The circulation desk.
 *
 * Two forms, both driven by a scanner: a book and a card to issue, a book
 * alone to take back. Everything else about the desk is a consequence of
 * those two acts, and burying them under a page of options is how a queue
 * forms at the counter.
 *
 * The refusals are shown in full rather than as "not allowed", because the
 * assistant has to be able to tell the reader in front of them *why* — "you
 * owe 40,000" is actionable and "computer says no" starts an argument.
 */

export default async function DeskPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, overdue] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.loans({ overdue_only: true, limit: 8 }).catch(() => null),
  ])
  const currency = institution?.currency ?? "UGX"

  return (
    <LibraryShell user={user} institution={institution} currentPath="/desk">
      <PageHeader
        icon={<Icons.ScanLine />}
        title="Issue & return"
        description="Two scans to issue, one to take back. A refusal says what the reader can do about it rather than just refusing."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <IssueForm />
        <ReturnForm />
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Overdue right now</h2>
        <ul className="divide-border divide-y text-sm">
          {(overdue?.items ?? []).map((loan) => {
            const days = Math.max(
              0,
              Math.round((Date.now() - new Date(loan.due_on).getTime()) / 86_400_000),
            )
            return (
              <li key={loan.id} className="flex items-center justify-between gap-4 py-2">
                <span className="font-mono text-xs">{loan.copy_id.slice(0, 8)}</span>
                <span className="flex items-center gap-3">
                  <StatusBadge tone="warning">{days}d late</StatusBadge>
                  <span className="text-muted-foreground tabular-nums">
                    {money(days * loan.fine_per_day_minor, currency)}
                  </span>
                </span>
              </li>
            )
          })}
          {(overdue?.items ?? []).length === 0 ? (
            <li className="text-muted-foreground py-2">Nothing overdue.</li>
          ) : null}
        </ul>
      </section>
    </LibraryShell>
  )
}
