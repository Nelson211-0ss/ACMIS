import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge, toneForStatus } from "@acmis/ui/components/status-badge"
import { date, humaniseStatus, money, surnameFirst } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

import { ReportLostForm } from "./form"

export const metadata = { title: "Campus ID" }

/**
 * The campus identity card.
 *
 * Shown as a card face rather than a table row, because that is the object
 * the student is holding and matching against. The serial and barcode are in
 * mono for the same reason they are on the card itself: they get read aloud
 * over a phone to a registry clerk.
 */
export default async function IdCardPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, record, cards, campuses] = await Promise.all([
    client.public.institution().catch(() => null),
    client.students.myRecord().catch(() => null),
    client.lifecycle.myIdCards().catch(() => []),
    client.reference.campuses().catch(() => []),
  ])

  const currency = institution?.currency ?? "UGX"
  const student = record?.data
  const primary = student?.programmes.find((p) => p.is_primary)
  const active = cards.find((card) => card.status === "active")
  const superseded = cards.filter((card) => card.id !== active?.id)
  const campusName = (id: string | null) =>
    campuses.find((campus) => campus.id === id)?.name ?? null

  return (
    <PortalShell user={user} institution={institution} currentPath="/id-card">
      <PageHeader
        icon={<Icons.IdCard />}
        title="Campus ID"
        description="Your identity card, as the registry issued it. Carry it to every examination — an examination card alone is not proof of who you are."
      />

      {active && student ? (
        <section className="space-y-4">
          <div className="bg-card shadow-card max-w-md overflow-hidden rounded-xl shadow-sm">
            <div className="bg-module/10 border-module/30 flex items-center gap-3 border-b px-4 py-3">
              {institution?.crest_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={institution.crest_url}
                  alt=""
                  className="size-10 shrink-0 object-contain"
                />
              ) : (
                <Icons.GraduationCap className="text-module size-8 shrink-0" aria-hidden />
              )}
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">
                  {institution?.name ?? user.tenant_name}
                </p>
                <p className="text-muted-foreground text-xs">Student identity card</p>
              </div>
            </div>
            <div className="space-y-3 p-4">
              <div>
                <p className="text-muted-foreground text-xs">Holder</p>
                <p className="text-lg font-semibold">{surnameFirst(student)}</p>
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-muted-foreground text-xs">Student number</dt>
                  <dd className="mt-0.5 font-mono">{student.student_number}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">Serial</dt>
                  <dd className="mt-0.5 font-mono">{active.serial}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">Campus</dt>
                  <dd className="mt-0.5">{campusName(active.campus_id) ?? "Main"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">Year of study</dt>
                  <dd className="mt-0.5">{primary?.current_year_of_study ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">Issued</dt>
                  <dd className="mt-0.5">{date(active.issued_on)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs">Expires</dt>
                  <dd className="mt-0.5">{date(active.expires_on)}</dd>
                </div>
              </dl>
              {active.barcode ? (
                <div className="border-t pt-3">
                  <p className="text-muted-foreground text-xs">Barcode</p>
                  <p className="mt-0.5 font-mono text-sm tracking-widest">{active.barcode}</p>
                </div>
              ) : null}
            </div>
            <div className="bg-muted/40 flex items-center justify-between border-t px-4 py-2">
              <StatusBadge tone={toneForStatus(active.status)}>
                {humaniseStatus(active.status)}
              </StatusBadge>
              <span className="text-muted-foreground text-xs">
                {humaniseStatus(active.reason)} issue
              </span>
            </div>
          </div>

          {active.collected_at ? null : (
            <p className="text-warning-foreground border-warning/40 bg-warning/10 max-w-md rounded-lg border px-4 py-3 text-sm">
              This card has been issued but not collected. Pick it up from the registry counter;
              bring something else with your photograph on it.
            </p>
          )}

          <details className="max-w-md rounded-lg border p-4">
            <summary className="cursor-pointer text-sm font-medium">I have lost this card</summary>
            <p className="text-muted-foreground mt-2 text-sm">
              Reporting it stops the card verifying anywhere on campus — at the library desk, the
              hall door and the gate — immediately. This cannot be undone; if the card turns up you
              will still need the replacement.
              {active.replacement_fee_minor
                ? ` A replacement costs ${money(active.replacement_fee_minor, currency)}.`
                : ""}
            </p>
            <div className="mt-3">
              <ReportLostForm cardId={active.id} />
            </div>
          </details>
        </section>
      ) : (
        <EmptyState
          icon={<Icons.IdCard className="size-8" />}
          title="You do not have an active campus ID"
          reason={
            cards.length > 0
              ? "Every card on your record has been replaced, lost or expired. Ask the registry to issue a replacement."
              : "Cards are issued by the registry once your admission is complete and your photograph is on file."
          }
        />
      )}

      {superseded.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Earlier cards</h2>
          <ul className="divide-border divide-y text-sm">
            {superseded.map((card) => (
              <li
                key={card.id}
                className="flex flex-wrap items-baseline justify-between gap-x-4 py-2"
              >
                <span>
                  <span className="font-mono text-xs">{card.serial}</span>
                  <span className="text-muted-foreground ml-2 text-xs">
                    {humaniseStatus(card.reason)} · issued {date(card.issued_on)}
                    {card.reported_lost_on ? ` · reported lost ${date(card.reported_lost_on)}` : ""}
                  </span>
                </span>
                <StatusBadge tone={toneForStatus(card.status)} dot={false}>
                  {humaniseStatus(card.status)}
                </StatusBadge>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground text-xs leading-relaxed">
            Superseded cards stay on the record rather than being deleted. When a card is presented
            months later, the question is which card it was and when it stopped being valid.
          </p>
        </section>
      ) : null}
    </PortalShell>
  )
}
