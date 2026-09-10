import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatRow, StatTile } from "@acmis/ui/components/stat-tile"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money, number } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

import { cancelReservation, renewLoan, reserveRecord } from "./actions"
import { LibraryButton } from "./form"

export const metadata = { title: "Library" }

/**
 * The reader's own library account, and the catalogue.
 *
 * Loans lead, because the thing a reader opens this page for is a due date.
 * The catalogue search is below it rather than above: looking something up is
 * the second most common reason to be here, and putting a search box at the
 * top pushes the overdue book off the first screen on a phone.
 */
export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; kind?: string }>
}) {
  const { q, kind } = await searchParams
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, membership, results, eResources] = await Promise.all([
    client.public.institution().catch(() => null),
    client.library.myMembership().catch(() => null),
    q
      ? client.library.search({ q, material_kind: kind, limit: 20 }).catch(() => null)
      : Promise.resolve(null),
    client.library.eResources().catch(() => []),
  ])

  const currency = institution?.currency ?? "UGX"
  const member = membership?.member
  const loans = membership?.loans ?? []
  const overdue = loans.filter((loan) => loan.overdue)
  const unpaidFines = (membership?.fines ?? []).filter(
    (fine) => fine.reason !== "waived",
  )
  const owed = unpaidFines.reduce((total, fine) => total + fine.amount_minor, 0)

  return (
    <PortalShell user={user} institution={institution} currentPath="/library">
      <PageHeader
        title="Library"
        description="Your loans, your queue, what you owe, and the catalogue. Everything on this page is your own borrowing record — the circulation register as a whole is not readable by borrowers, by design."
      />

      {!member ? (
        <EmptyState
          icon={<Icons.Library className="size-8" />}
          title="You are not registered as a borrower"
          reason="Membership is created at the library desk on your first visit; bring your campus ID. You can search the catalogue below without it."
        />
      ) : (
        <>
          <StatRow>
            <StatTile
              label="On loan"
              value={number(member.items_on_loan)}
              footnote="Items you are holding"
              icon={<Icons.BookOpen />}
            />
            <StatTile
              label="Overdue"
              value={number(overdue.length)}
              footnote={overdue.length > 0 ? "Fines accrue daily" : "Nothing late"}
              icon={<Icons.Clock />}
              emphasis={overdue.length > 0}
            />
            <StatTile
              label="Owed"
              value={money(owed || member.outstanding_fines_minor, currency)}
              footnote="Clears your graduation hold"
              icon={<Icons.CircleDollarSign />}
            />
            <StatTile
              label="Membership"
              value={humaniseStatus(member.status)}
              footnote={
                member.expires_on
                  ? `${humaniseStatus(member.borrower_category)} · to ${date(member.expires_on)}`
                  : humaniseStatus(member.borrower_category)
              }
              icon={<Icons.IdCard />}
            />
          </StatRow>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold">On loan to you</h2>
            {loans.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Nothing out at the moment.
              </p>
            ) : (
              <ul className="divide-border divide-y rounded-lg border">
                {loans.map((loan) => (
                  <li
                    key={loan.loan_id}
                    className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 p-4"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{loan.title}</p>
                      <p className="text-muted-foreground mt-0.5 text-xs">
                        <span className="font-mono">{loan.accession_number}</span>
                        {loan.renewals > 0
                          ? ` · renewed ${loan.renewals} time${loan.renewals === 1 ? "" : "s"}`
                          : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-2">
                      <StatusBadge tone={loan.overdue ? "danger" : "success"} dot={false}>
                        {loan.overdue ? "Overdue" : "Due"} {date(loan.due_on)}
                      </StatusBadge>
                      <LibraryButton
                        action={renewLoan}
                        label="Renew"
                        hidden={{ loan_id: loan.loan_id }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {overdue.length > 0 ? (
              <p className="text-destructive text-xs leading-relaxed">
                An overdue item accrues a fine every day it is out, and an
                unpaid library fine blocks graduation clearance. Returning it is
                cheaper than renewing it late.
              </p>
            ) : null}
          </section>

          {(membership?.reservations ?? []).length > 0 ? (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold">Your queue</h2>
              <ul className="divide-border divide-y rounded-lg border">
                {(membership?.reservations ?? []).map((reservation) => (
                  <li
                    key={reservation.reservation_id}
                    className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 p-4"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{reservation.title}</p>
                      <p className="text-muted-foreground mt-0.5 text-xs">
                        Position {reservation.queue_position} ·{" "}
                        {humaniseStatus(reservation.status)}
                        {reservation.collect_by
                          ? ` · collect by ${date(reservation.collect_by)}`
                          : ""}
                      </p>
                    </div>
                    <LibraryButton
                      action={cancelReservation}
                      label="Cancel"
                      hidden={{ reservation_id: reservation.reservation_id }}
                      subtle
                    />
                  </li>
                ))}
              </ul>
              <p className="text-muted-foreground text-xs leading-relaxed">
                A copy on the hold shelf is kept for you for a fixed number of
                days and then passed to the next reader. Cancel one you no
                longer need rather than letting it expire — it moves the queue.
              </p>
            </section>
          ) : null}

          {unpaidFines.length > 0 ? (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold">Fines</h2>
              <ul className="divide-border divide-y text-sm">
                {unpaidFines.map((fine) => (
                  <li
                    key={fine.fine_id}
                    className="flex flex-wrap items-baseline justify-between gap-x-4 py-2"
                  >
                    <span>
                      <span className="tabular font-medium">
                        {money(fine.amount_minor, currency)}
                      </span>
                      <span className="text-muted-foreground ml-2 text-xs">
                        {humaniseStatus(fine.reason)}
                        {fine.days_overdue !== null
                          ? ` · ${fine.days_overdue} days overdue`
                          : ""}
                      </span>
                    </span>
                    <span className="text-muted-foreground shrink-0 text-xs">
                      raised {date(fine.raised_on)}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="text-muted-foreground text-xs leading-relaxed">
                Fines are paid at the library desk or the bursary. A fine raised
                in error is waived by the librarian with a reason recorded — it
                is not deleted.
              </p>
            </section>
          ) : null}
        </>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Search the catalogue</h2>
        <form action="/library" method="get" className="flex flex-wrap gap-2">
          <input
            type="search"
            name="q"
            defaultValue={q ?? ""}
            placeholder="Title, author, subject or ISBN"
            aria-label="Search the catalogue"
            className="border-input bg-background min-h-11 min-w-0 flex-1 rounded-md border px-3 py-2 text-base sm:text-sm"
          />
          <select
            name="kind"
            defaultValue={kind ?? ""}
            aria-label="Material type"
            className="border-input bg-background min-h-11 rounded-md border px-3 py-2 text-sm"
          >
            <option value="">Anything</option>
            <option value="book">Books</option>
            <option value="journal">Journals</option>
            <option value="thesis">Theses</option>
            <option value="report">Reports</option>
            <option value="audio_visual">Audio-visual</option>
          </select>
          <button
            type="submit"
            className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 rounded-md px-4 py-2.5 text-sm font-medium"
          >
            Search
          </button>
        </form>

        {q && results ? (
          results.items.length === 0 ? (
            <EmptyState
              icon={<Icons.SearchX className="size-8" />}
              title={`Nothing catalogued matches “${q}”`}
              reason="Try fewer words, or an author's surname alone. If the library does not hold something you need for a course, your lecturer can request it — acquisitions are prioritised by whether a course reading list depends on the title."
            />
          ) : (
            <ul className="divide-border divide-y rounded-lg border">
              {results.items.map((record) => (
                <li key={record.id} className="p-4">
                  <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">
                        {record.title}
                        {record.subtitle ? (
                          <span className="text-muted-foreground">
                            : {record.subtitle}
                          </span>
                        ) : null}
                      </p>
                      <p className="text-muted-foreground mt-0.5 text-xs">
                        {record.authors.join("; ") || "Author not recorded"}
                        {record.edition ? ` · ${record.edition}` : ""}
                        {record.published_year ? ` · ${record.published_year}` : ""}
                        {record.publisher ? ` · ${record.publisher}` : ""}
                      </p>
                      <p className="text-muted-foreground mt-0.5 text-xs">
                        {humaniseStatus(record.material_kind)}
                        {record.classification ? (
                          <>
                            {" · shelf "}
                            <span className="font-mono">{record.classification}</span>
                          </>
                        ) : null}
                        {record.isbn ? ` · ISBN ${record.isbn}` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-2">
                      {record.online_url ? (
                        <a
                          href={record.online_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-module text-xs underline"
                        >
                          Read online
                        </a>
                      ) : null}
                      {member ? (
                        <LibraryButton
                          action={reserveRecord}
                          label="Reserve"
                          hidden={{ record_id: record.id }}
                        />
                      ) : null}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )
        ) : null}
      </section>

      {eResources.filter((resource) => resource.is_active).length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Databases and e-resources</h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {eResources
              .filter((resource) => resource.is_active)
              .map((resource) => (
                <li key={resource.id} className="bg-card rounded-lg border p-4">
                  <p className="text-sm font-medium">{resource.name}</p>
                  <p className="text-muted-foreground mt-0.5 text-xs">
                    {resource.provider} · {humaniseStatus(resource.kind)}
                    {resource.concurrent_users
                      ? ` · ${resource.concurrent_users} concurrent users`
                      : ""}
                  </p>
                  {resource.access_url ? (
                    <a
                      href={resource.access_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-module mt-2 inline-block text-xs underline"
                    >
                      Open
                    </a>
                  ) : null}
                  <p className="text-muted-foreground mt-1 text-xs">
                    Subscription runs to {date(resource.expires_on)}
                    {resource.authentication_method
                      ? ` · ${humaniseStatus(resource.authentication_method)}`
                      : ""}
                  </p>
                </li>
              ))}
          </ul>
        </section>
      ) : null}
    </PortalShell>
  )
}
