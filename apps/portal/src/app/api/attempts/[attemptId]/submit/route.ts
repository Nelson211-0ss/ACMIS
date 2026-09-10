import { NextResponse, type NextRequest } from "next/server"

import { ApiError } from "@acmis/api-client"
import { acmis } from "@acmis/auth/server"

import { APP } from "@/lib/config"

/**
 * Submit an attempt.
 *
 * A form POST, so it works with JavaScript disabled and — more usefully —
 * still works when a script error has broken the runner. A candidate who
 * cannot submit is the worst failure this system has, so the last step is the
 * most boring possible mechanism.
 */
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ attemptId: string }> },
) {
  const { attemptId } = await params
  const client = await acmis(APP)

  try {
    await client.learning.submitAttempt(attemptId)
  } catch (error) {
    if (error instanceof ApiError && error.isConflict) {
      // Already submitted, or expired and marked by the server. Both are
      // success from the candidate's point of view.
      return NextResponse.redirect(
        new URL(`/assessments?submitted=${attemptId}`, _request.url),
        { status: 303 },
      )
    }
    if (error instanceof ApiError) {
      return NextResponse.redirect(
        new URL(
          `/sit/${attemptId}?error=${encodeURIComponent(error.message)}`,
          _request.url,
        ),
        { status: 303 },
      )
    }
    throw error
  }

  return NextResponse.redirect(
    new URL(`/assessments?submitted=${attemptId}`, _request.url),
    { status: 303 },
  )
}
