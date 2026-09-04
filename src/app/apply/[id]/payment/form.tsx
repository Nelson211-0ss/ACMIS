"use client";

import { useActionState, useState } from "react";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { ChoiceRow, Field, Input } from "@/components/ui/field";
import { PAYMENT_METHODS } from "@/lib/data/payments";
import { ssp } from "@/lib/format";
import type { PaymentMethod } from "@/lib/types";
import type { StepState } from "../actions";

export function PaymentForm({
  action,
  applicationId,
  feeSSP,
  phone,
}: {
  action: (prev: StepState, formData: FormData) => Promise<StepState>;
  applicationId: string;
  feeSSP: number;
  /** From the personal details step, so it does not have to be retyped. */
  phone: string;
}) {
  const [state, formAction, pending] = useActionState<StepState, FormData>(
    action,
    undefined,
  );
  const [method, setMethod] = useState<PaymentMethod>("mgurush");
  const manual = method === "bank_slip";

  if (state?.ok === true) {
    return (
      <Card>
        <CardHeader title="Application fee" />
        <CardBody className="space-y-4">
          <Callout tone="success" title="Fee recorded">
            {state.message}
          </Callout>
          <p className="text-[13px] text-muted">
            Keep the reference number. You will need it if you ever have to
            query the payment.
          </p>
        </CardBody>
        <CardFooter className="justify-end">
          <ButtonLink href={`/apply/${applicationId}/review`}>
            Continue to review and submit
          </ButtonLink>
        </CardFooter>
      </Card>
    );
  }

  return (
    <form action={formAction}>
      {state?.ok === false && state.message ? (
        <Callout tone="error" className="mb-5">
          {state.message}
        </Callout>
      ) : null}

      <Card>
        <CardHeader
          title="Application fee"
          description={`${ssp(feeSSP)}, charged once. It is not refundable and does not depend on the outcome.`}
        />
        <CardBody className="space-y-5">
          <div className="flex items-baseline justify-between rounded-[--radius] border border-brand-200 bg-brand-50 px-4 py-3">
            <span className="text-[13.5px] font-medium text-brand-900">
              Amount due
            </span>
            <span className="nums text-xl font-semibold text-brand-800">
              {ssp(feeSSP)}
            </span>
          </div>

          <fieldset>
            <legend className="mb-2 text-[13px] font-medium text-ink-soft">
              How are you paying?
            </legend>
            <div className="space-y-2">
              {PAYMENT_METHODS.map((m) => (
                <ChoiceRow
                  key={m.id}
                  checked={method === m.id}
                  label={m.name}
                  description={m.detail}
                >
                  <input
                    type="radio"
                    name="method"
                    value={m.id}
                    checked={method === m.id}
                    onChange={() => setMethod(m.id)}
                    className="h-4 w-4 accent-[--brand-700]"
                  />
                </ChoiceRow>
              ))}
            </div>
          </fieldset>

          {manual ? (
            <Field
              label="Deposit slip number"
              name="slip"
              required
              hint="Deposit at any branch to the university's account, then enter the slip number here. You can submit straight away; the bursary confirms within two working days."
            >
              <Input
                id="slip"
                name="slip"
                autoCapitalize="characters"
                spellCheck={false}
                placeholder="IVB-0092447"
                required
              />
            </Field>
          ) : (
            <Field
              label="Mobile money number"
              name="phone"
              required
              hint="A prompt is sent to this number. Enter your PIN on the handset to approve."
            >
              <Input
                id="phone"
                name="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                defaultValue={phone}
                placeholder="0920 123 456"
                required
              />
            </Field>
          )}

          <Callout tone="warning" title="Never pay anyone for a place">
            The only payment is this fee, made to the university&apos;s own
            account.
            No member of staff, agent or middleman can secure you admission.
          </Callout>
        </CardBody>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={pending}>
            {pending
              ? "Sending…"
              : manual
                ? "Record deposit slip"
                : `Pay ${ssp(feeSSP)}`}
          </Button>
        </CardFooter>
      </Card>
    </form>
  );
}
