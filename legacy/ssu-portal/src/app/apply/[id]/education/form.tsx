"use client";

import { useActionState, useState } from "react";
import { Calculator, GraduationCap, Plus, Trash2 } from "lucide-react";
import { OfflineForm } from "@/components/offline-form";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { Field, FieldGrid, Input, Select } from "@/components/ui/field";
import { SSCSE_SUBJECTS, STATES } from "@/lib/data/reference";
import { aggregate } from "@/lib/application";
import type { EducationDetails } from "@/lib/types";
import type { StepState } from "../actions";

/** Rows start at eight — the number of subjects most candidates sit. */
const DEFAULT_ROWS = 8;

interface Row {
  key: number;
  subject: string;
  mark: string;
}

export function EducationForm({
  action,
  values,
  applicationId,
  updatedAt,
}: {
  action: (prev: StepState, formData: FormData) => Promise<StepState>;
  values: EducationDetails;
  applicationId: string;
  updatedAt: string;
}) {
  const [state, formAction, pending] = useActionState<StepState, FormData>(
    action,
    undefined,
  );
  const errors = state?.ok === false ? (state.errors ?? {}) : {};

  const [rows, setRows] = useState<Row[]>(() => {
    const existing = values.subjects.map((s, i) => ({
      key: i,
      subject: s.subject,
      mark: String(s.mark),
    }));
    const blanks = Array.from(
      { length: Math.max(0, DEFAULT_ROWS - existing.length) },
      (_, i) => ({ key: existing.length + i, subject: "", mark: "" }),
    );
    return [...existing, ...blanks];
  });

  // Live aggregate, so an applicant sees where they stand before choosing
  // programmes on the next step.
  const filled = rows
    .filter((r) => r.subject !== "" && r.mark !== "")
    .map((r) => ({ subject: r.subject, mark: Number(r.mark) }))
    .filter((r) => Number.isFinite(r.mark));
  const agg = filled.length > 0 ? aggregate(filled) : null;

  // Subject can only be claimed once; a taken option is hidden from the others.
  const taken = new Set(rows.map((r) => r.subject).filter((s) => s !== ""));

  const update = (key: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  // `subjects` errors arrive either as a whole-array message or indexed per row.
  const arrayError = errors["subjects"];

  return (
    <OfflineForm
      action={formAction}
      draftKey={`ssu:app:${applicationId}:education`}
      remoteUpdatedAt={updatedAt}
    >
      {state?.ok === false && state.message ? (
        <Callout tone="error" className="mb-5">
          {state.message}
        </Callout>
      ) : null}

      <Card>
        <CardHeader
          icon={GraduationCap}
          title="Secondary school"
          description="Where you sat the South Sudan Certificate of Secondary Education."
        />
        <CardBody>
          <FieldGrid>
            <Field
              label="School name"
              name="secondarySchool"
              required
              error={errors.secondarySchool}
              className="sm:col-span-2"
            >
              <Input
                id="secondarySchool"
                name="secondarySchool"
                defaultValue={values.secondarySchool}
                aria-invalid={Boolean(errors.secondarySchool)}
                required
              />
            </Field>
            <Field
              label="State"
              name="schoolState"
              required
              error={errors.schoolState}
            >
              <Select
                id="schoolState"
                name="schoolState"
                defaultValue={values.schoolState}
                aria-invalid={Boolean(errors.schoolState)}
                required
              >
                <option value="">Select…</option>
                {STATES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Year completed"
              name="yearCompleted"
              required
              error={errors.yearCompleted}
            >
              <Input
                id="yearCompleted"
                name="yearCompleted"
                inputMode="numeric"
                maxLength={4}
                placeholder="2025"
                defaultValue={values.yearCompleted}
                aria-invalid={Boolean(errors.yearCompleted)}
                required
              />
            </Field>
            <Field
              label="SSCSE index number"
              name="indexNumber"
              required
              hint="Printed on your marksheet, e.g. CE/0231/2025/0117."
              error={errors.indexNumber}
              className="sm:col-span-2"
            >
              <Input
                id="indexNumber"
                name="indexNumber"
                spellCheck={false}
                autoCapitalize="characters"
                defaultValue={values.indexNumber}
                aria-invalid={Boolean(errors.indexNumber)}
                required
              />
            </Field>
          </FieldGrid>
        </CardBody>
      </Card>

      <Card className="mt-5">
        <CardHeader
          icon={Calculator}
          title="Subjects and marks"
          description="Enter every subject you sat, with the mark out of 100. At least six, including English."
          action={
            agg === null ? null : (
              <div className="text-right">
                <p className="text-[11.5px] font-medium uppercase tracking-wide text-muted">
                  Best-six aggregate
                </p>
                <p className="nums text-xl font-semibold leading-tight text-ink">
                  {agg}
                </p>
              </div>
            )
          }
        />
        <CardBody>
          {arrayError ? (
            <Callout tone="error" className="mb-4">
              {arrayError}
            </Callout>
          ) : null}

          <ul className="space-y-2">
            {rows.map((row, index) => {
              const rowError = errors[`subjects.${index}.mark`];
              return (
                <li key={row.key} className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <label className="sr-only" htmlFor={`subject-${row.key}`}>
                      Subject {index + 1}
                    </label>
                    <Select
                      id={`subject-${row.key}`}
                      name="subject"
                      value={row.subject}
                      onChange={(e) => update(row.key, { subject: e.target.value })}
                    >
                      <option value="">Subject…</option>
                      {SSCSE_SUBJECTS.filter(
                        (s) => !taken.has(s) || s === row.subject,
                      ).map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </Select>
                  </div>

                  <div className="w-[88px] shrink-0">
                    <label className="sr-only" htmlFor={`mark-${row.key}`}>
                      Mark for subject {index + 1}
                    </label>
                    <Input
                      id={`mark-${row.key}`}
                      name="mark"
                      inputMode="numeric"
                      placeholder="/100"
                      maxLength={3}
                      value={row.mark}
                      aria-invalid={Boolean(rowError)}
                      onChange={(e) =>
                        update(row.key, {
                          mark: e.target.value.replace(/[^\d]/g, "").slice(0, 3),
                        })
                      }
                      className="nums text-center"
                    />
                    {rowError ? (
                      <p role="alert" className="mt-1 text-[11.5px] font-medium text-red-700">
                        {rowError}
                      </p>
                    ) : null}
                  </div>

                  <button
                    type="button"
                    aria-label={`Remove subject ${index + 1}`}
                    onClick={() =>
                      setRows((prev) =>
                        prev.length <= 6
                          ? prev.map((r) =>
                              r.key === row.key ? { ...r, subject: "", mark: "" } : r,
                            )
                          : prev.filter((r) => r.key !== row.key),
                      )
                    }
                    className="mt-0.5 flex h-11 w-9 shrink-0 items-center justify-center rounded text-muted transition-colors hover:bg-red-100 hover:text-red-700"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                </li>
              );
            })}
          </ul>

          {rows.length < 12 ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-3"
              onClick={() =>
                setRows((prev) => [
                  ...prev,
                  { key: Math.max(...prev.map((r) => r.key), 0) + 1, subject: "", mark: "" },
                ])
              }
            >
              <Plus className="h-4 w-4" aria-hidden />
              Add another subject
            </Button>
          ) : null}
        </CardBody>
        <CardFooter className="justify-between">
          <p className="text-[12.5px] text-muted">
            {filled.length} of at least 6 subjects entered
          </p>
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : "Save and continue"}
          </Button>
        </CardFooter>
      </Card>
    </OfflineForm>
  );
}
