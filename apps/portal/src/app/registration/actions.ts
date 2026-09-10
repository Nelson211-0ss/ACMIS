"use server"

import { revalidatePath } from "next/cache"

import { ApiError } from "@acmis/api-client"
import { acmis } from "@acmis/auth/server"

import { APP } from "@/lib/config"

export interface ActionResult {
  ok?: string
  error?: string
  /** The API's machine-readable reason, so the page can say what would fix it. */
  details?: Record<string, unknown>
}

/**
 * Open a registration for the current semester.
 *
 * Idempotent at the API — it returns the existing row rather than creating a
 * second one — so a double-tap on a slow connection is harmless.
 */
export async function openRegistration(
  _previous: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const studentId = String(formData.get("student_id") ?? "")
  const semesterId = String(formData.get("semester_id") ?? "")
  if (!studentId || !semesterId) return { error: "No current semester to register for." }

  const client = await acmis(APP)
  try {
    await client.students.openRegistration(studentId, semesterId)
    revalidatePath("/registration")
    return { ok: "Registration opened. Add your courses, then submit it." }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message, details: error.details }
    throw error
  }
}

/**
 * Submit a registration for approval.
 *
 * The window and the fee threshold are checked by the API, not here: they are
 * policy an institution adjusts, and a copy of the rule in the browser would
 * go stale the first time it changed.
 */
export async function submitRegistration(
  _previous: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const registrationId = String(formData.get("registration_id") ?? "")
  if (!registrationId) return { error: "Nothing to submit." }

  const client = await acmis(APP)
  try {
    await client.students.submitRegistration(registrationId)
    revalidatePath("/registration")
    revalidatePath("/courses")
    return { ok: "Submitted. Your department has to approve it before it counts." }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message, details: error.details }
    throw error
  }
}
