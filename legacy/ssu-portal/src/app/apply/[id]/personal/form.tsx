"use client";

import { useActionState } from "react";
import { User } from "lucide-react";
import { OfflineForm } from "@/components/offline-form";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { Field, FieldGrid, Input, Select } from "@/components/ui/field";
import { STATES } from "@/lib/data/reference";
import type { PersonalDetails } from "@/lib/types";
import type { StepState } from "../actions";

export function PersonalForm({
  action,
  values,
  applicationId,
  updatedAt,
}: {
  action: (prev: StepState, formData: FormData) => Promise<StepState>;
  values: PersonalDetails;
  applicationId: string;
  updatedAt: string;
}) {
  const [state, formAction, pending] = useActionState<StepState, FormData>(
    action,
    undefined,
  );
  const errors = state?.ok === false ? (state.errors ?? {}) : {};

  return (
    <OfflineForm
      action={formAction}
      draftKey={`ssu:app:${applicationId}:personal`}
      remoteUpdatedAt={updatedAt}
    >
      {state?.ok === false && state.message ? (
        <Callout tone="error" className="mb-5">
          {state.message}
        </Callout>
      ) : null}

      <Card>
        <CardHeader
          icon={User}
          title="Personal details"
          description="Use the spelling exactly as it appears on your SSCSE certificate. It cannot be changed after admission."
        />
        <CardBody className="space-y-5">
          <FieldGrid>
            <Field label="First name" name="firstName" required error={errors.firstName}>
              <Input
                id="firstName"
                name="firstName"
                defaultValue={values.firstName}
                autoComplete="given-name"
                aria-invalid={Boolean(errors.firstName)}
                required
              />
            </Field>
            <Field label="Middle name" name="middleName" error={errors.middleName}>
              <Input
                id="middleName"
                name="middleName"
                defaultValue={values.middleName ?? ""}
                autoComplete="additional-name"
              />
            </Field>
            <Field label="Family name" name="lastName" required error={errors.lastName}>
              <Input
                id="lastName"
                name="lastName"
                defaultValue={values.lastName}
                autoComplete="family-name"
                aria-invalid={Boolean(errors.lastName)}
                required
              />
            </Field>
            <Field
              label="Date of birth"
              name="dateOfBirth"
              required
              error={errors.dateOfBirth}
            >
              <Input
                id="dateOfBirth"
                name="dateOfBirth"
                type="date"
                defaultValue={values.dateOfBirth}
                autoComplete="bday"
                aria-invalid={Boolean(errors.dateOfBirth)}
                required
              />
            </Field>
            <Field label="Sex" name="sex" required error={errors.sex}>
              <Select
                id="sex"
                name="sex"
                defaultValue={values.sex}
                aria-invalid={Boolean(errors.sex)}
                required
              >
                <option value="">Select…</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
              </Select>
            </Field>
            <Field
              label="Nationality"
              name="nationality"
              required
              error={errors.nationality}
            >
              <Input
                id="nationality"
                name="nationality"
                defaultValue={values.nationality || "South Sudanese"}
                aria-invalid={Boolean(errors.nationality)}
                required
              />
            </Field>
          </FieldGrid>

          <FieldGrid className="border-t border-line pt-5">
            <Field
              label="State of origin"
              name="stateOfOrigin"
              required
              error={errors.stateOfOrigin}
            >
              <Select
                id="stateOfOrigin"
                name="stateOfOrigin"
                defaultValue={values.stateOfOrigin}
                aria-invalid={Boolean(errors.stateOfOrigin)}
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
            <Field label="County" name="county" required error={errors.county}>
              <Input
                id="county"
                name="county"
                defaultValue={values.county}
                aria-invalid={Boolean(errors.county)}
                required
              />
            </Field>
            <Field
              label="Your mobile number"
              name="phone"
              required
              hint="We send your application reference and decision here by SMS."
              error={errors.phone}
            >
              <Input
                id="phone"
                name="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                placeholder="0920 123 456"
                defaultValue={values.phone}
                aria-invalid={Boolean(errors.phone)}
                required
              />
            </Field>
            <Field label="Email address" name="email" required error={errors.email}>
              <Input
                id="email"
                name="email"
                type="email"
                inputMode="email"
                autoComplete="email"
                autoCapitalize="none"
                spellCheck={false}
                defaultValue={values.email}
                aria-invalid={Boolean(errors.email)}
                required
              />
            </Field>
            <Field
              label="National ID or nationality certificate number"
              name="nationalId"
              hint="Leave blank if you do not hold one yet. It will not stop your application."
              error={errors.nationalId}
            >
              <Input
                id="nationalId"
                name="nationalId"
                defaultValue={values.nationalId ?? ""}
                spellCheck={false}
              />
            </Field>
            <Field
              label="Disability or support needs"
              name="disability"
              hint="Tell us if you need particular arrangements for lectures or examinations."
              error={errors.disability}
            >
              <Input
                id="disability"
                name="disability"
                defaultValue={values.disability ?? ""}
              />
            </Field>
          </FieldGrid>

          <FieldGrid className="border-t border-line pt-5">
            <Field
              label="Parent or guardian's name"
              name="guardianName"
              required
              error={errors.guardianName}
            >
              <Input
                id="guardianName"
                name="guardianName"
                defaultValue={values.guardianName}
                aria-invalid={Boolean(errors.guardianName)}
                required
              />
            </Field>
            <Field
              label="Parent or guardian's mobile"
              name="guardianPhone"
              required
              hint="Used only if we cannot reach you."
              error={errors.guardianPhone}
            >
              <Input
                id="guardianPhone"
                name="guardianPhone"
                type="tel"
                inputMode="tel"
                placeholder="0920 123 456"
                defaultValue={values.guardianPhone}
                aria-invalid={Boolean(errors.guardianPhone)}
                required
              />
            </Field>
          </FieldGrid>
        </CardBody>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : "Save and continue"}
          </Button>
        </CardFooter>
      </Card>
    </OfflineForm>
  );
}
