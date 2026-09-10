import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { ScrollText } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { EmptyState } from "@/components/ui/empty";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { currentStaff } from "@/lib/auth";
import { getAuditLog, getSystemSettings } from "@/lib/data/repo";
import { can } from "@/lib/permissions";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Audit log" };

export default async function AdminAuditPage() {
  const staff = await currentStaff();
  if (!staff) redirect("/login");

  const settings = await getSystemSettings();
  if (!can(staff.staffRole, "view_audit_log", settings)) {
    return (
      <Callout tone="warning" title="Restricted">
        Your role ({staff.staffRole}) does not include the audit log.
      </Callout>
    );
  }

  const entries = await getAuditLog();

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Audit log
        </h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Every change made from this dashboard — who, what, and when.
        </p>
      </div>

      <Card>
        <CardHeader icon={ScrollText} title="Recent activity" />
        {entries.length === 0 ? (
          <EmptyState icon={ScrollText} title="No activity yet">
            Actions taken from the admin dashboard will appear here.
          </EmptyState>
        ) : (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>When</Th>
                  <Th>Who</Th>
                  <Th>Action</Th>
                  <Th>Target</Th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <Tr key={e.id}>
                    <Td className="nums whitespace-nowrap text-muted">{formatDateTime(e.at)}</Td>
                    <Td className="font-medium text-ink">{e.actor}</Td>
                    <Td>{e.action}</Td>
                    <Td className="text-muted">{e.target ?? "—"}</Td>
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
