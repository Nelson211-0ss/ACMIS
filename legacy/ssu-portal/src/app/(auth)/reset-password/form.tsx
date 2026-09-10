"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, Input } from "@/components/ui/field";
import { resetPassword, type ResetState } from "../actions";

export function ResetPasswordForm({ token }: { token: string }) {
  const [state, formAction, pending] = useActionState<ResetState, FormData>(
    resetPassword,
    undefined,
  );

  return (
    <form action={formAction} className="mt-6">
      {state?.error ? (
        <Callout tone="error" className="mb-4">
          {state.error}
        </Callout>
      ) : null}

      {/* The token rides in the form rather than being re-read from the URL
          on submit, so the action never has to trust the referrer. */}
      <input type="hidden" name="token" value={token} />

      <div className="space-y-4">
        <Field
          label="New password"
          name="password"
          required
          hint="At least 10 characters."
        >
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            minLength={10}
            required
          />
        </Field>

        <Field label="Confirm new password" name="confirm" required>
          <Input
            id="confirm"
            name="confirm"
            type="password"
            autoComplete="new-password"
            minLength={10}
            required
          />
        </Field>
      </div>

      <Button type="submit" block size="lg" className="mt-5" disabled={pending}>
        {pending ? "Saving…" : "Set new password"}
      </Button>
    </form>
  );
}
