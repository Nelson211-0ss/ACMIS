"use client";

import Link from "next/link";
import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, Input } from "@/components/ui/field";
import { requestPasswordReset, type ForgotState } from "../actions";

export function ForgotPasswordForm() {
  const [state, formAction, pending] = useActionState<ForgotState, FormData>(
    requestPasswordReset,
    undefined,
  );

  if (state?.sent) {
    return (
      <div className="mt-6">
        <Callout tone="success" title="Check your email">
          If an account exists for that address, a link to set a new password
          is on its way. It expires in an hour.
        </Callout>

        {state.devLink ? (
          <Callout tone="warning" className="mt-4" title="Development build">
            <p>
              No mail service is connected, so the link is shown here instead of
              being sent. This does not happen in production.
            </p>
            <Link
              href={state.devLink}
              className="mt-2 inline-block font-semibold underline underline-offset-2"
            >
              Open the reset link
            </Link>
          </Callout>
        ) : null}
      </div>
    );
  }

  return (
    <form action={formAction} className="mt-6">
      {state?.error ? (
        <Callout tone="error" className="mb-4">
          {state.error}
        </Callout>
      ) : null}

      <Field label="Email address" name="email" required>
        <Input
          id="email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="you@example.ss"
          required
        />
      </Field>

      <Button type="submit" block size="lg" className="mt-5" disabled={pending}>
        {pending ? "Sending…" : "Send reset link"}
      </Button>
    </form>
  );
}
