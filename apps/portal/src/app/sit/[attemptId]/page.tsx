import { notFound, redirect } from "next/navigation"

import { ApiError } from "@acmis/api-client"
import { acmis, requireUser } from "@acmis/auth/server"

import { APP } from "@/lib/config"

import { ExamRunner } from "./runner"

/**
 * The sitting page.
 *
 * Deliberately outside the portal chrome: no sidebar, no launcher, no
 * navigation. A candidate under time pressure should have nothing on screen
 * that is not the paper, and a nav link out of an examination is a mis-tap
 * away from a lost attempt.
 *
 * The paper comes from the server already stripped of answer keys and in this
 * candidate's own drawn and shuffled order — see `get_paper`. Nothing here can
 * reveal a key, because nothing here ever receives one.
 */

export const metadata = { title: "Examination" }

export default async function SitPage({
  params,
}: {
  params: Promise<{ attemptId: string }>
}) {
  const { attemptId } = await params
  await requireUser(APP)
  const client = await acmis(APP)

  let paper
  let attempts
  try {
    ;[paper, attempts] = await Promise.all([
      client.learning.paper(attemptId),
      client.learning.myAttempts(),
    ])
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound()
    if (error instanceof ApiError && error.isForbidden) redirect("/assessments")
    throw error
  }

  const attempt = attempts.find((a) => a.id === attemptId)
  if (!attempt) notFound()

  // A submitted attempt must not reopen. The API refuses a save on one
  // anyway, but landing back on the runner would look to a candidate as
  // though their submission had been undone.
  if (attempt.status !== "in_progress") {
    redirect(`/assessments?submitted=${attemptId}`)
  }

  const assessment = await client.learning
    .assessment(attempt.assessment_id)
    .then((envelope) => envelope.data)
    .catch(() => null)

  return (
    <ExamRunner
      attemptId={attemptId}
      assessmentTitle={attempt.assessment_title}
      totalMarks={attempt.total_marks}
      expiresAt={attempt.expires_at}
      questions={paper}
      behaviour={assessment?.behaviour ?? "deferred_feedback"}
      allowBacktracking={true}
      onePerPage={false}
      monitorFocus={false}
    />
  )
}
