"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { Callout } from "@/components/ui/callout";
import type { SignInState } from "./actions";

export function SignInForm({
  action,
  className,
}: {
  action: (prev: SignInState, formData: FormData) => Promise<SignInState>;
  className?: string;
}) {
  const [state, formAction, pending] = useActionState<SignInState, FormData>(
    action,
    undefined,
  );

  return (
    <form action={formAction} className={className}>
      {state?.error ? (
        <Callout tone="error" className="mb-4">
          {state.error}
        </Callout>
      ) : null}

      <div className="space-y-4">
        <Field label="Email address or student number" name="email" required>
          <Input
            id="email"
            name="email"
            type="text"
            inputMode="email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="achol.majok@student.example.ss"
            required
          />
        </Field>

        <Field label="Password" name="password" required>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
          />
        </Field>
      </div>

      <Button type="submit" block size="lg" className="mt-5" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
