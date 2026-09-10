"use server"

import { revalidatePath } from "next/cache"

import { ApiError } from "@acmis/api-client"
import { acmis } from "@acmis/auth/server"

import { APP } from "@/lib/config"

export interface VoteResult {
  error?: string
  /** One receipt per position, keyed by position id. The voter's only copy. */
  receipts?: Record<string, string>
  castAt?: string
}

/**
 * Cast a ballot.
 *
 * The receipts come back to the browser and are shown once. They are not
 * written anywhere on the server against this voter, so there is no second
 * chance to read them — the form says so before the button is pressed.
 */
export async function castBallot(
  _previous: VoteResult | null,
  formData: FormData,
): Promise<VoteResult> {
  const electionId = String(formData.get("election_id") ?? "")
  const positionIds = String(formData.get("position_ids") ?? "")
    .split(",")
    .filter(Boolean)
  if (!electionId || positionIds.length === 0) return { error: "Nothing to vote on." }

  // An absent field is an abstention on that position, not a missing answer:
  // the constitution treats a blank ballot paper as cast, and so does this.
  const choices: Record<string, string[]> = {}
  for (const positionId of positionIds) {
    choices[positionId] = formData
      .getAll(`position:${positionId}`)
      .map((value) => String(value))
      .filter((value) => value !== "" && value !== "abstain")
  }

  const client = await acmis(APP)
  try {
    const receipt = await client.elections.vote(electionId, choices)
    revalidatePath(`/elections/${electionId}`)
    return { receipts: receipt.receipts, castAt: receipt.cast_at }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message }
    throw error
  }
}

export interface CheckResult {
  message?: string
  error?: string
}

/** Confirm a receipt is in the count. Never returns the choice. */
export async function checkReceipt(
  _previous: CheckResult | null,
  formData: FormData,
): Promise<CheckResult> {
  const token = String(formData.get("token") ?? "").trim()
  if (!token) return { error: "Paste the receipt token." }

  const client = await acmis(APP)
  try {
    const check = await client.elections.verifyReceipt(token)
    if (!check.found) {
      return {
        error:
          "No ballot matches that token. Check for a transcription slip; if it is right, take it to the returning officer.",
      }
    }
    return {
      message: check.counted
        ? `Found and in the count${check.abstention ? ", recorded as an abstention" : ""}. Cast ${check.cast_at ?? "—"}.`
        : "Found, but not yet in a count — the poll has not closed.",
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message }
    throw error
  }
}
