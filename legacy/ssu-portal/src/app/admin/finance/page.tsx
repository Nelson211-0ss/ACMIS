import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Banknote, Check, Inbox, Receipt, Wallet, X } from "lucide-react";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Badge, PaymentStatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/empty";
import { Field, FieldGrid, Input, Select } from "@/components/ui/field";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { currentStaff } from "@/lib/auth";
import {
  getSystemSettings,
  listFeeBalances,
  listPendingPayments,
} from "@/lib/data/repo";
import { methodName } from "@/lib/data/payments";
import { can } from "@/lib/permissions";
import { shortDate, ssp } from "@/lib/format";
import { addCharge, decidePayment } from "./actions";

export const metadata: Metadata = { title: "Bursary" };

export default async function AdminFinancePage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  const mayVerify = can(staff.staffRole, "verify_payments", settings);
  const mayAdjust = can(staff.staffRole, "manage_fees", settings);

  if (!mayVerify && !mayAdjust) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include bursary work. Ask a super
        administrator to grant it on the Roles &amp; permissions page.
      </Callout>
    );
  }

  const [pending, balances] = await Promise.all([
    listPendingPayments(),
    listFeeBalances(),
  ]);

  const owed = balances.reduce((sum, b) => sum + Math.max(0, b.balance), 0);
  const pendingTotal = pending.reduce((sum, p) => sum + p.payment.amountSSP, 0);

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">Bursary</h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Clear deposit slips against the bank statement, and correct what a
          student has been charged.
        </p>
      </div>

      {error ? (
        <Callout tone="error" title="That did not go through">
          {error}
        </Callout>
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat
          icon={Inbox}
          label="Slips awaiting clearance"
          value={pending.length}
          tone={pending.length > 0 ? "gold" : "green"}
          note={pending.length > 0 ? ssp(pendingTotal) : "Nothing waiting"}
        />
        <Stat
          icon={Wallet}
          label="Outstanding across students"
          value={ssp(owed)}
          tone={owed > 0 ? "red" : "green"}
          note={`${balances.filter((b) => b.balance > 0).length} with a balance`}
        />
        <Stat
          icon={Banknote}
          label="Students on the roll"
          value={balances.length}
          tone="brand"
        />
      </div>

      {/* --- Deposit slips ---------------------------------------------- */}
      {mayVerify ? (
        <Card>
          <CardHeader
            icon={Receipt}
            title="Deposit slips awaiting clearance"
            description="Mobile money settles itself. A slip is a claim until someone checks it against the bank statement."
          />
          {pending.length === 0 ? (
            <CardBody>
              <EmptyState icon={Check} title="Nothing waiting">
                Every deposit slip submitted so far has been decided.
              </EmptyState>
            </CardBody>
          ) : (
            <>
              {/* Phone: one card per slip. Confirm/reject are the point of
                  this screen, so they get full-width targets rather than
                  being the last column of a sideways-scrolling table. */}
              <ul className="space-y-2.5 px-4 py-4 sm:hidden">
                {pending.map(({ payment, student }) => (
                  <li
                    key={`m-${payment.id}`}
                    className="rounded-lg border border-line bg-canvas p-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-[14px] font-medium text-ink">
                          {student
                            ? `${student.firstName} ${student.lastName}`
                            : "Unknown student"}
                        </p>
                        <p className="nums truncate text-[12px] text-muted">
                          {student?.studentNumber ?? payment.studentId}
                        </p>
                      </div>
                      <span className="nums shrink-0 text-[15px] font-semibold text-ink">
                        {ssp(payment.amountSSP)}
                      </span>
                    </div>

                    <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
                      <dt className="text-muted">Reference</dt>
                      <dd className="nums text-right text-ink-soft">{payment.reference}</dd>
                      <dt className="text-muted">Method</dt>
                      <dd className="text-right text-ink-soft">{methodName(payment.method)}</dd>
                      <dt className="text-muted">Submitted</dt>
                      <dd className="nums text-right text-ink-soft">
                        {shortDate(payment.paidAt)}
                      </dd>
                    </dl>

                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <form action={decidePayment}>
                        <input type="hidden" name="paymentId" value={payment.id} />
                        <input type="hidden" name="outcome" value="confirmed" />
                        <button
                          type="submit"
                          className="inline-flex h-10 w-full items-center justify-center gap-1.5 rounded border border-green-600/40 bg-green-100 text-[13px] font-medium text-green-700 transition-colors hover:bg-green-600 hover:text-white"
                        >
                          <Check className="h-4 w-4" aria-hidden />
                          Confirm
                        </button>
                      </form>
                      <form action={decidePayment}>
                        <input type="hidden" name="paymentId" value={payment.id} />
                        <input type="hidden" name="outcome" value="failed" />
                        <button
                          type="submit"
                          className="inline-flex h-10 w-full items-center justify-center gap-1.5 rounded border border-line-strong bg-surface text-[13px] font-medium text-ink-soft transition-colors hover:border-red-600/40 hover:bg-red-100 hover:text-red-700"
                        >
                          <X className="h-4 w-4" aria-hidden />
                          Reject
                        </button>
                      </form>
                    </div>
                  </li>
                ))}
              </ul>

            <TableWrap className="hidden sm:block">
              <Table>
                <thead>
                  <tr>
                    <Th>Student</Th>
                    <Th>Reference</Th>
                    <Th>Submitted</Th>
                    <Th className="text-right">Amount</Th>
                    <Th>Decision</Th>
                  </tr>
                </thead>
                <tbody>
                  {pending.map(({ payment, student }) => (
                    <Tr key={payment.id}>
                      <Td>
                        <span className="block font-medium text-ink">
                          {student
                            ? `${student.firstName} ${student.lastName}`
                            : "Unknown student"}
                        </span>
                        <span className="nums block text-[12px] text-muted">
                          {student?.studentNumber ?? payment.studentId}
                        </span>
                      </Td>
                      <Td className="nums text-[12.5px]">
                        <span className="block">{payment.reference}</span>
                        <span className="block text-muted">
                          {methodName(payment.method)}
                        </span>
                      </Td>
                      <Td className="nums whitespace-nowrap text-[12.5px] text-muted">
                        {shortDate(payment.paidAt)}
                      </Td>
                      <Td className="nums whitespace-nowrap text-right font-semibold">
                        {ssp(payment.amountSSP)}
                      </Td>
                      <Td>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <form action={decidePayment}>
                            <input type="hidden" name="paymentId" value={payment.id} />
                            <input type="hidden" name="outcome" value="confirmed" />
                            <button
                              type="submit"
                              className="inline-flex items-center gap-1.5 whitespace-nowrap rounded border border-green-600/40 bg-green-100 px-2.5 py-1.5 text-[12.5px] font-medium text-green-700 transition-colors hover:bg-green-600 hover:text-white"
                            >
                              <Check className="h-3.5 w-3.5" aria-hidden />
                              Confirm
                            </button>
                          </form>
                          <form action={decidePayment}>
                            <input type="hidden" name="paymentId" value={payment.id} />
                            <input type="hidden" name="outcome" value="failed" />
                            <button
                              type="submit"
                              className="inline-flex items-center gap-1.5 whitespace-nowrap rounded border border-line-strong bg-surface px-2.5 py-1.5 text-[12.5px] font-medium text-ink-soft transition-colors hover:border-red-600/40 hover:bg-red-100 hover:text-red-700"
                            >
                              <X className="h-3.5 w-3.5" aria-hidden />
                              Reject
                            </button>
                          </form>
                        </div>
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
            </>
          )}
        </Card>
      ) : null}

      {/* --- Adjust a charge --------------------------------------------- */}
      {mayAdjust ? (
        <form action={addCharge}>
          <Card>
            <CardHeader
              icon={Wallet}
              title="Add a charge or a waiver"
              description="A negative amount is a waiver or scholarship. Everything here is written to the audit log."
            />
            <CardBody className="space-y-4">
              <FieldGrid>
                <Field label="Student" name="studentId" required>
                  <Select id="studentId" name="studentId" required defaultValue="">
                    <option value="" disabled>
                      Choose a student…
                    </option>
                    {balances.map(({ student }) => (
                      <option key={student.id} value={student.id}>
                        {student.firstName} {student.lastName} · {student.studentNumber}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  label="Amount (SSP)"
                  name="amountSSP"
                  required
                  hint="Negative waives; positive charges."
                >
                  <Input
                    id="amountSSP"
                    name="amountSSP"
                    type="number"
                    step="1"
                    placeholder="-25000"
                    required
                  />
                </Field>
              </FieldGrid>

              <Field label="Description" name="description" required>
                <Input
                  id="description"
                  name="description"
                  placeholder="Hardship waiver approved by the Dean"
                  required
                  maxLength={90}
                />
              </Field>

              <FieldGrid>
                <Field label="Due date" name="dueDate" required>
                  <Input id="dueDate" name="dueDate" type="date" required />
                </Field>
                <div className="flex items-end">
                  <label className="flex items-center gap-2 pb-2.5 text-[13px] text-ink-soft">
                    <input
                      type="checkbox"
                      name="blocking"
                      className="h-4 w-4 accent-brand-700"
                    />
                    Withhold results until this is paid
                  </label>
                </div>
              </FieldGrid>
            </CardBody>
            <div className="flex flex-wrap items-center gap-3 border-t border-line bg-sunken px-4 py-3 sm:px-5">
              <Button type="submit" size="sm">
                Post to the account
              </Button>
            </div>
          </Card>
        </form>
      ) : null}

      {/* --- Balances ----------------------------------------------------- */}
      <Card>
        <CardHeader
          icon={Banknote}
          title="Fee balances"
          description="Every student on the roll, largest balance first."
        />
        {/* Phone: the balance is the number that matters, so it leads. */}
        <ul className="space-y-2.5 px-4 py-4 sm:hidden">
          {balances.map(({ student, charged, paid, balance }) => (
            <li
              key={`m-${student.id}`}
              className="flex items-start justify-between gap-3 rounded-lg border border-line bg-canvas p-3"
            >
              <div className="min-w-0">
                <p className="truncate text-[14px] font-medium text-ink">
                  {student.firstName} {student.lastName}
                </p>
                <p className="nums truncate text-[12px] text-muted">
                  {student.studentNumber}
                </p>
                <p className="nums mt-1 text-[12px] text-muted">
                  {ssp(paid)} paid of {ssp(charged)}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="nums text-[15px] font-semibold text-ink">
                  {balance === 0 ? "—" : ssp(balance)}
                </p>
                <Badge tone={balance > 0 ? "red" : "green"} className="mt-1">
                  {balance > 0 ? "Owing" : "Cleared"}
                </Badge>
              </div>
            </li>
          ))}
        </ul>

        <TableWrap className="hidden sm:block">
          <Table>
            <thead>
              <tr>
                <Th>Student</Th>
                <Th className="text-right">Charged</Th>
                <Th className="text-right">Paid</Th>
                <Th className="text-right">Balance</Th>
                <Th>State</Th>
              </tr>
            </thead>
            <tbody>
              {balances.map(({ student, charged, paid, balance }) => (
                <Tr key={student.id}>
                  <Td>
                    <span className="block font-medium text-ink">
                      {student.firstName} {student.lastName}
                    </span>
                    <span className="nums block text-[12px] text-muted">
                      {student.studentNumber}
                    </span>
                  </Td>
                  <Td className="nums text-right">{ssp(charged)}</Td>
                  <Td className="nums text-right">{ssp(paid)}</Td>
                  <Td className="nums text-right font-semibold">
                    {balance === 0 ? "—" : ssp(balance)}
                  </Td>
                  <Td>
                    <Badge tone={balance > 0 ? "red" : "green"}>
                      {balance > 0 ? "Owing" : "Cleared"}
                    </Badge>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      </Card>

      <p className="text-[12px] text-muted">
        Payment states use the same vocabulary students see:{" "}
        <PaymentStatusBadge status="pending" />{" "}
        <PaymentStatusBadge status="confirmed" />{" "}
        <PaymentStatusBadge status="failed" />
      </p>
    </div>
  );
}
