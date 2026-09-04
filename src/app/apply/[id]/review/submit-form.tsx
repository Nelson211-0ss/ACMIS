"use client";

import { useActionState, useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import type { SubmitState } from "../../actions";

/**
 * Final submit.
 *
 * The declaration checkbox is a real gate, not decoration: submitting false
 * SSCSE marks is grounds for having an admission revoked, and the applicant
 * should have to say so deliberately.
 */
export function SubmitForm({
  action,
  applicationId,
  blocking,
}: {
  action: (prev: SubmitState, formData: FormData) => Promise<SubmitState>;
  applicationId: string;
  /** Section names that are still incomplete. Empty means ready. */
  blocking: string[];
}) {
  const [state, formAction, pending] = useActionState<SubmitState, FormData>(
    action,
    undefined,
  );
  const [declared, setDeclared] = useState(false);

  const ready = blocking.length === 0;

  return (
    <form action={formAction} className="space-y-4">
      <input type="hidden" name="id" value={applicationId} />

      {state?.error ? <Callout tone="error">{state.error}</Callout> : null}

      {!ready ? (
        <Callout tone="warning" title="Not ready to submit">
          Finish these sections first: {blocking.join(", ")}.
        </Callout>
      ) : null}

      <label className="flex cursor-pointer items-start gap-3 rounded-[--radius] border border-line-strong bg-surface px-3.5 py-3">
        <input
          type="checkbox"
          checked={declared}
          onChange={(e) => setDeclared(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 accent-[--brand-700]"
        />
        <span className="text-[13px] leading-snug text-ink-soft">
          I declare that the information in this application is true and
          complete, and that the documents I have uploaded are genuine. I
          understand that false information will cause my application to be
          rejected, or any admission granted to be withdrawn.
        </span>
      </label>

      <Button type="submit" size="lg" block disabled={pending || !ready || !declared}>
        <Send className="h-4 w-4" aria-hidden />
        {pending ? "Submitting…" : "Submit my application"}
      </Button>

      <p className="text-center text-[12px] text-muted">
        Once submitted, your application cannot be edited.
      </p>
    </form>
  );
}
