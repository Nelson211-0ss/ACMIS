import { NextResponse, type NextRequest } from "next/server"

import { ApiError } from "@acmis/api-client"
import { acmis } from "@acmis/auth/server"

import { APP } from "@/lib/config"

/**
 * Save one answer.
 *
 * A route handler rather than a Server Action because the runner needs the
 * response — it shows the candidate whether their work is safe, and retries
 * what did not land. A Server Action's revalidation round trip would also
 * re-render the paper on every keystroke.
 *
 * This is the reason the BFF exists: the browser posts to its own origin and
 * never holds an API token, so an XSS anywhere in the app cannot lift one.
 */
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ attemptId: string }> },
) {
  const { attemptId } = await params
  const body = (await request.json()) as {
    question_id: string
    answer: Record<string, unknown>
    flagged?: boolean
    seconds_spent?: number
  }

  const client = await acmis(APP)
  try {
    await client.learning.saveAnswer(attemptId, {
      question_id: body.question_id,
      answer: body.answer ?? {},
      flagged: body.flagged,
      seconds_spent: body.seconds_spent,
    })
    return new NextResponse(null, { status: 204 })
  } catch (error) {
    if (error instanceof ApiError) {
      // The status is passed through so the runner can tell a transient
      // failure (retry) from a refusal (the attempt has closed, stop).
      return NextResponse.json(
        { error: { code: error.code, message: error.message } },
        { status: error.status },
      )
    }
    return NextResponse.json(
      { error: { code: "upstream_failed", message: "Could not reach the server." } },
      { status: 502 },
    )
  }
}
