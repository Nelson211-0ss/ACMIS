import { Badge } from "@/components/ui/badge";
import type { Tone } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Table, TableWrap, Td, Th, Tr } from "@/components/ui/table";
import { ALL_PERMISSIONS, STAFF_ROLE_LABELS, STAFF_ROLES } from "@/lib/permissions";
import type { DirectoryUser, StaffRole, SystemSettings } from "@/lib/types";
import { changeStaffRole, changeStaffStatus, changeStudentStatus } from "./actions";
import { UserSearchBox } from "./search-box";

const KIND_LABEL: Record<DirectoryUser["kind"], string> = {
  staff: "Staff",
  student: "Student",
  applicant: "Applicant",
};

const KIND_TONE: Record<DirectoryUser["kind"], Tone> = {
  staff: "brand",
  student: "neutral",
  applicant: "neutral",
};

/**
 * Super administrator is gold: it is the one role with no ceiling, and gold is
 * already this system's "this is the top of the scale" colour. Everything else
 * is brand or neutral — red is reserved for things being wrong, and a role is
 * never wrong.
 */
const ROLE_TONE: Record<StaffRole, Tone> = {
  super_admin: "gold",
  head_of_department: "gold",
  registrar: "brand",
  bursar: "brand",
  lecturer: "neutral",
  it_support: "brand",
  viewer: "neutral",
};

/** Splits a display name for the avatar's initials fallback. */
function splitName(name: string): { first: string; last: string } {
  // Drop an academic title so the avatar reads "PL", not "DP".
  const parts = name.replace(/^(Dr|Prof|Mr|Mrs|Ms)\.?\s+/i, "").split(/\s+/);
  return { first: parts[0] ?? name, last: parts.length > 1 ? parts[parts.length - 1] : "" };
}

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
  settings,
}: {
  rows: DirectoryUser[];
  currentStaffId: string;
  settings: SystemSettings;
}) {
  const permissionCount = (role: StaffRole) =>
    role === "super_admin"
      ? ALL_PERMISSIONS.length
      : (settings.rolePermissions[role] ?? []).length;

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
                <Th>Access</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isSelf = row.kind === "staff" && row.id === currentStaffId;
                const search = `${row.name} ${row.email}`.toLowerCase();
                const { first, last } = splitName(row.name);
                const role = row.kind === "staff" ? (row.roleLabel as StaffRole) : null;

                return (
                  <Tr key={`${row.kind}-${row.id}`} data-search={search}>
                    <Td>
                      <div className="flex items-center gap-2.5">
                        <Avatar firstName={first} lastName={last} />
                        <div className="min-w-0">
                          <span className="block truncate font-medium text-ink">
                            {row.name}
                          </span>
                          <span className="block truncate text-[12px] text-muted">
                            {row.email}
                          </span>
                        </div>
                      </div>
                    </Td>
                    <Td>
                      <Badge tone={KIND_TONE[row.kind]}>{KIND_LABEL[row.kind]}</Badge>
                    </Td>
                    <Td>
                      {role ? (
                        <Badge tone={ROLE_TONE[role]}>{STAFF_ROLE_LABELS[role]}</Badge>
                      ) : (
                        <span className="nums text-[13px] text-ink-soft">
                          {row.roleLabel}
                        </span>
                      )}
                    </Td>
                    <Td>
                      {role ? (
                        <span className="nums whitespace-nowrap text-[12.5px] text-muted">
                          {permissionCount(role)} of {ALL_PERMISSIONS.length}
                        </span>
                      ) : (
                        <span className="text-[12.5px] text-faint">—</span>
                      )}
                    </Td>
                    <Td>
                      <Badge tone={row.statusTone}>{row.statusLabel}</Badge>
                    </Td>
                    <Td>
                      {!row.mutable ? (
                        <span className="text-[12.5px] text-faint">—</span>
                      ) : isSelf ? (
                        <span className="whitespace-nowrap text-[12.5px] text-faint">
                          This is you
                        </span>
                      ) : row.kind === "student" ? (
                        <form action={changeStudentStatus} className="flex items-center gap-1.5">
                          <input type="hidden" name="id" value={row.id} />
                          <select
                            name="status"
                            defaultValue={row.statusLabel}
                            aria-label={`Status for ${row.name}`}
                            className="h-8 rounded border border-line-strong bg-surface px-2 text-[12.5px] text-ink"
                          >
                            <option value="active">active</option>
                            <option value="suspended">suspended</option>
                            <option value="graduated">graduated</option>
                            <option value="deferred">deferred</option>
                          </select>
                          <RowButton>Save</RowButton>
                        </form>
                      ) : (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <form action={changeStaffRole} className="flex items-center gap-1.5">
                            <input type="hidden" name="id" value={row.id} />
                            <select
                              name="staffRole"
                              defaultValue={row.roleLabel}
                              aria-label={`Role for ${row.name}`}
                              className="h-8 rounded border border-line-strong bg-surface px-2 text-[12.5px] text-ink"
                            >
                              {STAFF_ROLES.map((r) => (
                                <option key={r} value={r}>
                                  {STAFF_ROLE_LABELS[r]}
                                </option>
                              ))}
                            </select>
                            <RowButton>Save</RowButton>
                          </form>
                          <form action={changeStaffStatus}>
                            <input type="hidden" name="id" value={row.id} />
                            <input
                              type="hidden"
                              name="status"
                              value={row.statusLabel === "active" ? "suspended" : "active"}
                            />
                            <RowButton danger={row.statusLabel === "active"}>
                              {row.statusLabel === "active" ? "Suspend" : "Activate"}
                            </RowButton>
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

/**
 * Row-scale button. Smaller than the shared Button (which is built for a
 * 44px touch target in forms); a table row that used those would be twice
 * the height for controls that are secondary to reading the row.
 */
function RowButton({
  children,
  danger,
}: {
  children: React.ReactNode;
  danger?: boolean;
}) {
  return (
    <button
      type="submit"
      className={
        "whitespace-nowrap rounded border border-line-strong bg-surface px-2.5 py-1.5 text-[12.5px] font-medium transition-colors " +
        (danger
          ? "text-ink-soft hover:border-red-600/40 hover:bg-red-100 hover:text-red-700"
          : "text-ink-soft hover:bg-sunken")
      }
    >
      {children}
    </button>
  );
}
