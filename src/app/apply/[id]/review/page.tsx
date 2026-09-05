import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  BookOpen,
  CheckCircle2,
  FileText,
  GraduationCap,
  type LucideIcon,
  Pencil,
  Send,
  User,
  Wallet,
} from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ApplicationStatusBadge, Badge, PaymentStatusBadge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { ButtonLink } from "@/components/ui/button";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { getApplication, getScheme } from "@/lib/data/repo";
import { programmeById } from "@/lib/data/reference";
import { methodName } from "@/lib/data/payments";
import { aggregate, canSubmit, REQUIRED_DOCUMENTS } from "@/lib/application";
import { admissionCycle, institution } from "@/lib/institution";
import { displayPhone, shortDate, ssp } from "@/lib/format";
import { submitApplication } from "../../actions";
import { SubmitForm } from "./submit-form";

export const metadata: Metadata = { title: "Review and submit" };

export default async function ReviewStep({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ submitted?: string }>;
}) {
  const { id } = await params;
  const { submitted } = await searchParams;
  const application = await getApplication(id);
  if (!application) notFound();

  const scheme = application.schemeId ? await getScheme(application.schemeId) : null;
  const resultsBy = scheme?.resultsBy ?? admissionCycle.resultsBy;
  const feeSSP = scheme?.applicationFeeSSP ?? institution.applicationFeeSSP;

  const { personal, education, choices, documents, payment } = application;
  const isDraft = application.status === "draft";
  const { blocking } = canSubmit(application);
  const agg = education.subjects.length > 0 ? aggregate(education.subjects) : null;

  return (
    <div className="space-y-5">
      {submitted === "1" ? (
        <Callout tone="success" title="Your application has been submitted">
          <p>
            Keep your reference{" "}
            <span className="nums font-semibold">{application.reference}</span>.
            A confirmation SMS has been sent to{" "}
            {personal.phone ? displayPhone(personal.phone) : "your number"}.
            Decisions for this cycle are published by{" "}
            {shortDate(resultsBy)}.
          </p>
        </Callout>
      ) : null}

      {!isDraft && submitted !== "1" ? (
        <Card>
          <CardBody className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-green-600" aria-hidden />
            <div>
              <p className="text-[14px] font-semibold text-ink">
                Submitted {application.submittedAt ? shortDate(application.submittedAt) : ""}
              </p>
              <p className="mt-1 text-[13px] text-muted">
                Decisions are published by {shortDate(resultsBy)}.
                You will be notified by SMS on{" "}
                {personal.phone ? displayPhone(personal.phone) : "your number"}.
              </p>
            </div>
            <div className="ml-auto shrink-0">
              <ApplicationStatusBadge status={application.status} />
            </div>
          </CardBody>
        </Card>
      ) : null}

      {application.decision ? (
        <Callout
          tone={application.status === "admitted" ? "success" : "info"}
          title={
            application.status === "admitted"
              ? "You have been offered a place"
              : "Admissions decision"
          }
        >
          {application.decision.message}
        </Callout>
      ) : null}

      {/* Personal */}
      <Section icon={User} title="Personal details" editHref={isDraft ? `/apply/${id}/personal` : undefined}>
        <dl className="divide-y divide-line text-[13.5px]">
          <Row
            label="Full name"
            value={[personal.firstName, personal.middleName, personal.lastName]
              .filter(Boolean)
              .join(" ")}
          />
          <Row label="Date of birth" value={personal.dateOfBirth ? shortDate(personal.dateOfBirth) : "—"} />
          <Row label="Sex" value={personal.sex || "—"} />
          <Row label="Nationality" value={personal.nationality || "—"} />
          <Row
            label="Origin"
            value={
              personal.stateOfOrigin
                ? `${personal.county}, ${personal.stateOfOrigin}`
                : "—"
            }
          />
          <Row label="Mobile" value={personal.phone ? displayPhone(personal.phone) : "—"} />
          <Row label="Email" value={personal.email || "—"} />
          <Row label="National ID" value={personal.nationalId || "Not provided"} />
          <Row
            label="Guardian"
            value={
              personal.guardianName
                ? `${personal.guardianName} · ${displayPhone(personal.guardianPhone)}`
                : "—"
            }
          />
        </dl>
      </Section>

      {/* Education */}
      <Section
        icon={GraduationCap}
        title="Secondary results"
        editHref={isDraft ? `/apply/${id}/education` : undefined}
        action={
          agg === null ? undefined : <Badge tone="brand">Aggregate {agg}</Badge>
        }
      >
        <dl className="divide-y divide-line pb-4 text-[13.5px]">
          <Row label="School" value={education.secondarySchool || "—"} />
          <Row label="State" value={education.schoolState || "—"} />
          <Row label="Index number" value={education.indexNumber || "—"} />
          <Row label="Year completed" value={education.yearCompleted || "—"} />
        </dl>
        {education.subjects.length > 0 ? (
          <TableWrap className="-mx-4 sm:-mx-5">
            <Table>
              <thead>
                <tr>
                  <Th>Subject</Th>
                  <Th className="text-right">Mark / 100</Th>
                </tr>
              </thead>
              <tbody>
                {[...education.subjects]
                  .sort((a, b) => b.mark - a.mark)
                  .map((s) => (
                    <Tr key={s.subject}>
                      <Td>{s.subject}</Td>
                      <Td className="nums text-right font-medium">{s.mark}</Td>
                    </Tr>
                  ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <p className="text-[13px] text-muted">No subjects entered.</p>
        )}
      </Section>

      {/* Choices */}
      <Section
        icon={BookOpen}
        title="Programme choices"
        editHref={isDraft ? `/apply/${id}/programme` : undefined}
      >
        {choices.length === 0 ? (
          <p className="text-[13px] text-muted">No programmes chosen.</p>
        ) : (
          <ol className="space-y-2.5">
            {[...choices]
              .sort((a, b) => a.rank - b.rank)
              .map((choice) => {
                const programme = programmeById(choice.programmeId);
                return (
                  <li
                    key={choice.rank}
                    className="relative rounded border border-line bg-canvas px-3.5 py-3 pl-4"
                  >
                    <span
                      className={`absolute inset-y-0 left-0 w-[3px] ${choice.rank === 1 ? "bg-gold-500" : "bg-line-strong"}`}
                      aria-hidden
                    />
                    <p className="text-[11.5px] font-semibold uppercase tracking-wide text-faint">
                      Choice {choice.rank}
                    </p>
                    <p className="mt-0.5 text-[13.5px] font-medium text-ink">
                      {programme?.name ?? "Unknown programme"}
                    </p>
                    {programme ? (
                      <p className="nums mt-0.5 text-[12.5px] text-muted">
                        {programme.code} · {programme.durationYears} years ·{" "}
                        {ssp(programme.tuitionPerSemesterSSP)} per semester
                      </p>
                    ) : null}
                  </li>
                );
              })}
          </ol>
        )}
      </Section>

      {/* Documents */}
      <Section icon={FileText} title="Documents" editHref={isDraft ? `/apply/${id}/documents` : undefined}>
        <ul className="divide-y divide-line text-[13.5px]">
          {REQUIRED_DOCUMENTS.map((spec) => {
            const uploaded = documents.find((d) => d.kind === spec.kind);
            return (
              <li
                key={spec.kind}
                className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0"
              >
                <span className="min-w-0">
                  <span className="block text-ink">{spec.label}</span>
                  {uploaded ? (
                    <span className="block truncate text-[12.5px] text-muted">
                      {uploaded.fileName}
                    </span>
                  ) : null}
                </span>
                {uploaded ? (
                  <Badge tone={uploaded.status === "verified" ? "green" : "gold"}>
                    {uploaded.status === "verified" ? "verified" : "uploaded"}
                  </Badge>
                ) : (
                  <Badge tone={spec.required ? "red" : "neutral"}>
                    {spec.required ? "missing" : "not provided"}
                  </Badge>
                )}
              </li>
            );
          })}
        </ul>
      </Section>

      {/* Fee */}
      <Section icon={Wallet} title="Application fee" editHref={isDraft && !payment ? `/apply/${id}/payment` : undefined}>
        {payment ? (
          <dl className="divide-y divide-line text-[13.5px]">
            <Row label="Amount" value={ssp(payment.amountSSP)} />
            <Row label="Method" value={methodName(payment.method)} />
            <Row label="Reference" value={payment.reference ?? "—"} />
            <div className="flex items-center justify-between gap-4 py-2.5 last:pb-0">
              <dt className="text-muted">Status</dt>
              <dd>
                <PaymentStatusBadge status={payment.status} />
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-[13px] text-muted">
            The {ssp(feeSSP)} fee has not been paid yet.
          </p>
        )}
      </Section>

      {/* Submit */}
      {isDraft ? (
        <Card>
          <CardHeader
            icon={Send}
            title="Submit your application"
            description="Check every section above carefully. Nothing can be changed after submission."
          />
          <CardBody>
            <SubmitForm
              action={submitApplication}
              applicationId={id}
              blocking={blocking}
            />
          </CardBody>
        </Card>
      ) : (
        <div className="flex justify-center pb-2">
          <ButtonLink href="/apply" variant="secondary">
            Back to my applications
          </ButtonLink>
        </div>
      )}
    </div>
  );
}

function Section({
  icon,
  title,
  editHref,
  action,
  children,
}: {
  icon?: LucideIcon;
  title: string;
  editHref?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader
        icon={icon}
        title={title}
        action={
          <div className="flex items-center gap-2.5">
            {action}
            {editHref ? (
              <Link
                href={editHref}
                className="inline-flex items-center gap-1 text-[13px] font-medium text-brand-700 underline decoration-brand-300 underline-offset-2 hover:decoration-brand-700"
              >
                <Pencil className="h-3.5 w-3.5" aria-hidden />
                Edit
              </Link>
            ) : null}
          </div>
        }
      />
      <CardBody>{children}</CardBody>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="text-right font-medium text-ink">{value || "—"}</dd>
    </div>
  );
}
