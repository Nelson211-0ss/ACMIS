"use client"

import { useActionState } from "react"
import { useFormStatus } from "react-dom"

import { type ActionResult, lodgeSpecialExam } from "./actions"

const GROUNDS = [
  ["illness", "Illness"],
  ["hospitalisation", "Hospitalisation"],
  ["bereavement", "Bereavement"],
  ["accident", "Accident"],
  ["national_duty", "National or university duty"],
  ["institutional_error", "An error by the university"],
  ["other", "Something else"],
] as const

/**
 * The special-examination application.
 *
 * `institutional_error` is on the list because it happens — a clash, a paper
 * that started late, a mark sheet that lost an entry — and a form that only
 * offers reasons the student is at fault pushes those cases into an informal
 * channel where they are not counted.
 */
export function SpecialExamForm({
  semesterId,
  courses,
}: {
  semesterId: string
  courses: Array<{ id: string; label: string }>
}) {
  const [state, formAction] = useActionState<ActionResult | null, FormData>(
    lodgeSpecialExam,
    null,
  )

  return (
    <form action={formAction} className="space-y-4">
      <input type="hidden" name="semester_id" value={semesterId} />

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="font-medium">Course</span>
          <select
            name="course_offering_id"
            required
            className="border-input bg-background mt-1 min-h-11 w-full rounded-md border px-3 py-2 text-base sm:text-sm"
          >
            <option value="">Choose the paper you missed</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="font-medium">Kind</span>
          <select
            name="kind"
            defaultValue="special"
            className="border-input bg-background mt-1 min-h-11 w-full rounded-md border px-3 py-2 text-base sm:text-sm"
          >
            <option value="special">Special — I missed the paper</option>
            <option value="supplementary">Supplementary — I sat and failed</option>
          </select>
          <span className="text-muted-foreground mt-1 block text-xs">
            A special examination is marked out of full marks. A supplementary
            is capped at the pass mark, whatever you score.
          </span>
        </label>

        <label className="block text-sm">
          <span className="font-medium">Ground</span>
          <select
            name="ground"
            required
            className="border-input bg-background mt-1 min-h-11 w-full rounded-md border px-3 py-2 text-base sm:text-sm"
          >
            <option value="">Choose one</option>
            {GROUNDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="font-medium">Date you missed it</span>
          <input
            type="date"
            name="missed_on"
            className="border-input bg-background mt-1 min-h-11 w-full rounded-md border px-3 py-2 text-base sm:text-sm"
          />
        </label>
      </div>

      <label className="block text-sm">
        <span className="font-medium">What happened</span>
        <textarea
          name="narrative"
          required
          minLength={20}
          maxLength={4000}
          rows={5}
          className="border-input bg-background mt-1 w-full rounded-md border px-3 py-2 text-base sm:text-sm"
          placeholder="Set out the facts and the dates. The board reads this text and nothing else, so say what happened rather than how you feel about it."
        />
      </label>

      <Submit />

      {state?.ok ? (
        <p className="text-success text-sm" role="status">
          {state.ok}
        </p>
      ) : null}
      {state?.error ? (
        <p className="text-destructive text-sm" role="alert">
          {state.error}
        </p>
      ) : null}
    </form>
  )
}

function Submit() {
  const { pending } = useFormStatus()
  return (
    <button
      type="submit"
      disabled={pending}
      className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 rounded-md px-4 py-2.5 text-sm font-medium disabled:opacity-60"
    >
      {pending ? "Lodging…" : "Lodge the application"}
    </button>
  )
}
