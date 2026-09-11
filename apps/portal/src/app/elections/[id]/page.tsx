import * as Icons from "lucide-react"
import Link from "next/link"
import { notFound } from "next/navigation"

import { ApiError } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { dateTime, humaniseStatus, number, percent } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

import { BallotPaper, ReceiptChecker } from "./ballot"

/**
 * One election: the candidates, the ballot, and the result once declared.
 *
 * The order matters. A voter arriving while the poll is open should meet the
 * ballot, not a wall of turnout statistics; a voter arriving after it closed
 * should meet the result. Everything else is below whichever of those applies.
 */
export default async function ElectionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const institution = await client.public.institution().catch(() => null)

  let election
  try {
    election = await client.elections.get(id)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    throw error
  }

  const [candidates, entitlement, turnout, results, petitions] = await Promise.all([
    client.elections.candidates(id, { approved_only: true }).catch(() => []),
    client.elections.myEntitlement(id).catch(() => null),
    election.status === "voting" || election.status === "declared"
      ? client.elections.turnout(id).catch(() => null)
      : Promise.resolve(null),
    election.status === "declared" ? client.elections.results(id).catch(() => []) : [],
    client.elections.petitions(id).catch(() => []),
  ])

  const positions = [...election.positions].sort((a, b) => a.sequence - b.sequence)
  const canVote =
    election.status === "voting" &&
    entitlement?.eligible === true &&
    entitlement.has_voted === false

  return (
    <PortalShell user={user} institution={institution} currentPath="/elections">
      <PageHeader
        icon={<Icons.Vote />}
        title={election.title}
        breadcrumbs={
          <Link href="/elections" className="text-muted-foreground text-xs hover:underline">
            ← All elections
          </Link>
        }
        description={election.description ?? undefined}
        actions={
          <StatusBadge tone={toneForStatus(election.status)}>
            {humaniseStatus(election.status)}
          </StatusBadge>
        }
      />

      <dl className="bg-card shadow-card grid grid-cols-2 gap-4 rounded-lg p-4 sm:grid-cols-4">
        <Fact label="Reference" value={election.reference} mono />
        <Fact label="Kind" value={humaniseStatus(election.kind)} />
        <Fact label="Voting opens" value={dateTime(election.voting_opens_at)} />
        <Fact label="Voting closes" value={dateTime(election.voting_closes_at)} />
      </dl>

      {election.status === "voting" ? (
        entitlement?.has_voted ? (
          <section className="border-success/40 bg-success/10 rounded-lg border p-4">
            <h2 className="text-success flex items-center gap-2 text-sm font-semibold">
              <Icons.CircleCheck className="size-4" aria-hidden />
              You have already voted
            </h2>
            <p className="text-muted-foreground mt-1 text-sm">
              Recorded {dateTime(entitlement.voted_at)}. A ballot cannot be changed or withdrawn —
              that is what makes it worth anything. If you kept your receipt you can confirm it is
              in the count below.
            </p>
          </section>
        ) : entitlement?.eligible === false ? (
          <section className="border-warning/40 bg-warning/10 rounded-lg border p-4">
            <h2 className="text-warning-foreground text-sm font-semibold">
              You cannot vote in this election
            </h2>
            <p className="text-muted-foreground mt-1 text-sm">
              {entitlement.reason ?? "You are not on the roll for this election."} The reason is
              stated so you know what to appeal. Appeals go to the returning officer, and the roll
              closes before the poll opens — an appeal lodged during voting is usually too late.
            </p>
          </section>
        ) : null
      ) : null}

      {canVote ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Your ballot</h2>
          <BallotPaper electionId={election.id} positions={positions} candidates={candidates} />
        </section>
      ) : null}

      {election.status === "declared" && results.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Declared result</h2>
          {results
            .slice()
            .sort((a, b) => {
              const first = positions.findIndex((p) => p.id === a.position_id)
              const second = positions.findIndex((p) => p.id === b.position_id)
              return first - second
            })
            .map((result) => {
              const position = positions.find((p) => p.id === result.position_id)
              return (
                <div key={result.id} className="bg-card shadow-card rounded-lg p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                    <h3 className="text-sm font-semibold">{position?.title ?? "Position"}</h3>
                    <p className="text-muted-foreground text-xs">
                      {number(result.ballots_cast)} of {number(result.eligible_count)} voted
                      {result.turnout_percent !== null
                        ? ` · ${percent(result.turnout_percent, "en-UG", 1)} turnout`
                        : ""}
                      {result.quorum_met === false ? " · quorum not met" : ""}
                    </p>
                  </div>
                  <ul className="mt-3 space-y-2">
                    {result.tally.map((row) => (
                      <li key={row.candidate_id}>
                        <div className="flex items-baseline justify-between gap-4 text-sm">
                          <span className={row.elected ? "font-semibold" : ""}>
                            {row.ballot_name}
                            {row.elected ? (
                              <span className="text-success ml-2 text-xs font-medium">elected</span>
                            ) : null}
                          </span>
                          <span className="tabular shrink-0">
                            {number(row.votes)}
                            {row.share_percent !== null
                              ? ` · ${percent(row.share_percent, "en-UG", 1)}`
                              : ""}
                          </span>
                        </div>
                        <div className="bg-muted mt-1 h-1.5 overflow-hidden rounded-full">
                          <div
                            className={
                              row.elected
                                ? "bg-success h-full rounded-full"
                                : "bg-muted-foreground/40 h-full rounded-full"
                            }
                            style={{ width: `${Math.min(100, row.share_percent ?? 0)}%` }}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                  <p className="text-muted-foreground mt-3 text-xs">
                    {number(result.abstentions)} abstentions · {number(result.spoilt)} spoilt ·
                    declared {dateTime(result.declared_at)}
                  </p>
                  {result.tie_break_note ? (
                    <p className="text-warning-foreground mt-2 text-xs">
                      Tie broken: {result.tie_break_note}
                    </p>
                  ) : null}
                </div>
              )
            })}
        </section>
      ) : null}

      {!canVote && election.status !== "declared" ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Candidates</h2>
          {candidates.length === 0 ? (
            <EmptyState
              icon={<Icons.Users className="size-8" />}
              title="No candidates yet"
              reason="Candidates appear once nominations close and the returning officer has vetted them. A nomination that fails vetting is refused with a recorded reason, not quietly dropped."
            />
          ) : (
            <ul className="space-y-3">
              {positions.map((position) => {
                const standing = candidates
                  .filter((candidate) => candidate.position_id === position.id)
                  .sort((a, b) => a.ballot_order - b.ballot_order)
                if (standing.length === 0) return null
                return (
                  <li key={position.id} className="bg-card shadow-card rounded-lg p-4">
                    <h3 className="text-sm font-semibold">{position.title}</h3>
                    <p className="text-muted-foreground text-xs">
                      {number(position.seats)} seat
                      {position.seats === 1 ? "" : "s"} · {number(standing.length)} standing
                    </p>
                    <ul className="mt-3 space-y-2 text-sm">
                      {standing.map((candidate) => (
                        <li key={candidate.id}>
                          <p className="font-medium">
                            {candidate.ballot_order}. {candidate.ballot_name}
                          </p>
                          {candidate.slogan ? (
                            <p className="text-muted-foreground text-xs italic">
                              “{candidate.slogan}”
                            </p>
                          ) : null}
                          {candidate.manifesto ? (
                            <p className="text-muted-foreground mt-0.5 text-xs">
                              {candidate.manifesto}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                    <p className="text-muted-foreground mt-3 text-xs">
                      Ballot order was drawn by lot from a recorded seed, not set alphabetically —
                      being first on the paper is worth votes.
                    </p>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      ) : null}

      {turnout ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Turnout</h2>
          <div className="bg-card shadow-card rounded-lg p-4">
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Fact label="On the roll" value={number(turnout.eligible)} />
              <Fact label="Ballots cast" value={number(turnout.cast)} />
              <Fact
                label="Turnout"
                value={
                  turnout.turnout_percent !== null
                    ? percent(turnout.turnout_percent, "en-UG", 1)
                    : "—"
                }
              />
              <Fact
                label="Quorum"
                value={
                  turnout.quorum_percent
                    ? turnout.quorum_met
                      ? `Met (${turnout.quorum_percent}%)`
                      : `Not met (${turnout.quorum_percent}% needed)`
                    : "None set"
                }
              />
            </dl>
            {turnout.by_hour.length > 0 ? (
              <div className="mt-4">
                <p className="text-muted-foreground text-xs">Ballots cast, by hour</p>
                <ul className="mt-2 flex items-end gap-1" aria-hidden>
                  {turnout.by_hour.map((bucket) => {
                    const peak = Math.max(...turnout.by_hour.map((b) => b.cast), 1)
                    return (
                      <li
                        key={bucket.hour}
                        className="bg-module/60 min-h-[2px] w-full rounded-t"
                        style={{ height: `${(bucket.cast / peak) * 48}px` }}
                        title={`${bucket.hour}: ${bucket.cast}`}
                      />
                    )
                  })}
                </ul>
                <p className="text-muted-foreground mt-2 text-xs">
                  {number(turnout.most_from_one_device)} ballots came from the busiest single
                  device. A high figure is the shape ballot stuffing actually takes, which is why it
                  is published rather than only monitored.
                </p>
              </div>
            ) : null}
          </div>
          <p className="text-muted-foreground text-xs leading-relaxed">
            Turnout only. There is no running tally while a poll is open — a live count changes how
            people vote and whether they bother, so the API refuses one to everybody, including the
            returning officer.
          </p>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Check a receipt</h2>
        <div className="bg-card shadow-card max-w-md rounded-lg p-4">
          <p className="text-muted-foreground mb-3 text-sm">
            Paste a receipt token to confirm the ballot is in the count. It will never tell you — or
            anyone else — what the ballot said.
          </p>
          <ReceiptChecker />
        </div>
      </section>

      {petitions.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Petitions</h2>
          <ul className="divide-border divide-y text-sm">
            {petitions.map((petition) => (
              <li key={petition.id} className="py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                  <span className="font-medium">
                    <span className="font-mono text-xs">{petition.reference}</span>
                    <span className="ml-2">{humaniseStatus(petition.ground)}</span>
                  </span>
                  <StatusBadge tone={toneForStatus(petition.status)} dot={false}>
                    {humaniseStatus(petition.status)}
                  </StatusBadge>
                </div>
                <p className="text-muted-foreground mt-1 text-xs">{petition.submission}</p>
                {petition.determination ? (
                  <p className="mt-1 text-xs">
                    <span className="font-medium">Determination:</span> {petition.determination}
                    {petition.remedy ? ` Remedy: ${petition.remedy}` : ""}
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

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className={mono ? "mt-0.5 font-mono text-sm" : "mt-0.5 text-sm font-medium"}>{value}</dd>
    </div>
  )
}
