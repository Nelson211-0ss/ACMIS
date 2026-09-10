import { FileQuestion } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty";
import { institution } from "@/lib/institution";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto max-w-4xl px-4 py-3.5 sm:px-6">
          <Wordmark />
        </div>
      </header>
      <main
        id="main"
        className="mx-auto flex w-full max-w-md flex-1 items-center px-4 py-10"
      >
        <Card className="w-full">
          <EmptyState
            icon={FileQuestion}
            title="That page does not exist"
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <ButtonLink href="/" size="sm">
                  Go to the portal home
                </ButtonLink>
                <ButtonLink href="/apply" variant="secondary" size="sm">
                  My applications
                </ButtonLink>
              </div>
            }
          >
            The link may be out of date, or the application reference may be
            wrong. If you were sent here from an SMS, call the admissions office
            on {institution.supportPhone}.
          </EmptyState>
        </Card>
      </main>
    </div>
  );
}
