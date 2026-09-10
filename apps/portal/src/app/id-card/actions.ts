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
 * Report a campus ID lost or stolen.
 *
 * Deliberately available to the holder rather than only at a counter: the
 * window between losing a card and reporting it is exactly when it gets used
 * by someone else, and a form that is open at 2am closes that window.
 */
export async function reportLost(
  _previous: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const cardId = String(formData.get("card_id") ?? "")
  const stolen = formData.get("stolen") === "on"
  if (!cardId) return { error: "No card selected." }

  const client = await acmis(APP)
  try {
    await client.lifecycle.reportCardLost(cardId, stolen)
    revalidatePath("/id-card")
    return {
      ok: stolen
        ? "Reported stolen. The card no longer verifies. Take the police reference to the registry for a replacement."
        : "Reported lost. The card no longer verifies. A replacement is chargeable.",
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message }
    throw error
  }
}
