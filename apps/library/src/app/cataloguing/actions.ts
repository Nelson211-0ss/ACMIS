"use server"

import { revalidatePath } from "next/cache"

import { ApiError } from "@acmis/api-client"
import { acmis } from "@acmis/auth/server"

import { APP } from "@/lib/config"

export interface CatalogueResult {
  ok?: string
  error?: string
  recordId?: string
}

/**
 * Catalogue a work and accession its copies in one step.
 *
 * One submission, two calls: the record then its copies. Splitting them
 * across two screens is how a library ends up with records for books nobody
 * ever accessioned — they exist in the catalogue, a reader finds them, and
 * there is nothing on the shelf.
 */
export async function catalogueWork(
  _previous: CatalogueResult | null,
  formData: FormData,
): Promise<CatalogueResult> {
  const title = String(formData.get("title") ?? "").trim()
  if (!title) return { error: "A record needs a title." }

  const copies = Number(formData.get("copies") ?? 0)
  const libraryId = String(formData.get("library_id") ?? "").trim()
  const callNumber = String(formData.get("call_number") ?? "").trim()
  const shortLoanFirst = formData.get("short_loan_first") === "on"

  if (copies > 0 && !libraryId) {
    return { error: "Say which library the copies belong to." }
  }

  const client = await acmis(APP)
  try {
    const record = await client.library.createRecord({
      title,
      material_kind: String(formData.get("material_kind") ?? "book"),
      statement_of_responsibility:
        String(formData.get("statement_of_responsibility") ?? "").trim() || undefined,
      authors: String(formData.get("authors") ?? "")
        .split(";")
        .map((a) => a.trim())
        .filter(Boolean),
      edition: String(formData.get("edition") ?? "").trim() || undefined,
      publisher: String(formData.get("publisher") ?? "").trim() || undefined,
      published_year: formData.get("published_year")
        ? Number(formData.get("published_year"))
        : undefined,
      isbn: String(formData.get("isbn") ?? "").replace(/-/g, "").trim() || undefined,
      classification: callNumber.split(" ")[0] || undefined,
      subjects: String(formData.get("subjects") ?? "")
        .split(";")
        .map((s) => s.trim())
        .filter(Boolean),
    })

    let accessioned = 0
    for (let index = 0; index < copies; index += 1) {
      // The accession number is the library's permanent number for the item
      // and is written inside the front cover; the barcode is what a scanner
      // reads and may be replaced when a label peels off.
      const stamp = `${Date.now().toString().slice(-7)}${index}`
      await client.library.addCopy(record.id, {
        library_id: libraryId,
        accession_number: stamp,
        barcode: `KIT${stamp}`,
        call_number: callNumber || undefined,
        loan_class: shortLoanFirst && index === 0 ? "short_loan" : "normal",
        acquired_on: new Date().toISOString().slice(0, 10),
        price_minor: formData.get("price")
          ? Math.round(Number(formData.get("price")) * 100)
          : undefined,
      })
      accessioned += 1
    }

    revalidatePath("/cataloguing")
    revalidatePath("/catalogue")
    return {
      ok:
        accessioned > 0
          ? `Catalogued “${record.title}” with ${accessioned} cop${
              accessioned === 1 ? "y" : "ies"
            }.`
          : `Catalogued “${record.title}”. No copies accessioned yet.`,
      recordId: record.id,
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message }
    throw error
  }
}
