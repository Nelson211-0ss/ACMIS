import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { CheckCircle2, History, Receipt, Wallet } from "lucide-react";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Badge, PaymentStatusBadge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/empty";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { currentStudent } from "@/lib/auth";
import { getFeeSummary } from "@/lib/data/repo";
import { methodName } from "@/lib/data/payments";
import { institution } from "@/lib/institution";
import { relativeDays, shortDate, ssp } from "@/lib/format";
import { payFees } from "./actions";
import { PayForm } from "./form";

export const metadata: Metadata = { title: "Fees & payments" };

export default async function FinancePage() {
  const student = await currentStudent();
  if (!student) redirect("/login");

  const fees = await getFeeSummary(student.id);
  const overdue = fees.items.filter(
    (f) => new Date(f.dueDate).getTime() < Date.now(),
  );

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Fees &amp; payments
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          {institution.academicYear} · Semester {student.currentSemester} ·{" "}
          {student.studentNumber}
        </p>
      </div>

      {fees.blockingBalance > 0 && overdue.length > 0 ? (
        <Callout tone="error" title="Overdue">
          {overdue.length} charge{overdue.length === 1 ? "" : "s"} passed the due
          date. Results and registration stay blocked while tuition or
          examination fees are outstanding.
        </Callout>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat icon={Receipt} label="Charged this semester" value={ssp(fees.charged)} />
        <Stat icon={CheckCircle2} label="Paid" value={ssp(fees.paid)} />
        <Stat
          icon={Wallet}
          label="Balance"
          value={fees.balance === 0 ? "Cleared" : ssp(fees.balance)}
          note={
            fees.nextDue && fees.balance > 0
              ? `Next due ${relativeDays(fees.nextDue.dueDate)}`
              : undefined
          }
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader
            icon={Receipt}
            title="Charges"
            description="Tuition and examination fees must be cleared before results are released."
          />
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Description</Th>
                  <Th>Due</Th>
                  <Th className="text-right">Amount</Th>
                </tr>
              </thead>
              <tbody>
                {fees.items.map((item) => {
                  const late = new Date(item.dueDate).getTime() < Date.now();
                  return (
                    <Tr key={item.id}>
                      <Td>
                        <span className="block text-[13.5px] text-ink">
                          {item.description}
                        </span>
                        {item.blocking ? (
                          <Badge tone="gold" className="mt-1">
                            blocks results
                          </Badge>
                        ) : null}
                      </Td>
                      <Td
                        className={`nums whitespace-nowrap text-[13px] ${late ? "font-medium text-red-700" : "text-muted"}`}
                      >
                        {shortDate(item.dueDate)}
                      </Td>
                      <Td className="nums whitespace-nowrap text-right font-medium">
                        {ssp(item.amountSSP)}
                      </Td>
                    </Tr>
                  );
                })}
                <tr>
                  <Td className="bg-sunken font-semibold" colSpan={2}>
                    Total charged
                  </Td>
                  <Td className="nums bg-sunken text-right font-semibold">
                    {ssp(fees.charged)}
                  </Td>
                </tr>
              </tbody>
            </Table>
          </TableWrap>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            icon={Wallet}
            title="Make a payment"
            description={
              fees.balance > 0 ? `${ssp(fees.balance)} outstanding` : "Account cleared"
            }
          />
          <CardBody>
            <PayForm action={payFees} balance={fees.balance} phone={student.phone} />
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader icon={History} title="Payment history" />
        {fees.payments.length === 0 ? (
          <EmptyState icon={Receipt} title="No payments recorded">
            Payments appear here as soon as your provider confirms them, or
            within two working days for a bank deposit slip.
          </EmptyState>
        ) : (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Date</Th>
                  <Th>Method</Th>
                  <Th>Reference</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Amount</Th>
                </tr>
              </thead>
              <tbody>
                {fees.payments.map((p) => (
                  <Tr key={p.id}>
                    <Td className="nums whitespace-nowrap text-muted">
                      {shortDate(p.paidAt)}
                    </Td>
                    <Td className="whitespace-nowrap">{methodName(p.method)}</Td>
                    <Td className="nums text-muted">{p.reference}</Td>
                    <Td>
                      <PaymentStatusBadge status={p.status} />
                    </Td>
                    <Td className="nums whitespace-nowrap text-right font-medium">
                      {ssp(p.amountSSP)}
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
