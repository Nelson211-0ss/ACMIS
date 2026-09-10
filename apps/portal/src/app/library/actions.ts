"use server"

import { revalidatePath } from "next/cache"

import { ApiError } from "@acmis/api-client"
import { acmis } from "@acmis/auth/server"

import { APP } from "@/lib/config"

export interface ActionResult {
  ok?: string
  error?: string
}

/**
 * Renew a loan the reader is holding.
 *
 * Refused by the API when someone else has reserved the item or the renewal
 * limit is reached — both are rules a reader is entitled to hear stated, so
 * the message comes back verbatim rather than being flattened to "failed".
 */
export async function renewLoan(
  _previous: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const loanId = String(formData.get("loan_id") ?? "")
  if (!loanId) return { error: "No loan selected." }

  const client = await acmis(APP)
  try {
    const loan = await client.library.renew(loanId)
    revalidatePath("/library")
    return { ok: `Renewed. Now due ${loan.due_on}.` }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message }
    throw error
  }
}

/** Join the queue for a title whose copies are all out. */
export async function reserveRecord(
  _previous: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const recordId = String(formData.get("record_id") ?? "")
  if (!recordId) return { error: "No title selected." }

  const client = await acmis(APP)
  try {
    await client.library.reserve(recordId)
    revalidatePath("/library")
    return { ok: "Reserved. You will be told when a copy is on the hold shelf." }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message }
    throw error
  }
}

/** Leave the queue. */
export async function cancelReservation(
  _previous: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const reservationId = String(formData.get("reservation_id") ?? "")
  if (!reservationId) return { error: "No reservation selected." }

  const client = await acmis(APP)
  try {
    await client.library.cancelReservation(reservationId)
    revalidatePath("/library")
    return { ok: "Cancelled." }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message }
    throw error
  }
}
