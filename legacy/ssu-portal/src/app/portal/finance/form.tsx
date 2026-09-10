"use client";

import { useActionState, useState } from "react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { ChoiceRow, Field, Input } from "@/components/ui/field";
import { PAYMENT_METHODS } from "@/lib/data/payments";
import type { PaymentMethod } from "@/lib/types";
import { ssp } from "@/lib/format";
import type { PayState } from "./actions";

/**
 * Payment form.
 *
 * The amount defaults to the full balance but stays editable, because part
 * payment is the norm — most families clear tuition across two or three
 * instalments over a semester.
 */
export function PayForm({
  action,
  balance,
  phone,
}: {
  action: (prev: PayState, formData: FormData) => Promise<PayState>;
  balance: number;
  /** Pre-filled from the student record; still editable. */
  phone: string;
}) {
  const [state, formAction, pending] = useActionState<PayState, FormData>(
    action,
    undefined,
  );
  const [method, setMethod] = useState<PaymentMethod>("mgurush");

  const manual = method === "bank_slip";

  return (
    <form action={formAction} className="space-y-4">
      {state?.ok === false ? (
        <Callout tone="error" title="Payment not recorded">
          {state.message}
        </Callout>
      ) : null}
      {state?.ok === true ? (
        <Callout tone="success" title="Payment recorded">
          {state.message}
        </Callout>
      ) : null}

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

      <Field
        label="Amount"
        name="amount"
        required
        hint={
          balance > 0
            ? `Full outstanding balance is ${ssp(balance)}. Part payment is accepted.`
            : "Your account is cleared. Any payment will sit as credit."
        }
      >
        <Input
          id="amount"
          name="amount"
          type="number"
          inputMode="numeric"
          min={1}
          step={1000}
          defaultValue={balance > 0 ? balance : ""}
          required
        />
      </Field>

      {manual ? (
        <Field
          label="Deposit slip number"
          name="slip"
          required
          hint="Printed on the receipt the bank teller gives you."
        >
          <Input
            id="slip"
            name="slip"
            type="text"
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
          hint="A prompt is sent here. Enter your PIN on the handset to approve."
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

      <Button type="submit" block size="lg" disabled={pending}>
        {pending
          ? "Sending…"
          : manual
            ? "Record deposit slip"
            : "Send payment request to my phone"}
      </Button>

      <p className="text-[12px] leading-snug text-muted">
        The university never asks for your mobile money PIN. Enter it only on
        your own handset, in response to the prompt from your provider.
      </p>
    </form>
  );
}
