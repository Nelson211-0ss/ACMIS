import { Lock } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty";

/**
 * Shown in place of a step's form once the application has been submitted.
 * Edits are refused server-side too — see `requireDraft` in ./actions.ts.
 */
export function ReadOnlyNotice({ applicationId }: { applicationId: string }) {
  return (
    <Card>
      <EmptyState
        icon={Lock}
        title="This application has been submitted"
        action={
          <ButtonLink href={`/apply/${applicationId}/review`} size="sm">
            View what you submitted
          </ButtonLink>
        }
      >
        Submitted applications cannot be edited. If something is wrong, call the
        admissions office and quote your reference number.
      </EmptyState>
    </Card>
  );
}
