import * as Icons from "lucide-react"

import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { StatusBadge } from "@acmis/ui/components/status-badge"

import { QualityShell } from "@/components/shell"
import { APP } from "@/lib/config"

export const metadata = { title: "Questionnaires" }

/**
 * Evaluation instruments.
 *
 * Versioned rather than edited. A question reworded between semesters makes
 * a trend meaningless, and these numbers are compared across years — so an
 * instrument in use is never changed: a new version is published and the old
 * one retired. Same reasoning as a curriculum version, for the same reason.
 */
export default async function InstrumentsPage() {
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const [institution, instruments] = await Promise.all([
    client.public.institution().catch(() => null),
    client.quality.instruments({ published_only: false }).catch(() => []),
  ])

  const byCode = new Map<string, typeof instruments>()
  for (const instrument of instruments) {
    byCode.set(instrument.code, [...(byCode.get(instrument.code) ?? []), instrument])
  }

  return (
    <QualityShell user={user} institution={institution} currentPath="/instruments">
      <PageHeader
        icon={<Icons.ListChecks />}
        title="Questionnaires"
        description="Versioned, because the numbers have to be comparable. An instrument in use is never edited — a new version is published and the old one retired."
      />

      {instruments.length === 0 ? (
        <EmptyState
          icon={<Icons.ListChecks />}
          title="No questionnaires"
          reason="An instrument is a set of questions grouped into dimensions. Reporting is by dimension, because nobody acts on a single question's mean."
        />
      ) : (
        <div className="space-y-6">
          {[...byCode.entries()].map(([code, versions]) => (
            <section key={code} className="space-y-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <span className="font-mono">{code}</span>
                <span className="text-muted-foreground font-normal">
                  {versions.length} version{versions.length === 1 ? "" : "s"}
                </span>
              </h2>
              {versions
                .sort((a, b) => b.version - a.version)
                .map((instrument) => (
                  <article
                    key={instrument.id}
                    className="bg-card shadow-card space-y-3 rounded-lg p-4"
                  >
                    <header className="flex flex-wrap items-baseline justify-between gap-2">
                      <h3 className="font-medium">
                        {instrument.name}{" "}
                        <span className="text-muted-foreground text-sm">v{instrument.version}</span>
                      </h3>
                      <StatusBadge tone={instrument.is_published ? "success" : "neutral"}>
                        {instrument.is_published ? "published" : "draft"}
                      </StatusBadge>
                    </header>
                    {instrument.introduction ? (
                      <p className="text-muted-foreground text-sm">{instrument.introduction}</p>
                    ) : null}
                    <ol className="space-y-1.5 text-sm">
                      {instrument.questions.map((question, index) => {
                        const text = String((question as Record<string, unknown>).text ?? "")
                        const dimension = (question as Record<string, unknown>).dimension
                        const kind = String((question as Record<string, unknown>).kind ?? "")
                        return (
                          <li key={index} className="flex flex-wrap gap-2">
                            <span className="text-muted-foreground tabular-nums">{index + 1}.</span>
                            <span className="flex-1">{text}</span>
                            {dimension ? (
                              <StatusBadge tone="neutral" dot={false}>
                                {String(dimension)}
                              </StatusBadge>
                            ) : null}
                            <span className="text-muted-foreground text-xs">
                              {kind.replace(/_/g, " ")}
                            </span>
                          </li>
                        )
                      })}
                    </ol>
                    {instrument.dimensions.length > 0 ? (
                      <footer className="text-muted-foreground text-xs">
                        Dimensions: {instrument.dimensions.join(", ")}
                      </footer>
                    ) : null}
                  </article>
                ))}
            </section>
          ))}
        </div>
      )}
    </QualityShell>
  )
}
