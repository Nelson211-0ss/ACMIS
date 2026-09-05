import { ArrowRight } from "lucide-react";
import { Card, CardBody, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AdmissionScheme } from "@/lib/types";
import { relativeDays, shortDate, ssp } from "@/lib/format";

/**
 * One published admission scheme, as a prospective applicant sees it.
 *
 * The gold accent bar matches the same "flat fill, no gradient" language used
 * for Stat tiles elsewhere — a scheme is exactly that: one figure (its
 * closing date) with supporting detail, not a generic content card.
 */
export function SchemeCard({
  scheme,
  action,
}: {
  scheme: AdmissionScheme;
  action: () => Promise<void>;
}) {
  const closesSoon = new Date(scheme.closesAt).getTime() - Date.now() < 7 * 86_400_000;

  return (
    <Card className="relative flex h-full flex-col overflow-hidden">
      <span className="absolute inset-y-0 left-0 w-[3px] bg-gold-500" aria-hidden />
      <CardBody className="flex-1 pl-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[15px] font-semibold leading-snug text-ink">{scheme.name}</p>
            <p className="nums mt-0.5 text-[11.5px] font-medium uppercase tracking-wide text-muted">
              {scheme.code}
            </p>
          </div>
          <Badge tone={closesSoon ? "red" : "gold"} className="shrink-0">
            Closes {relativeDays(scheme.closesAt)}
          </Badge>
        </div>

        <p className="mt-2.5 text-[13px] leading-snug text-muted">{scheme.description}</p>

        <dl className="mt-3.5 space-y-1.5 border-t border-line pt-3 text-[12.5px]">
          <Row label="Programmes offered" value={String(scheme.programmeIds.length)} />
          <Row label="Application fee" value={ssp(scheme.applicationFeeSSP)} />
          <Row label="Closing date" value={shortDate(scheme.closesAt)} />
          <Row label="Semester begins" value={shortDate(scheme.semesterStarts)} />
        </dl>
      </CardBody>
      <CardFooter>
        <form action={action}>
          <Button type="submit" size="sm">
            Apply under this scheme
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        </form>
      </CardFooter>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="nums font-medium text-ink-soft">{value}</dd>
    </div>
  );
}
