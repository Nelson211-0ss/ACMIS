"use client";

import { useActionState, useState } from "react";
import { BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { Badge } from "@/components/ui/badge";
import { Field, Select } from "@/components/ui/field";
import { checkEligibility } from "@/lib/application";
import { ssp } from "@/lib/format";
import type { Faculty, Programme, SubjectResult } from "@/lib/types";
import type { StepState } from "../actions";

const RANK_LABEL = ["First choice", "Second choice", "Third choice"] as const;

/**
 * Programme ranking.
 *
 * Eligibility is computed in the browser from marks already entered, so an
 * applicant sees immediately whether they meet a cut-off instead of finding
 * out weeks later. It is advisory only — a marginal candidate can still apply,
 * and the board decides.
 */
export function ProgrammeForm({
  action,
  grouped,
  subjects,
  initial,
  applicationId,
}: {
  action: (prev: StepState, formData: FormData) => Promise<StepState>;
  grouped: Array<{ faculty: Faculty; programmes: Programme[] }>;
  subjects: SubjectResult[];
  /** Programme ids already chosen, in rank order. */
  initial: string[];
  applicationId: string;
}) {
  const [state, formAction, pending] = useActionState<StepState, FormData>(
    action,
    undefined,
  );

  const [choices, setChoices] = useState<[string, string, string]>([
    initial[0] ?? "",
    initial[1] ?? "",
    initial[2] ?? "",
  ]);

  const all = grouped.flatMap((g) => g.programmes);
  const byId = (id: string) => all.find((p) => p.id === id);

  const set = (index: number, value: string) =>
    setChoices((prev) => {
      const next = [...prev] as [string, string, string];
      next[index] = value;
      return next;
    });

  const chosen = choices.filter((c) => c !== "");
  const duplicate = new Set(chosen).size !== chosen.length;

  return (
    <form action={formAction} id={`choices-${applicationId}`}>
      {state?.ok === false && state.message ? (
        <Callout tone="error" className="mb-5">
          {state.message}
        </Callout>
      ) : null}

      {subjects.length === 0 ? (
        <Callout tone="warning" className="mb-5" title="No marks entered yet">
          Go back and enter your SSCSE subjects first, and we can tell you which
          programmes you qualify for as you choose.
        </Callout>
      ) : null}

      <Card>
        <CardHeader
          icon={BookOpen}
          title="Programme choices"
          description="Rank up to three. If you are not offered your first choice, you are considered for the second, then the third."
        />
        <CardBody className="space-y-5">
          {[0, 1, 2].map((index) => {
            const value = choices[index];
            const programme = value ? byId(value) : undefined;
            const eligibility =
              programme && subjects.length > 0
                ? checkEligibility(programme, subjects)
                : null;

            return (
              <div key={index}>
                <Field
                  label={RANK_LABEL[index]}
                  name={`choice${index + 1}`}
                  required={index === 0}
                >
                  <Select
                    id={`choice${index + 1}`}
                    name={`choice${index + 1}`}
                    value={value}
                    onChange={(e) => set(index, e.target.value)}
                    required={index === 0}
                  >
                    <option value="">
                      {index === 0 ? "Select a programme…" : "None"}
                    </option>
                    {grouped.map((group) => (
                      <optgroup key={group.faculty.id} label={group.faculty.name}>
                        {group.programmes.map((p) => (
                          <option
                            key={p.id}
                            value={p.id}
                            // Hide programmes taken by another rank.
                            disabled={choices.some(
                              (c, i) => i !== index && c === p.id,
                            )}
                          >
                            {p.name} ({p.code})
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </Select>
                </Field>

                {programme ? (
                  <div className="mt-2.5 rounded border border-line bg-canvas px-3.5 py-3">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12.5px]">
                      <span className="text-muted">
                        {programme.durationYears} years ·{" "}
                        {programme.award.toLowerCase()} degree
                      </span>
                      <span className="text-line-strong" aria-hidden>
                        /
                      </span>
                      <span className="nums text-muted">
                        {ssp(programme.tuitionPerSemesterSSP)} per semester
                      </span>
                      <span className="text-line-strong" aria-hidden>
                        /
                      </span>
                      <span className="nums text-muted">
                        {programme.intake} places
                      </span>
                    </div>

                    {eligibility ? (
                      <div className="mt-2.5">
                        {eligibility.eligible ? (
                          <Badge tone="green">
                            You qualify — aggregate {eligibility.aggregate} against{" "}
                            {programme.minimumAggregate} required
                            {eligibility.margin > 0
                              ? `, ${eligibility.margin} above`
                              : ""}
                          </Badge>
                        ) : (
                          <div>
                            <Badge tone="gold">Below the stated requirement</Badge>
                            <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[12.5px] text-ink-soft">
                              {eligibility.reasons.map((reason) => (
                                <li key={reason}>{reason}</li>
                              ))}
                            </ul>
                            <p className="mt-1.5 text-[12px] text-muted">
                              You may still apply. The admissions board considers
                              applications below the cut-off when places remain.
                            </p>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="mt-2 text-[12.5px] text-muted">
                        Required subjects: {programme.requiredSubjects.join(", ")}.
                        Minimum aggregate {programme.minimumAggregate}.
                      </p>
                    )}
                  </div>
                ) : null}
              </div>
            );
          })}

          {duplicate ? (
            <Callout tone="error">
              You have picked the same programme twice. Choose three different
              programmes, or leave the later ranks empty.
            </Callout>
          ) : null}
        </CardBody>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={pending || duplicate || chosen.length === 0}>
            {pending ? "Saving…" : "Save and continue"}
          </Button>
        </CardFooter>
      </Card>
    </form>
  );
}
