"use client"

import { useActionState } from "react"

import { catalogueWork } from "./actions"

/** The cataloguing form. Client-side only so the outcome lands in place. */
export function CatalogueForm({ branches }: { branches: Array<{ id: string; label: string }> }) {
  const [result, action, pending] = useActionState(catalogueWork, null)

  const field = "border-input bg-background w-full rounded-md border px-3 py-2 text-base sm:text-sm"

  return (
    <form action={action} className="bg-card shadow-card space-y-5 rounded-lg p-5">
      {result?.ok ? (
        <p
          role="status"
          className="rounded-md border border-emerald-600/30 bg-emerald-600/10 px-3 py-2 text-sm text-emerald-800 dark:text-emerald-300"
        >
          {result.ok}{" "}
          {result.recordId ? (
            <a className="underline" href={`/catalogue/${result.recordId}`}>
              Open the record
            </a>
          ) : null}
        </p>
      ) : null}
      {result?.error ? (
        <p
          role="alert"
          className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm"
        >
          {result.error}
        </p>
      ) : null}

      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold">The work</legend>
        <div className="space-y-1.5">
          <label htmlFor="title" className="text-sm font-medium">
            Title
          </label>
          <input id="title" name="title" required className={field} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="statement_of_responsibility" className="text-sm font-medium">
              Statement of responsibility
            </label>
            <input
              id="statement_of_responsibility"
              name="statement_of_responsibility"
              placeholder="Silberschatz, Korth and Sudarshan"
              className={field}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="authors" className="text-sm font-medium">
              Authors
            </label>
            <input
              id="authors"
              name="authors"
              placeholder="Separate with semicolons"
              className={field}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="edition" className="text-sm font-medium">
              Edition
            </label>
            <input id="edition" name="edition" placeholder="7th" className={field} />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="published_year" className="text-sm font-medium">
              Year
            </label>
            <input
              id="published_year"
              name="published_year"
              type="number"
              min={1400}
              max={2200}
              className={field}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="publisher" className="text-sm font-medium">
              Publisher
            </label>
            <input id="publisher" name="publisher" className={field} />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="isbn" className="text-sm font-medium">
              ISBN
            </label>
            <input id="isbn" name="isbn" inputMode="numeric" className={field} />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="material_kind" className="text-sm font-medium">
              Kind
            </label>
            <select id="material_kind" name="material_kind" className={field}>
              {["book", "journal", "thesis", "report", "e_book", "audio", "video"].map((value) => (
                <option key={value} value={value}>
                  {value.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="subjects" className="text-sm font-medium">
              Subject headings
            </label>
            <input
              id="subjects"
              name="subjects"
              placeholder="Separate with semicolons"
              className={field}
            />
          </div>
        </div>
      </fieldset>

      <fieldset className="space-y-4 border-t pt-5">
        <legend className="text-sm font-semibold">Copies</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="library_id" className="text-sm font-medium">
              Library
            </label>
            <select id="library_id" name="library_id" className={field}>
              <option value="">—</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="call_number" className="text-sm font-medium">
              Call number
            </label>
            <input id="call_number" name="call_number" placeholder="005.74 SIL" className={field} />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="copies" className="text-sm font-medium">
              How many
            </label>
            <input
              id="copies"
              name="copies"
              type="number"
              min={0}
              max={50}
              defaultValue={1}
              className={field}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="price" className="text-sm font-medium">
              Price each
            </label>
            <input id="price" name="price" type="number" min={0} step="0.01" className={field} />
            <p className="text-muted-foreground text-xs">
              What a replacement charge is based on. A lost book charged at a guessed price is a
              charge that gets waived.
            </p>
          </div>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" name="short_loan_first" className="mt-1" defaultChecked />
          <span>
            Make the first copy short loan
            <span className="text-muted-foreground block text-xs">
              The reserve copy that never leaves the reading room overnight.
            </span>
          </span>
        </label>
      </fieldset>

      <button
        type="submit"
        disabled={pending}
        className="bg-primary text-primary-foreground h-11 rounded-md px-6 text-sm font-medium disabled:opacity-60"
      >
        {pending ? "Cataloguing…" : "Catalogue"}
      </button>
    </form>
  )
}
