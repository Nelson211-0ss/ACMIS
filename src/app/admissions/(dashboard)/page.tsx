import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, Clock, Hourglass, Inbox, XCircle } from "lucide-react";
import { Card, CardHeader, Stat } from "@/components/ui/card";
import { ApplicationStatusBadge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { getScheme, listApplicationsForReview } from "@/lib/data/repo";
import { programmeById } from "@/lib/data/reference";
import { shortDate } from "@/lib/format";
import type { ApplicationStatus } from "@/lib/types";
import { cn } from "@/lib/cn";

export const metadata: Metadata = { title: "Admissions queue" };

const FILTERS: Array<{ value: ApplicationStatus | "all"; label: string }> = [
  { value: "all", label: "All" },
  { value: "submitted", label: "Submitted" },
  { value: "under_review", label: "Under review" },
  { value: "interview", label: "Interview" },
  { value: "admitted", label: "Admitted" },
  { value: "waitlisted", label: "Waitlisted" },
  { value: "rejected", label: "Rejected" },
];

export default async function AdmissionsQueuePage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const applications = await listApplicationsForReview();

  const awaiting = applications.filter((a) =>
    ["submitted", "under_review", "interview"].includes(a.status),
  ).length;
  const admitted = applications.filter((a) => a.status === "admitted").length;
  const waitlisted = applications.filter((a) => a.status === "waitlisted").length;
  const rejected = applications.filter((a) => a.status === "rejected").length;

  const filtered = status && status !== "all"
    ? applications.filter((a) => a.status === status)
    : applications;

  const rows = await Promise.all(
    filtered.map(async (a) => {
      const scheme = a.schemeId ? await getScheme(a.schemeId) : null;
      const firstChoice = [...a.choices].sort((x, y) => x.rank - y.rank)[0];
      const programme = firstChoice ? programmeById(firstChoice.programmeId) : undefined;
      return { application: a, scheme, programme };
    }),
  );

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Admissions queue
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Every submitted application, across every scheme.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Clock} label="Awaiting decision" value={awaiting} />
        <Stat icon={CheckCircle2} label="Admitted" value={admitted} />
        <Stat icon={Hourglass} label="Waitlisted" value={waitlisted} />
        <Stat icon={XCircle} label="Rejected" value={rejected} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => {
          const active = (status ?? "all") === f.value;
          return (
            <Link
              key={f.value}
              href={f.value === "all" ? "/admissions" : `/admissions?status=${f.value}`}
              className={cn(
                "rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition-colors",
                active
                  ? "border-brand-500 bg-brand-50 text-brand-800"
                  : "border-line-strong bg-surface text-ink-soft hover:border-brand-300",
              )}
            >
              {f.label}
            </Link>
          );
        })}
      </div>

      <Card>
        <CardHeader icon={Inbox} title="Applications" description={`${filtered.length} shown`} />
        {rows.length === 0 ? (
          <EmptyState icon={Inbox} title="Nothing here">
            No applications match this filter.
          </EmptyState>
        ) : (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Reference</Th>
                  <Th>Applicant</Th>
                  <Th>Scheme</Th>
                  <Th>First choice</Th>
                  <Th>Status</Th>
                  <Th>Submitted</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {rows.map(({ application: a, scheme, programme }) => (
                  <Tr key={a.id}>
                    <Td className="nums font-medium text-brand-700">{a.reference}</Td>
                    <Td>
                      {[a.personal.firstName, a.personal.lastName].filter(Boolean).join(" ") ||
                        "Unnamed"}
                    </Td>
                    <Td className="text-[12.5px] text-muted">{scheme?.name ?? "—"}</Td>
                    <Td className="text-[12.5px] text-muted">{programme?.name ?? "—"}</Td>
                    <Td>
                      <ApplicationStatusBadge status={a.status} />
                    </Td>
                    <Td className="nums text-muted">
                      {a.submittedAt ? shortDate(a.submittedAt) : "—"}
                    </Td>
                    <Td>
                      <Link
                        href={`/admissions/${a.id}`}
                        className="text-[12.5px] font-medium text-brand-700 underline decoration-brand-300 underline-offset-2 hover:decoration-brand-700"
                      >
                        Review
                      </Link>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        )}
      </Card>
    </div>
  );
}
