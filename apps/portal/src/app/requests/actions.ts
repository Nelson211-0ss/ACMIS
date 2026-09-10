"use server"

import { revalidatePath } from "next/cache"

import { ApiError } from "@acmis/api-client"
import { acmis } from "@acmis/auth/server"

import { APP } from "@/lib/config"

export interface ActionResult {
  ok?: string
  error?: string
  /** Field-level complaints from the API, keyed by field name. */
  details?: Record<string, unknown>
}

/**
 * Apply for a special or supplementary examination.
 *
 * Lodged without evidence on purpose — a student in hospital cannot produce a
 * certificate that day — but the API will not *grant* it without evidence, and
 * the form says so rather than letting the student assume the matter is
 * settled.
 */
export async function lodgeSpecialExam(
  _previous: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const offering = String(formData.get("course_offering_id") ?? "")
  const semester = String(formData.get("semester_id") ?? "")
  const kind = String(formData.get("kind") ?? "special")
  const ground = String(formData.get("ground") ?? "")
  const narrative = String(formData.get("narrative") ?? "").trim()
  const missedOn = String(formData.get("missed_on") ?? "").trim()

  if (!offering) return { error: "Choose the course." }
  if (!ground) return { error: "Choose the ground you are applying on." }
  if (narrative.length < 20) {
    return {
      error:
        "Explain what happened in at least a couple of sentences — the board decides on this text.",
    }
  }

  const client = await acmis(APP)
  try {
    const request = await client.lifecycle.lodgeSpecialExam({
      course_offering_id: offering,
      semester_id: semester,
      kind,
      ground,
      narrative,
      missed_on: missedOn || null,
    })
    revalidatePath("/requests")
    return {
      ok: `Lodged as ${request.reference}. Take your evidence to the faculty office — it cannot be granted until the evidence is verified.`,
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message, details: error.details }
    throw error
  }
}
