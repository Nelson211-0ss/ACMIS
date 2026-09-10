"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, Input } from "@/components/ui/field";
import { register, type RegisterState } from "../actions";

export function RegisterForm() {
  const [state, formAction, pending] = useActionState<RegisterState, FormData>(
    register,
    undefined,
  );

  return (
    <form action={formAction} className="mt-6">
      {state?.error ? (
        <Callout tone="error" className="mb-4">
          {state.error}
        </Callout>
      ) : null}

      <div className="space-y-4">
        <Field
          label="Email address"
          name="email"
          required
          hint="Use an address you will still have after you leave school — decisions are sent here."
        >
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

        <Field
          label="Password"
          name="password"
          required
          hint="At least 10 characters. A short phrase you will remember beats a short word you will not."
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

        <Field label="Confirm password" name="confirm" required>
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
        {pending ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
