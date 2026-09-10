import * as Icons from "lucide-react"
import Link from "next/link"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { dateTime, humaniseStatus, number, percent } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Elections" }

/** Where in the process each state sits, in the voter's words. */
const STAGE: Record<string, string> = {
  draft: "Being set up. Nothing to do yet.",
  nominations: "Nominations are open.",
  vetting: "Nominations closed; candidates are being vetted.",
  campaign: "Campaigning. Voting has not opened.",
  voting: "Voting is open.",
  counting: "Voting closed; the count is under way.",
  declared: "Result declared.",
  annulled: "Annulled.",
}

/**
 * Guild elections.
 *
 * Turnout is shown while a poll is open; a running tally never is. A live
 * count changes how people vote and, in a close race, whether they bother —
 * so the API does not serve one and this page could not show it if it wanted.
 */
export default async function ElectionsPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, page] = await Promise.all([
    client.public.institution().catch(() => null),
    client.elections.list({ limit: 25 }).catch(() => null),
  ])

  const elections = page?.items ?? []
  const open = elections.filter((election) => election.status === "voting")
  const others = elections.filter((election) => election.status !== "voting")

  return (
    <PortalShell user={user} institution={institution} currentPath="/elections">
      <PageHeader
        title="Elections"
        description="Guild and faculty elections. Your ballot is secret: it is stored with no link to your name, and the receipt you are given proves your vote was counted without revealing what it said."
      />

      {elections.length === 0 ? (
        <EmptyState
          icon={<Icons.Vote className="size-8" />}
          title="No elections have been published"
          reason="Elections appear here once the returning officer publishes the notice. Until then the timetable is not fixed and there is nothing to plan against."
        />
      ) : (
        <>
          {open.length > 0 ? (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold">Open for voting</h2>
              <ul className="space-y-3">
                {open.map((election) => (
                  <li
                    key={election.id}
                    className="border-module/40 bg-module/5 rounded-lg border p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="font-semibold">{election.title}</h3>
                        <p className="text-muted-foreground mt-0.5 text-xs">
                          <span className="font-mono">{election.reference}</span> ·{" "}
                          {number(election.positions.length)} position
                          {election.positions.length === 1 ? "" : "s"} · closes{" "}
                          {dateTime(election.voting_closes_at)}
                        </p>
                      </div>
                      <StatusBadge tone="success">Voting open</StatusBadge>
                    </div>
                    <p className="text-muted-foreground mt-2 text-sm">
                      {number(election.eligible_count)} on the roll ·{" "}
                      {number(election.ballots_cast)} have voted
                      {election.turnout_percent !== null
                        ? ` (${percent(election.turnout_percent, "en-UG", 0)} turnout)`
                        : ""}
                      {election.quorum_percent
                        ? ` · ${election.quorum_percent}% needed for a valid result`
                        : ""}
                    </p>
                    <Link
                      href={`/elections/${election.id}`}
                      className="bg-primary text-primary-foreground hover:bg-primary/90 mt-3 inline-block min-h-11 rounded-md px-4 py-2.5 text-sm font-medium"
                    >
                      Go to the ballot
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {others.length > 0 ? (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold">
                {open.length > 0 ? "Other elections" : "Elections"}
              </h2>
              <ul className="divide-border divide-y rounded-lg border">
                {others.map((election) => (
                  <li key={election.id} className="p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <Link
                          href={`/elections/${election.id}`}
                          className="font-medium hover:underline"
                        >
                          {election.title}
                        </Link>
                        <p className="text-muted-foreground mt-0.5 text-xs">
                          <span className="font-mono">{election.reference}</span> ·{" "}
                          {humaniseStatus(election.kind)} ·{" "}
                          {STAGE[election.status] ?? humaniseStatus(election.status)}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <StatusBadge tone={toneForStatus(election.status)} dot={false}>
                          {humaniseStatus(election.status)}
                        </StatusBadge>
                        {election.status === "declared" &&
                        election.turnout_percent !== null ? (
                          <p className="text-muted-foreground mt-1 text-xs">
                            {percent(election.turnout_percent, "en-UG", 0)} turnout
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      )}

      <section className="bg-muted/40 space-y-2 rounded-lg border p-4">
        <h2 className="text-sm font-semibold">How the secret ballot works here</h2>
        <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-xs leading-relaxed">
          <li>
            Two records are written when you vote, and there is no key joining
            them: one says <em>you voted</em>, the other says{" "}
            <em>what was chosen</em>. The time on the ballot is rounded to the
            minute so it cannot be matched back to you by ordering.
          </li>
          <li>
            You get a receipt token for each position. Keep it: it is the only
            thing that can confirm your ballot is in the count, and the
            university does not hold a copy against your name.
          </li>
          <li>
            No one — not the returning officer, not a system administrator — can
            read an individual ballot. There is no endpoint that returns one,
            and the policy bundle denies the attempt to everybody.
          </li>
          <li>
            An empty choice is a deliberate abstention. It counts toward
            turnout, which is what makes a quorum meaningful.
          </li>
        </ul>
      </section>
    </PortalShell>
  )
}
