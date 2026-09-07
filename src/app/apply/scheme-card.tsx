import { ArrowRight, CalendarClock, GraduationCap, Layers, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card, CardBody, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AdmissionScheme } from "@/lib/types";
import { relativeDays, shortDate, ssp } from "@/lib/format";

/**
 * One published admission scheme, as a prospective applicant sees it.
 *
 * Led by an icon chip rather than an accent bar down the edge: the four facts
 * that decide whether to apply — how many programmes, what it costs, when it
 * shuts, when you would start — each get their own labelled cell instead of
 * being a run of rows to read top to bottom.
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
    <Card className="flex h-full flex-col">
      <CardBody className="flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-700">
              <GraduationCap className="h-5 w-5 text-white" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-[15px] font-semibold leading-snug text-ink">
                {scheme.name}
              </p>
              <p className="nums mt-0.5 text-[11.5px] font-medium uppercase tracking-wide text-faint">
                {scheme.code}
              </p>
            </div>
          </div>
          <Badge tone={closesSoon ? "red" : "gold"} className="shrink-0">
            Closes {relativeDays(scheme.closesAt)}
          </Badge>
        </div>

        <p className="mt-3 text-[13px] leading-relaxed text-muted">
          {scheme.description}
        </p>

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-line pt-4">
          <Fact
            icon={Layers}
            label="Programmes"
            value={String(scheme.programmeIds.length)}
          />
          <Fact icon={Wallet} label="Fee" value={ssp(scheme.applicationFeeSSP)} />
          <Fact
            icon={CalendarClock}
            label="Closing date"
            value={shortDate(scheme.closesAt)}
          />
          <Fact
            icon={GraduationCap}
            label="Semester begins"
            value={shortDate(scheme.semesterStarts)}
          />
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

function Fact({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1.5 text-[11.5px] text-muted">
        <Icon className="h-3.5 w-3.5 shrink-0 text-faint" aria-hidden />
        {label}
      </dt>
      <dd className="nums mt-0.5 truncate text-[13.5px] font-semibold text-ink">
        {value}
      </dd>
    </div>
  );
}
