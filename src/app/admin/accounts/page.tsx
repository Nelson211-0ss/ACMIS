import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { KeyRound, LifeBuoy, Lock, LockOpen } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, Input } from "@/components/ui/field";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { currentStaff } from "@/lib/auth";
import { getSystemSettings, listAllUsers } from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import { issueResetLink, setAccountStatus } from "./actions";

export const metadata: Metadata = { title: "Account recovery" };

export default async function AdminAccountsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; issued?: string; token?: string }>;
}) {
  const { error, issued, token } = await searchParams;
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "manage_accounts", settings)) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include account recovery. Ask a
        super administrator to grant it on the Roles &amp; permissions page.
      </Callout>
    );
  }

  const rows = await listAllUsers();
  // Applicants have no status to unlock, so they are not listed for locking.
  const lockable = rows.filter((r) => r.kind !== "applicant");

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Account recovery
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Get people back into their accounts. This desk can reset and unlock —
          it cannot create an account or change what anyone is allowed to do.
        </p>
      </div>

      {error ? (
        <Callout tone="error" title="That did not go through">
          {error}
        </Callout>
      ) : null}

      {issued && token ? (
        <Callout tone="success" title={`Reset link issued for ${issued}`}>
          <p>
            It expires in an hour and works once. Read it out or send it on —
            do not set a password on their behalf.
          </p>
          <p className="nums mt-2 break-all rounded border border-line bg-surface px-3 py-2 text-[12.5px]">
            /reset-password?token={token}
          </p>
          <p className="mt-2 text-[12px]">
            Shown here because no mail service is connected yet. Once one is,
            this sends instead of displaying.
          </p>
        </Callout>
      ) : null}

      <form action={issueResetLink}>
        <Card>
          <CardHeader
            icon={KeyRound}
            title="Issue a password reset link"
            description="Works for a student, an applicant or a staff member — whoever owns the address."
          />
          <CardBody>
            <Field
              label="Email address on the account"
              name="email"
              required
              hint="The person sets their own new password from the link. You never see it."
            >
              <Input
                id="email"
                name="email"
                type="email"
                inputMode="email"
                autoCapitalize="none"
                spellCheck={false}
                placeholder="achol.majok@student.example.ss"
                required
              />
            </Field>
          </CardBody>
          <div className="flex flex-wrap items-center gap-3 border-t border-line bg-sunken px-4 py-3 sm:px-5">
            <Button type="submit" size="sm">
              <LifeBuoy className="h-4 w-4" aria-hidden />
              Issue reset link
            </Button>
          </div>
        </Card>
      </form>

      <Card>
        <CardHeader
          icon={Lock}
          title="Locked and active accounts"
          description="Unlock someone who has been suspended, or lock an account that is being misused."
        />
        {/* Phone: one card per account, lock/unlock as a full-width target. */}
        <ul className="space-y-2.5 px-4 py-4 sm:hidden">
          {lockable.map((row) => {
            const suspended = row.statusLabel === "suspended";
            const isSelf = row.kind === "staff" && row.id === staff.id;
            return (
              <li
                key={`m-${row.kind}-${row.id}`}
                className="rounded-lg border border-line bg-canvas p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-[14px] font-medium text-ink">{row.name}</p>
                    <p className="truncate text-[12px] text-muted">{row.email}</p>
                    <p className="mt-0.5 text-[12px] capitalize text-faint">{row.kind}</p>
                  </div>
                  <Badge tone={row.statusTone} className="shrink-0">
                    {row.statusLabel}
                  </Badge>
                </div>

                <div className="mt-3">
                  {isSelf ? (
                    <p className="text-[12.5px] text-faint">
                      This is you — use another account to change it.
                    </p>
                  ) : (
                    <form action={setAccountStatus}>
                      <input type="hidden" name="kind" value={row.kind} />
                      <input type="hidden" name="id" value={row.id} />
                      <input
                        type="hidden"
                        name="status"
                        value={suspended ? "active" : "suspended"}
                      />
                      <button
                        type="submit"
                        className={
                          "inline-flex h-10 w-full items-center justify-center gap-1.5 rounded border text-[13px] font-medium transition-colors " +
                          (suspended
                            ? "border-green-600/40 bg-green-100 text-green-700 hover:bg-green-600 hover:text-white"
                            : "border-line-strong bg-surface text-ink-soft hover:border-red-600/40 hover:bg-red-100 hover:text-red-700")
                        }
                      >
                        {suspended ? (
                          <>
                            <LockOpen className="h-4 w-4" aria-hidden />
                            Unlock this account
                          </>
                        ) : (
                          <>
                            <Lock className="h-4 w-4" aria-hidden />
                            Lock this account
                          </>
                        )}
                      </button>
                    </form>
                  )}
                </div>
              </li>
            );
          })}
        </ul>

        <TableWrap className="hidden sm:block">
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Kind</Th>
                <Th>Status</Th>
                <Th>Action</Th>
              </tr>
            </thead>
            <tbody>
              {lockable.map((row) => {
                const suspended = row.statusLabel === "suspended";
                const isSelf = row.kind === "staff" && row.id === staff.id;
                return (
                  <Tr key={`${row.kind}-${row.id}`}>
                    <Td>
                      <span className="block font-medium text-ink">{row.name}</span>
                      <span className="block text-[12px] text-muted">{row.email}</span>
                    </Td>
                    <Td className="text-[12.5px] capitalize text-muted">{row.kind}</Td>
                    <Td>
                      <Badge tone={row.statusTone}>{row.statusLabel}</Badge>
                    </Td>
                    <Td>
                      {isSelf ? (
                        <span className="whitespace-nowrap text-[12.5px] text-faint">
                          This is you
                        </span>
                      ) : (
                        <form action={setAccountStatus}>
                          <input type="hidden" name="kind" value={row.kind} />
                          <input type="hidden" name="id" value={row.id} />
                          <input
                            type="hidden"
                            name="status"
                            value={suspended ? "active" : "suspended"}
                          />
                          <button
                            type="submit"
                            className={
                              "inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-2.5 py-1.5 text-[12.5px] font-medium transition-colors " +
                              (suspended
                                ? "border-green-600/40 bg-green-100 text-green-700 hover:bg-green-600 hover:text-white"
                                : "border-line-strong bg-surface text-ink-soft hover:border-red-600/40 hover:bg-red-100 hover:text-red-700")
                            }
                          >
                            {suspended ? (
                              <>
                                <LockOpen className="h-3.5 w-3.5" aria-hidden />
                                Unlock
                              </>
                            ) : (
                              <>
                                <Lock className="h-3.5 w-3.5" aria-hidden />
                                Lock
                              </>
                            )}
                          </button>
                        </form>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </TableWrap>
      </Card>
    </div>
  );
}
