import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CalendarClock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { ApplicationStatusBadge, Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { Progress } from "@/components/ui/progress";
import { EmptyState } from "@/components/ui/empty";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { currentSession } from "@/lib/auth";
import { getApplicationsFor, getSystemSettings, listOpenSchemes } from "@/lib/data/repo";
import { competitiveness, programmesByFaculty } from "@/lib/data/reference";
import { institution } from "@/lib/institution";
import { progressPercent } from "@/lib/application";
import { shortDate, ssp } from "@/lib/format";
import { continueApplication, startApplication } from "./actions";
import { SchemeCard } from "./scheme-card";

export const metadata: Metadata = { title: "Apply for admission" };

const COMPETITIVENESS_LABEL = {
  high: { text: "Very competitive", tone: "red" as const },
  moderate: { text: "Competitive", tone: "gold" as const },
  open: { text: "Places usually available", tone: "green" as const },
};

export default async function ApplyPage() {
  const session = await currentSession();
  const [applications, settings, openSchemes] = await Promise.all([
    session ? getApplicationsFor(session.subjectId) : Promise.resolve([]),
    getSystemSettings(),
    listOpenSchemes(),
  ]);

  // Two independent switches: a super admin can pause admissions site-wide,
  // and separately, the admissions office opens and closes each scheme on its
  // own schedule — either one closing the door is enough.
  const closed = !settings.applicationsOpen;
  const drafts = applications.filter((a) => a.status === "draft");
  const submitted = applications.filter((a) => a.status !== "draft");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[24px] font-semibold tracking-tight text-ink">
          Apply for admission
        </h1>
        <p className="mt-1.5 text-[14px] text-muted">
          {closed
            ? "New applications are paused by the admissions office."
            : openSchemes.length > 0
              ? `${openSchemes.length} admission scheme${openSchemes.length === 1 ? "" : "s"} currently open`
              : "No admission scheme is open right now."}
        </p>
      </div>

      {closed ? (
        <Callout tone="warning" title="Applications are closed">
          New applications have been paused by the admissions office.
          Applications already submitted are still being processed.
        </Callout>
      ) : null}

      {/* Existing applications */}
      {applications.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-[15px] font-semibold text-ink">My applications</h2>

          {[...drafts, ...submitted].map((app) => {
            const percent = progressPercent(app);
            return (
              <Card key={app.id}>
                <CardBody>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="nums text-[13px] font-semibold text-brand-700">
                        {app.reference}
                      </p>
                      <p className="mt-0.5 text-[13.5px] text-ink">
                        {app.personal.firstName || app.personal.lastName
                          ? `${app.personal.firstName} ${app.personal.lastName}`.trim()
                          : "Unnamed draft"}
                      </p>
                      <p className="mt-0.5 text-[12.5px] text-muted">
                        {app.submittedAt
                          ? `Submitted ${shortDate(app.submittedAt)}`
                          : `Started ${shortDate(app.createdAt)}`}
                      </p>
                    </div>
                    <ApplicationStatusBadge status={app.status} />
                  </div>

                  {app.status === "draft" ? (
                    <Progress
                      className="mt-4"
                      value={percent}
                      label="Application complete"
                    />
                  ) : null}

                  {app.decision ? (
                    <Callout
                      tone={app.status === "admitted" ? "success" : "info"}
                      className="mt-4"
                      title={
                        app.status === "admitted" ? "You have been offered a place" : "Decision"
                      }
                    >
                      {app.decision.message}
                    </Callout>
                  ) : null}
                </CardBody>
                <CardFooter>
                  {app.status === "draft" ? (
                    <form action={continueApplication}>
                      <input type="hidden" name="id" value={app.id} />
                      <Button type="submit" size="sm">
                        Continue application
                        <ArrowRight className="h-4 w-4" aria-hidden />
                      </Button>
                    </form>
                  ) : (
                    <Link
                      href={`/apply/${app.id}/review`}
                      className="text-[13px] font-medium text-brand-700 underline decoration-brand-300 underline-offset-2 hover:decoration-brand-700"
                    >
                      View submitted application
                    </Link>
                  )}
                </CardFooter>
              </Card>
            );
          })}
        </section>
      ) : null}

      {/* Open admission schemes */}
      {!closed ? (
        <section className="space-y-3">
          <div>
            <h2 className="text-[15px] font-semibold text-ink">
              {applications.length > 0 ? "Start another application" : "Choose a scheme to apply under"}
            </h2>
            {openSchemes.length > 0 ? (
              <p className="mt-1 text-[13px] text-muted">
                Each scheme has its own programmes on offer, fee and closing
                date, set by the admissions office.
              </p>
            ) : null}
          </div>

          {openSchemes.length === 0 ? (
            <Card>
              <CardBody>
                <EmptyState icon={CalendarClock} title="No admission scheme is open">
                  The admissions office has not published a scheme to apply
                  under right now. Check back soon, or call{" "}
                  {institution.supportPhone} for the next intake date.
                </EmptyState>
              </CardBody>
            </Card>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {openSchemes.map((scheme) => (
                <SchemeCard
                  key={scheme.id}
                  scheme={scheme}
                  action={startApplication.bind(null, scheme.id)}
                />
              ))}
            </div>
          )}

          {applications.length === 0 && openSchemes.length > 0 ? (
            <Card>
              <CardBody>
                <p className="mb-3 text-[13px] font-semibold text-ink">
                  What to have ready
                </p>
                <ol className="space-y-2.5 text-[13px] text-muted">
                  <Step n="1">
                    Your personal details and a parent or guardian&apos;s phone
                    number.
                  </Step>
                  <Step n="2">
                    Your SSCSE index number and the mark for each subject you sat.
                  </Step>
                  <Step n="3">Up to three programmes, ranked in order of preference.</Step>
                  <Step n="4">
                    Photographs or scans of your certificate, marksheet and a
                    passport photo.
                  </Step>
                  <Step n="5">The application fee.</Step>
                </ol>
              </CardBody>
            </Card>
          ) : null}
        </section>
      ) : null}

      {/* Entry requirements */}
      <section className="space-y-3">
        <div>
          <h2 className="text-[15px] font-semibold text-ink">Entry requirements</h2>
          <p className="mt-1 text-[13px] text-muted">
            Minimum aggregate is the average of your best six SSCSE subjects.
            Meeting it makes you eligible; it does not guarantee a place.
          </p>
        </div>

        {programmesByFaculty().map(({ faculty, programmes }) => (
          <Card key={faculty.id}>
            <CardHeader title={faculty.name} />
            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>Programme</Th>
                    <Th>Required subjects</Th>
                    <Th className="text-right">Min. aggregate</Th>
                    <Th className="text-right">Places</Th>
                  </tr>
                </thead>
                <tbody>
                  {programmes.map((p) => {
                    const c = COMPETITIVENESS_LABEL[competitiveness(p)];
                    return (
                      <Tr key={p.id}>
                        <Td>
                          <span className="block text-[13.5px] font-medium leading-snug text-ink">
                            {p.name}
                          </span>
                          <span className="nums mt-0.5 block text-[12px] text-muted">
                            {p.code} · {p.durationYears} years ·{" "}
                            {ssp(p.tuitionPerSemesterSSP)}/semester
                          </span>
                        </Td>
                        <Td className="text-[12.5px] text-muted">
                          {p.requiredSubjects.join(", ")}
                        </Td>
                        <Td className="nums text-right font-semibold">
                          {p.minimumAggregate}
                        </Td>
                        <Td className="text-right">
                          <span className="nums block font-medium">{p.intake}</span>
                          <Badge tone={c.tone} className="mt-1">
                            {c.text}
                          </Badge>
                        </Td>
                      </Tr>
                    );
                  })}
                </tbody>
              </Table>
            </TableWrap>
          </Card>
        ))}
      </section>

      <Callout tone="info" title="Beware of fraud">
        <p>
          No one at {institution.name} will ask you to pay for admission
          outside this portal. The only fee is the one shown on the scheme you
          apply under, paid to the university&apos;s own m-GURUSH, Nilepay or
          bank account. If someone asks for money to secure you a place,
          report it to the admissions office on {institution.supportPhone}.
        </p>
      </Callout>
    </div>
  );
}

function Step({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-2.5">
      <span className="nums flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line-strong bg-surface text-[11px] font-semibold text-ink-soft">
        {n}
      </span>
      <span className="leading-snug">{children}</span>
    </li>
  );
}
