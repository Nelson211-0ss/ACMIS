import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  BadgeCheck,
  BookOpen,
  FileText,
  GraduationCap,
  User,
  Wallet,
} from "lucide-react";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import {
  ApplicationStatusBadge,
  Badge,
  PaymentStatusBadge,
} from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/field";
import { getApplication, getScheme } from "@/lib/data/repo";
import { programmeById } from "@/lib/data/reference";
import { aggregate, checkEligibility, REQUIRED_DOCUMENTS } from "@/lib/application";
import { displayPhone, shortDate, ssp } from "@/lib/format";
import { methodName } from "@/lib/data/payments";
import { changeDocumentStatus, saveDecision } from "./actions";

export const metadata: Metadata = { title: "Review application" };

export default async function AdmissionsReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const application = await getApplication(id);
  if (!application) notFound();

  const scheme = application.schemeId ? await getScheme(application.schemeId) : null;
  const { personal, education, choices, documents, payment } = application;
  const agg = education.subjects.length > 0 ? aggregate(education.subjects) : null;
  const ranked = [...choices].sort((a, b) => a.rank - b.rank);

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-semibold tracking-tight text-ink">
            {[personal.firstName, personal.lastName].filter(Boolean).join(" ") || "Unnamed applicant"}
          </h1>
          <p className="mt-1 text-[13px] text-muted">
            <span className="nums">{application.reference}</span>
            {scheme ? ` · ${scheme.name}` : ""}
            {application.submittedAt ? ` · submitted ${shortDate(application.submittedAt)}` : ""}
          </p>
        </div>
        <ApplicationStatusBadge status={application.status} />
      </div>

      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-5">
        <div className="space-y-5">
          <Card>
            <CardHeader icon={User} title="Personal details" />
            <CardBody>
              <dl className="divide-y divide-line text-[13.5px]">
                <Row label="Date of birth" value={personal.dateOfBirth ? shortDate(personal.dateOfBirth) : "—"} />
                <Row label="Sex" value={personal.sex || "—"} />
                <Row label="Nationality" value={personal.nationality || "—"} />
                <Row
                  label="Origin"
                  value={personal.stateOfOrigin ? `${personal.county}, ${personal.stateOfOrigin}` : "—"}
                />
                <Row label="Mobile" value={personal.phone ? displayPhone(personal.phone) : "—"} />
                <Row label="Email" value={personal.email || "—"} />
                <Row label="National ID" value={personal.nationalId || "—"} />
                <Row
                  label="Guardian"
                  value={
                    personal.guardianName
                      ? `${personal.guardianName} · ${displayPhone(personal.guardianPhone)}`
                      : "—"
                  }
                />
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              icon={GraduationCap}
              title="Secondary education"
              action={agg !== null ? <Badge tone="brand">Aggregate {agg}</Badge> : null}
            />
            <CardBody>
              <dl className="mb-3 divide-y divide-line text-[13.5px]">
                <Row label="School" value={education.secondarySchool || "—"} />
                <Row label="Index number" value={education.indexNumber || "—"} />
                <Row
                  label="State / year"
                  value={
                    education.schoolState
                      ? `${education.schoolState}, ${education.yearCompleted}`
                      : "—"
                  }
                />
              </dl>
              {education.subjects.length > 0 ? (
                <ul className="grid grid-cols-2 gap-1.5 border-t border-line pt-3 sm:grid-cols-3">
                  {education.subjects.map((s) => (
                    <li key={s.subject} className="flex items-center justify-between gap-2 text-[12.5px]">
                      <span className="truncate text-muted">{s.subject}</span>
                      <span className="nums font-medium text-ink">{s.mark}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </CardBody>
          </Card>

          <Card>
            <CardHeader icon={BookOpen} title="Programme choices" />
            <ul className="divide-y divide-line">
              {ranked.map((choice) => {
                const programme = programmeById(choice.programmeId);
                if (!programme) return null;
                const eligibility =
                  education.subjects.length > 0 ? checkEligibility(programme, education.subjects) : null;
                return (
                  <li key={choice.rank} className="px-4 py-3.5 sm:px-5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="nums flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line-strong text-[11px] font-semibold text-ink-soft">
                        {choice.rank}
                      </span>
                      <span className="text-[13.5px] font-medium text-ink">{programme.name}</span>
                      <span className="nums text-[12px] text-muted">{programme.code}</span>
                      {eligibility ? (
                        <Badge tone={eligibility.eligible ? "green" : "gold"} className="ml-auto">
                          {eligibility.eligible ? "Meets requirement" : "Below requirement"}
                        </Badge>
                      ) : null}
                    </div>
                    {eligibility && !eligibility.eligible ? (
                      <ul className="mt-1.5 list-disc space-y-0.5 pl-6 text-[12px] text-muted">
                        {eligibility.reasons.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                );
              })}
              {ranked.length === 0 ? (
                <li className="px-4 py-3.5 text-[13px] text-muted sm:px-5">No choices recorded.</li>
              ) : null}
            </ul>
          </Card>

          <Card>
            <CardHeader icon={FileText} title="Documents" />
            <ul className="divide-y divide-line">
              {REQUIRED_DOCUMENTS.map((spec) => {
                const uploaded = documents.find((d) => d.kind === spec.kind);
                return (
                  <li key={spec.kind} className="flex items-center gap-3 px-4 py-3.5 sm:px-5">
                    <div className="min-w-0 flex-1">
                      <p className="text-[13.5px] font-medium text-ink">{spec.label}</p>
                      <p className="truncate text-[12px] text-muted">
                        {uploaded ? uploaded.fileName : spec.required ? "Not uploaded" : "Not provided"}
                      </p>
                    </div>
                    {uploaded ? (
                      <>
                        <Badge tone={uploaded.status === "verified" ? "green" : uploaded.status === "rejected" ? "red" : "gold"}>
                          {uploaded.status}
                        </Badge>
                        <form action={changeDocumentStatus.bind(null, application.id)} className="flex gap-1.5">
                          <input type="hidden" name="documentId" value={uploaded.id} />
                          <input type="hidden" name="status" value="verified" />
                          <button
                            type="submit"
                            disabled={uploaded.status === "verified"}
                            className="rounded border border-line-strong bg-surface px-2.5 py-1.5 text-[12px] font-medium text-ink-soft transition-colors hover:bg-sunken disabled:opacity-40"
                          >
                            Verify
                          </button>
                        </form>
                        <form action={changeDocumentStatus.bind(null, application.id)}>
                          <input type="hidden" name="documentId" value={uploaded.id} />
                          <input type="hidden" name="status" value="rejected" />
                          <button
                            type="submit"
                            disabled={uploaded.status === "rejected"}
                            className="rounded border border-line-strong bg-surface px-2.5 py-1.5 text-[12px] font-medium text-ink-soft transition-colors hover:bg-red-100 hover:text-red-700 disabled:opacity-40"
                          >
                            Reject
                          </button>
                        </form>
                      </>
                    ) : (
                      <Badge tone={spec.required ? "red" : "neutral"}>
                        {spec.required ? "missing" : "optional"}
                      </Badge>
                    )}
                  </li>
                );
              })}
            </ul>
          </Card>

          <Card>
            <CardHeader icon={Wallet} title="Application fee" action={payment ? <PaymentStatusBadge status={payment.status} /> : null} />
            <CardBody>
              {payment ? (
                <dl className="divide-y divide-line text-[13.5px]">
                  <Row label="Amount" value={ssp(payment.amountSSP)} />
                  <Row label="Method" value={methodName(payment.method)} />
                  <Row label="Reference" value={payment.reference ?? "—"} />
                  <Row label="Date" value={shortDate(payment.createdAt)} />
                </dl>
              ) : (
                <p className="text-[13px] text-muted">No payment recorded yet.</p>
              )}
            </CardBody>
          </Card>
        </div>

        <div className="mt-5 lg:sticky lg:top-20 lg:mt-0 lg:self-start">
          <form action={saveDecision.bind(null, application.id)}>
            <Card>
              <CardHeader icon={BadgeCheck} title="Decision" description="Visible to the applicant as soon as you save." />
              <CardBody className="space-y-4">
                <Field label="Status" name="status" required>
                  <Select id="status" name="status" defaultValue={application.status}>
                    <option value="submitted">Submitted</option>
                    <option value="under_review">Under review</option>
                    <option value="interview">Interview scheduled</option>
                    <option value="admitted">Admitted</option>
                    <option value="waitlisted">Waitlisted</option>
                    <option value="rejected">Not offered</option>
                  </Select>
                </Field>

                {ranked.length > 0 ? (
                  <Field label="Offer programme" name="programmeId" hint="Only meaningful if admitting">
                    <Select id="programmeId" name="programmeId" defaultValue={application.decision?.programmeId ?? ranked[0].programmeId}>
                      {ranked.map((c) => {
                        const p = programmeById(c.programmeId);
                        return p ? (
                          <option key={c.programmeId} value={c.programmeId}>
                            {p.name}
                          </option>
                        ) : null;
                      })}
                    </Select>
                  </Field>
                ) : null}

                <Field label="Message to applicant" name="message" hint="Shown on their application status page">
                  <Textarea
                    id="message"
                    name="message"
                    defaultValue={application.decision?.message}
                    placeholder="e.g. Congratulations — you have been offered a place in…"
                  />
                </Field>
              </CardBody>
              <CardFooter>
                <Button type="submit" size="sm" block>
                  Save decision
                </Button>
              </CardFooter>
            </Card>
          </form>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 first:pt-0 last:pb-0">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="text-right font-medium text-ink">{value}</dd>
    </div>
  );
}
