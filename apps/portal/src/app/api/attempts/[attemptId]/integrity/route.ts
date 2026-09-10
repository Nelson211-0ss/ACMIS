import { NextResponse, type NextRequest } from "next/server"

import { acmis } from "@acmis/auth/server"

import { APP } from "@/lib/config"

/**
 * Report an integrity signal.
 *
 * Fire-and-forget: a failure here must never interrupt a candidate. The signal
 * is for an invigilator to weigh afterwards, and losing one is a much smaller
 * problem than an error dialog appearing over an examination.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ attemptId: string }> },
) {
  const { attemptId } = await params
  const body = (await request.json().catch(() => ({}))) as {
    kind?: string
    detail?: Record<string, unknown>
  }
  if (!body.kind) return new NextResponse(null, { status: 204 })

  const client = await acmis(APP)
  await client.learning
    .reportIntegrityEvent(attemptId, { kind: body.kind, detail: body.detail })
    .catch(() => undefined)

  return new NextResponse(null, { status: 204 })
}
