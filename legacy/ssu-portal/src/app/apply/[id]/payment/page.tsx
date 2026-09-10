import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Wallet } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { PaymentStatusBadge } from "@/components/ui/badge";
import { getApplication, getScheme } from "@/lib/data/repo";
import { methodName } from "@/lib/data/payments";
import { institution } from "@/lib/institution";
import { shortDate, ssp } from "@/lib/format";
import { payApplicationFee } from "../actions";
import { PaymentForm } from "./form";

export const metadata: Metadata = { title: "Application fee" };

export default async function PaymentStep({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const application = await getApplication(id);
  if (!application) notFound();

  const scheme = application.schemeId ? await getScheme(application.schemeId) : null;
  const feeSSP = scheme?.applicationFeeSSP ?? institution.applicationFeeSSP;
  const payment = application.payment;

  // Already paid, or a slip is lodged and waiting on the bursary.
  if (payment) {
    return (
      <Card>
        <CardHeader
          icon={Wallet}
          title="Application fee"
          description={`Reference ${application.reference}`}
          action={<PaymentStatusBadge status={payment.status} />}
        />
        <CardBody className="space-y-4">
          <dl className="divide-y divide-line text-[13.5px]">
            <Row label="Amount" value={ssp(payment.amountSSP)} />
            <Row label="Method" value={methodName(payment.method)} />
            <Row label="Reference" value={payment.reference ?? "—"} />
            <Row label="Date" value={shortDate(payment.createdAt)} />
          </dl>

          {payment.status === "pending" ? (
            <Callout tone="info" title="Awaiting confirmation">
              The bursary is checking your deposit slip. You do not have to wait
              — submit your application now, and the fee will be matched to it.
            </Callout>
          ) : (
            <Callout tone="success" title="Fee paid">
              Nothing further is due for this application.
            </Callout>
          )}
        </CardBody>
        <CardFooter className="justify-end">
          <ButtonLink href={`/apply/${id}/review`}>
            {application.status === "draft"
              ? "Continue to review and submit"
              : "View application"}
          </ButtonLink>
        </CardFooter>
      </Card>
    );
  }

  return (
    <PaymentForm
      action={payApplicationFee.bind(null, id)}
      applicationId={id}
      feeSSP={feeSSP}
      phone={application.personal.phone}
    />
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="nums text-right font-medium text-ink">{value}</dd>
    </div>
  );
}
