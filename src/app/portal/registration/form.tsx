"use client";

import { useActionState, useState } from "react";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Badge } from "@/components/ui/badge";
import { ChoiceRow } from "@/components/ui/field";
import type { Course } from "@/lib/types";
import type { RegistrationState } from "./actions";

interface CourseRow {
  course: Course;
  registered: boolean;
  /** Unmet prerequisite course codes. Non-empty means the row is locked. */
  missingPrerequisites: string[];
}

/**
 * Course selection.
 *
 * Compulsory courses render as locked, checked rows with a hidden input, so
 * they always post even though the student cannot untick them. Credit load is
 * totalled live because exceeding the cap is the most common reason the
 * registrar rejects a registration.
 */
export function RegistrationForm({
  action,
  rows,
  maxCredits,
  semester,
}: {
  action: (
    prev: RegistrationState,
    formData: FormData,
  ) => Promise<RegistrationState>;
  rows: CourseRow[];
  maxCredits: number;
  semester: 1 | 2;
}) {
  const [state, formAction, pending] = useActionState<RegistrationState, FormData>(
    action,
    undefined,
  );

  const [selected, setSelected] = useState<Set<string>>(
    () =>
      new Set(
        rows
          .filter((r) => r.course.compulsory || r.registered)
          .map((r) => r.course.id),
      ),
  );

  const credits = rows
    .filter((r) => selected.has(r.course.id))
    .reduce((sum, r) => sum + r.course.creditHours, 0);

  const over = credits > maxCredits;

  const compulsory = rows.filter((r) => r.course.compulsory);
  const electives = rows.filter((r) => !r.course.compulsory);

  return (
    <form action={formAction} className="space-y-5">
      {state?.ok === false ? (
        <Callout tone="error" title="Registration not saved">
          {state.message}
        </Callout>
      ) : null}

      {state?.ok === true ? (
        <Callout tone="success" title="Registration saved">
          <p>{state.message}</p>
          {state.rejected.length > 0 ? (
            <ul className="mt-2 list-disc space-y-0.5 pl-4">
              {state.rejected.map((r) => (
                <li key={r.code}>
                  <span className="font-semibold">{r.code}</span> was not
                  registered — {r.reason.toLowerCase()}.
                </li>
              ))}
            </ul>
          ) : null}
        </Callout>
      ) : null}

      <section>
        <h2 className="mb-2.5 text-[13px] font-semibold uppercase tracking-wide text-muted">
          Compulsory · Semester {semester}
        </h2>
        <div className="space-y-2">
          {compulsory.map(({ course, missingPrerequisites }) => (
            <div key={course.id}>
              {/* Locked but still submitted. */}
              <input type="hidden" name="courses" value={course.id} />
              <ChoiceRow
                checked
                disabled
                label={
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="nums font-semibold text-brand-700">
                      {course.code}
                    </span>
                    <span>{course.title}</span>
                    <Badge tone="neutral">{course.creditHours} CH</Badge>
                  </span>
                }
                description={
                  missingPrerequisites.length > 0
                    ? `Compulsory, but you have not passed ${missingPrerequisites.join(", ")} — see the registrar.`
                    : `${course.lecturer} · compulsory, cannot be dropped`
                }
              >
                <Lock className="h-4 w-4 text-muted" aria-hidden />
              </ChoiceRow>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2.5 text-[13px] font-semibold uppercase tracking-wide text-muted">
          Electives
        </h2>
        <div className="space-y-2">
          {electives.map(({ course, missingPrerequisites }) => {
            const locked = missingPrerequisites.length > 0;
            const checked = selected.has(course.id);
            return (
              <ChoiceRow
                key={course.id}
                checked={checked}
                disabled={locked}
                label={
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="nums font-semibold text-brand-700">
                      {course.code}
                    </span>
                    <span>{course.title}</span>
                    <Badge tone="neutral">{course.creditHours} CH</Badge>
                  </span>
                }
                description={
                  locked
                    ? `Locked — requires a pass in ${missingPrerequisites.join(", ")}`
                    : course.lecturer
                }
              >
                <input
                  type="checkbox"
                  name="courses"
                  value={course.id}
                  checked={checked}
                  disabled={locked}
                  onChange={(e) =>
                    setSelected((prev) => {
                      const next = new Set(prev);
                      if (e.target.checked) next.add(course.id);
                      else next.delete(course.id);
                      return next;
                    })
                  }
                  className="h-4 w-4 accent-[--brand-700]"
                />
              </ChoiceRow>
            );
          })}
        </div>
      </section>

      {/* Sticky footer so the load total and the save button follow the thumb. */}
      <div className="sticky bottom-16 z-10 -mx-4 border-y border-line bg-surface px-4 py-3 sm:-mx-5 sm:px-5 lg:bottom-0 lg:rounded-lg lg:border">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[13px] text-muted">
              Credit load{" "}
              <span
                className={`nums font-semibold ${over ? "text-red-700" : "text-ink"}`}
              >
                {credits}
              </span>{" "}
              <span className="nums text-faint">/ {maxCredits} maximum</span>
            </p>
            {over ? (
              <p className="mt-0.5 text-[12.5px] font-medium text-red-700">
                Drop {credits - maxCredits} credit
                {credits - maxCredits === 1 ? "" : "s"} before saving.
              </p>
            ) : null}
          </div>
          <Button type="submit" disabled={pending || over}>
            {pending ? "Saving…" : "Save registration"}
          </Button>
        </div>
      </div>
    </form>
  );
}
