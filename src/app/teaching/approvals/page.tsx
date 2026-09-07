import type { Metadata } from "next";
import { redirect } from "next/navigation";
import Link from "next/link";
import { Check, Stamp, Undo2 } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/empty";
import { Input } from "@/components/ui/field";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings, listPendingApprovals } from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import { shortDate } from "@/lib/format";
import { decideApproval } from "./actions";

export const metadata: Metadata = { title: "Results approvals" };

export default async function ApprovalsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "approve_results", settings)) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include approving results. Ask a
        super administrator to grant it on the Roles &amp; permissions page.
      </Callout>
    );
  }

  const pending = await listPendingApprovals();

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-[20px] font-semibold tracking-tight text-ink">
          Results awaiting sign-off
        </h1>
        <p className="mt-1 text-[13px] leading-relaxed text-muted">
          Approving publishes a class&apos;s marks to students. Returning sends
          them back to the lecturer with a note and publishes nothing.
        </p>
      </div>

      {error ? (
        <Callout tone="error" title="That did not go through">
          {error}
        </Callout>
      ) : null}

      {pending.length === 0 ? (
        <Card>
          <CardBody>
            <EmptyState icon={Check} title="Nothing waiting">
              No lecturer has submitted a class for approval. Marks appear here
              the moment they do.
            </EmptyState>
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-4">
          {pending.map(({ submission, course, submittedBy, marked, registered }) => {
            const ownSubmission = submission.submittedBy === staff.id;
            return (
              <Card key={course.id}>
                <CardHeader
                  icon={Stamp}
                  title={`${course.code} — ${course.title}`}
                  description={`Year ${course.year}, Semester ${course.semester} · ${course.creditHours} credit hours`}
                  action={<Badge tone="gold">Awaiting sign-off</Badge>}
                />
                <CardBody className="space-y-4">
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                    <div>
                      <dt className="text-[12px] text-muted">Submitted by</dt>
                      <dd className="mt-0.5 text-[13.5px] font-medium text-ink">
                        {submittedBy?.name ?? "Unknown"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[12px] text-muted">Submitted</dt>
                      <dd className="nums mt-0.5 text-[13.5px] font-medium text-ink">
                        {submission.submittedAt ? shortDate(submission.submittedAt) : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[12px] text-muted">Roster marked</dt>
                      <dd className="nums mt-0.5 text-[13.5px] font-medium text-ink">
                        {marked} of {registered}
                      </dd>
                    </div>
                  </dl>

                  <p className="text-[12.5px] text-muted">
                    <Link
                      href={`/teaching/${course.id}`}
                      className="font-medium text-brand-700 underline decoration-brand-300 underline-offset-2 hover:decoration-brand-700"
                    >
                      Review the roster and every mark
                    </Link>{" "}
                    before deciding.
                  </p>

                  {ownSubmission ? (
                    <Callout tone="warning" title="You submitted these">
                      Sign-off has to be a second pair of eyes, so this one has
                      to go to another head of department.
                    </Callout>
                  ) : (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <form action={decideApproval} className="flex flex-col gap-2">
                        <input type="hidden" name="courseId" value={course.id} />
                        <input type="hidden" name="outcome" value="approved" />
                        <button
                          type="submit"
                          className="inline-flex items-center justify-center gap-1.5 rounded border border-green-600 bg-green-600 px-3 py-2 text-[13px] font-medium text-white transition-colors hover:bg-green-700 hover:border-green-700"
                        >
                          <Check className="h-4 w-4" aria-hidden />
                          Approve and publish
                        </button>
                      </form>

                      <form action={decideApproval} className="flex flex-col gap-2">
                        <input type="hidden" name="courseId" value={course.id} />
                        <input type="hidden" name="outcome" value="returned" />
                        <Input
                          name="note"
                          placeholder="What needs correcting?"
                          maxLength={160}
                          aria-label={`Reason for returning ${course.code}`}
                        />
                        <button
                          type="submit"
                          className="inline-flex items-center justify-center gap-1.5 rounded border border-line-strong bg-surface px-3 py-2 text-[13px] font-medium text-ink-soft transition-colors hover:border-gold-500 hover:bg-gold-100 hover:text-gold-700"
                        >
                          <Undo2 className="h-4 w-4" aria-hidden />
                          Send back
                        </button>
                      </form>
                    </div>
                  )}
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
