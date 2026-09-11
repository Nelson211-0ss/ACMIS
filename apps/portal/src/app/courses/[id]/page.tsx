import * as Icons from "lucide-react"
import Link from "next/link"
import { notFound } from "next/navigation"

import { ApiError } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"
import { EmptyState, NotPermitted } from "@acmis/ui/components/empty-state"
import { PageHeader } from "@acmis/ui/components/page-header"
import { dateTime, duration, humaniseStatus, number } from "@acmis/ui/lib/format"

import { PortalShell } from "@/components/shell"
import { APP } from "@/lib/config"

/**
 * One course's space: notes, recordings, reading, and the tests open on it.
 *
 * Material is grouped by week, which is the organising principle the lecturer
 * publishes against. An undifferentiated list of files is how a course space
 * becomes unusable by about week four.
 */
export default async function CourseSpacePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const user = await requireUser(APP)
  const client = await acmis(APP)

  const institution = await client.public.institution().catch(() => null)

  // `openSpace` is idempotent and returns the existing space; a student
  // reaching a course with no space yet gets the empty state rather than a 404.
  let space
  try {
    space = await client.learning.openSpace(id)
  } catch (error) {
    if (error instanceof ApiError && error.isForbidden) {
      return (
        <PortalShell user={user} institution={institution} currentPath="/courses">
          <NotPermitted what="this course's material" contact="your lecturer" />
        </PortalShell>
      )
    }
    if (error instanceof ApiError && error.status === 404) notFound()
    throw error
  }

  const [materials, assessments] = await Promise.all([
    client.learning.materials(space.id).catch(() => []),
    client.learning.spaceAssessments(space.id).catch(() => []),
  ])

  // Grouped by week, with general material last: a student looking for this
  // week's notes should not scroll past the module handbook to reach them.
  const byWeek = new Map<number | null, typeof materials>()
  for (const material of materials) {
    const key = material.week_number ?? null
    byWeek.set(key, [...(byWeek.get(key) ?? []), material])
  }
  const weeks = [...byWeek.keys()].sort((a, b) => {
    if (a === null) return 1
    if (b === null) return -1
    return a - b
  })

  const open = assessments.filter((a) => a.status === "open")

  return (
    <PortalShell user={user} institution={institution} currentPath="/courses">
      <PageHeader
        icon={<Icons.BookOpen />}
        title={`Course ${id.slice(0, 8)}`}
        description={
          space.is_published
            ? `${number(materials.length)} item${materials.length === 1 ? "" : "s"} published`
            : "Your lecturer has not published this space yet."
        }
        breadcrumbs={
          <nav className="text-muted-foreground text-xs" aria-label="Breadcrumb">
            <Link href="/courses" className="hover:text-foreground underline">
              My courses
            </Link>
            <span aria-hidden> / </span>
            <span>{id.slice(0, 8)}</span>
          </nav>
        }
      />

      {open.length > 0 ? (
        <section className="border-module/50 bg-module/5 rounded-lg border p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Icons.Timer className="text-module size-4" aria-hidden />
            {open.length} test{open.length === 1 ? "" : "s"} open now
          </h2>
          <ul className="mt-3 space-y-2">
            {open.map((assessment) => (
              <li
                key={assessment.id}
                className="bg-card shadow-card flex flex-wrap items-center justify-between gap-3 rounded-md p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{assessment.title}</p>
                  <p className="text-muted-foreground text-xs">
                    {number(assessment.total_marks)} marks
                    {assessment.duration_minutes
                      ? ` · ${duration(assessment.duration_minutes)}`
                      : ""}
                    {assessment.closes_at
                      ? ` · closes ${dateTime(assessment.closes_at, institution?.locale, institution?.timezone)}`
                      : ""}
                  </p>
                </div>
                <form action={startAttempt.bind(null, assessment.id)}>
                  <button
                    type="submit"
                    className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 shrink-0 rounded-md px-4 text-sm font-semibold"
                  >
                    Start
                  </button>
                </form>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-2 text-xs">
            Once started, the clock runs on the server. Your answers save as you give them, so a
            dropped connection does not lose your work.
          </p>
        </section>
      ) : null}

      {materials.length === 0 ? (
        <EmptyState
          title="No material published yet"
          reason="Notes, slides and recordings appear here as your lecturer publishes them. Items can also be scheduled — week 7's notes may exist and not be visible until week 7."
          icon={<Icons.FolderOpen className="size-8" />}
        />
      ) : (
        <div className="space-y-6">
          {weeks.map((week) => (
            <section key={week ?? "general"}>
              <h2 className="text-base font-semibold">
                {week === null ? "General" : `Week ${week}`}
              </h2>
              <ul className="mt-2 divide-y rounded-lg border">
                {(byWeek.get(week) ?? []).map((material) => (
                  <li key={material.id} className="flex items-start gap-3 p-3">
                    <span className="text-muted-foreground mt-0.5 shrink-0">
                      <MaterialIcon kind={material.kind} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{material.title}</p>
                      {material.description ? (
                        <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed">
                          {material.description}
                        </p>
                      ) : null}
                      <p className="text-muted-foreground mt-1 text-xs">
                        {humaniseStatus(material.kind)}
                        {material.duration_seconds
                          ? ` · ${duration(Math.round(material.duration_seconds / 60))}`
                          : ""}
                        {material.topic ? ` · ${material.topic}` : ""}
                      </p>
                    </div>
                    <a
                      href={material.external_url ?? `/api/materials/${material.id}`}
                      // A view is recorded when a student opens something, so
                      // "has this student engaged with week 6" is answerable
                      // in week 6 rather than after the first test.
                      className="text-module min-h-11 shrink-0 px-2 py-2.5 text-xs font-medium underline"
                    >
                      {material.allow_download ? "Open" : "View"}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </PortalShell>
  )
}

async function startAttempt(assessmentId: string) {
  "use server"
  const { redirect } = await import("next/navigation")
  const client = await acmis(APP)
  try {
    const attempt = await client.learning.startAttempt(assessmentId)
    redirect(`/sit/${attempt.id}`)
  } catch (error) {
    if (error instanceof ApiError) {
      redirect(`/assessments?error=${encodeURIComponent(error.message)}`)
    }
    throw error
  }
}

function MaterialIcon({ kind }: { kind: string }) {
  const Icon =
    {
      notes: Icons.FileText,
      slides: Icons.Presentation,
      reading: Icons.BookOpen,
      recording: Icons.Video,
      video_link: Icons.Youtube,
      link: Icons.Link,
      dataset: Icons.Database,
      past_paper: Icons.FileQuestion,
      announcement: Icons.Megaphone,
    }[kind] ?? Icons.File
  return <Icon className="size-4" aria-hidden />
}
