import { Badge } from "@/components/ui/badge";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { STAFF_ROLE_LABELS } from "@/lib/permissions";
import type { DirectoryUser, StaffRole } from "@/lib/types";
import { changeStaffRole, changeStaffStatus, changeStudentStatus } from "./actions";
import { UserSearchBox } from "./search-box";

const STAFF_ROLES = Object.keys(STAFF_ROLE_LABELS) as StaffRole[];

const KIND_LABEL: Record<DirectoryUser["kind"], string> = {
  staff: "Staff",
  student: "Student",
  applicant: "Applicant",
};

/**
 * Plain server component — deliberately NOT "use client".
 *
 * Every row's mutation is a `<form action={serverFn}>` bound directly to a
 * Server Action. Binding one of those inside a Client Component turned out to
 * hit a real dev-mode bug in this Next.js version: the action's own execution
 * and the page's next render pulled from two different module instances of
 * the in-memory store, so a mutation would apply and then immediately appear
 * to have never happened. Keeping the table (forms included) as ordinary
 * server-rendered markup — the same pattern the working Settings and Roles
 * pages already use — avoids it. Only the search box below is a client
 * island, and it filters via the DOM rather than by holding `rows` in React
 * state, so it never needs to re-render (or move) these forms.
 */
export function UsersTable({
  rows,
  currentStaffId,
}: {
  rows: DirectoryUser[];
  currentStaffId: string;
}) {
  return (
    <div className="space-y-3">
      <UserSearchBox />

      <TableWrap>
        <div data-users-table>
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Kind</Th>
                <Th>Role / programme</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isSelf = row.kind === "staff" && row.id === currentStaffId;
                const search = `${row.name} ${row.email}`.toLowerCase();
                return (
                  <Tr key={`${row.kind}-${row.id}`} data-search={search}>
                    <Td>
                      <span className="block font-medium text-ink">{row.name}</span>
                      <span className="block text-[12px] text-muted">{row.email}</span>
                    </Td>
                    <Td>{KIND_LABEL[row.kind]}</Td>
                    <Td className="nums">
                      {row.kind === "staff" ? STAFF_ROLE_LABELS[row.roleLabel as StaffRole] : row.roleLabel}
                    </Td>
                    <Td>
                      <Badge tone={row.statusTone}>{row.statusLabel}</Badge>
                    </Td>
                    <Td>
                      {!row.mutable ? (
                        <span className="text-[12.5px] text-faint">—</span>
                      ) : isSelf ? (
                        <span className="text-[12.5px] text-faint">This is you</span>
                      ) : row.kind === "student" ? (
                        <form action={changeStudentStatus} className="flex items-center gap-1.5">
                          <input type="hidden" name="id" value={row.id} />
                          <select
                            name="status"
                            defaultValue={row.statusLabel}
                            className="h-8 rounded border border-line-strong bg-surface px-2 text-[12.5px]"
                          >
                            <option value="active">active</option>
                            <option value="suspended">suspended</option>
                            <option value="graduated">graduated</option>
                            <option value="deferred">deferred</option>
                          </select>
                          <button
                            type="submit"
                            className="rounded border border-line-strong bg-surface px-2.5 py-1.5 text-[12.5px] font-medium text-ink-soft transition-colors hover:bg-sunken"
                          >
                            Save
                          </button>
                        </form>
                      ) : (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <form action={changeStaffRole} className="flex items-center gap-1.5">
                            <input type="hidden" name="id" value={row.id} />
                            <select
                              name="staffRole"
                              defaultValue={row.roleLabel}
                              className="h-8 rounded border border-line-strong bg-surface px-2 text-[12.5px]"
                            >
                              {STAFF_ROLES.map((r) => (
                                <option key={r} value={r}>
                                  {STAFF_ROLE_LABELS[r]}
                                </option>
                              ))}
                            </select>
                            <button
                              type="submit"
                              className="rounded border border-line-strong bg-surface px-2.5 py-1.5 text-[12.5px] font-medium text-ink-soft transition-colors hover:bg-sunken"
                            >
                              Save
                            </button>
                          </form>
                          <form action={changeStaffStatus}>
                            <input type="hidden" name="id" value={row.id} />
                            <input
                              type="hidden"
                              name="status"
                              value={row.statusLabel === "active" ? "suspended" : "active"}
                            />
                            <button
                              type="submit"
                              className="rounded border border-line-strong bg-surface px-2.5 py-1.5 text-[12.5px] font-medium text-ink-soft transition-colors hover:bg-sunken"
                            >
                              {row.statusLabel === "active" ? "Suspend" : "Activate"}
                            </button>
                          </form>
                        </div>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </div>
      </TableWrap>
    </div>
  );
}
