"use server"

import { revalidatePath } from "next/cache"

import { ApiError } from "@acmis/api-client"
import { acmis } from "@acmis/auth/server"

import { APP } from "@/lib/config"

/** What the desk needs to say to the reader standing in front of it. */
export interface DeskResult {
  ok?: string
  error?: string
  /**
   * The machine-readable reason. Kept so the form can say something specific
   * — "you owe 40,000, and the limit is 200,000" — rather than repeating the
   * sentence the API already sent.
   */
  details?: Record<string, unknown>
}

export async function issueLoan(
  _previous: DeskResult | null,
  formData: FormData,
): Promise<DeskResult> {
  const barcode = String(formData.get("barcode") ?? "").trim()
  const membership = String(formData.get("membership_number") ?? "").trim()
  if (!barcode || !membership) {
    return { error: "Scan the book and the card." }
  }

  const client = await acmis(APP)
  try {
    const loan = await client.library.issue({ barcode, membership_number: membership })
    revalidatePath("/desk")
    return {
      ok: `Issued. Due ${new Date(loan.due_on).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })}.`,
    }
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message, details: error.details }
    }
    throw error
  }
}

export async function receiveLoan(
  _previous: DeskResult | null,
  formData: FormData,
): Promise<DeskResult> {
  const barcode = String(formData.get("barcode") ?? "").trim()
  const condition = String(formData.get("condition") ?? "").trim() || undefined
  if (!barcode) return { error: "Scan the book." }

  const client = await acmis(APP)
  try {
    const result = await client.library.return({ barcode, condition })
    revalidatePath("/desk")
    const said = ["Returned."]
    if (result.fine) {
      said.push(
        `${result.fine.days_overdue ?? 0} day(s) overdue — charge of ${(
          result.fine.amount_minor / 100
        ).toLocaleString()}.`,
      )
    }
    if (result.on_hold_shelf) {
      said.push("Hold shelf: a reader is waiting for this title.")
    }
    return { ok: said.join(" ") }
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message, details: error.details }
    }
    throw error
  }
}
