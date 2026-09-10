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
 *
 * Two renderings of the same rows: stacked cards on a phone, a table from
 * `sm` up. A six-column table with a select and two buttons per row is
 * readable on a laptop and miserable on a 360px screen, and this portal is
 * built for the phone first. Both carry `data-search`, so the search box
 * filters whichever one is on screen without knowing which that is.
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

  const prepared = rows.map((row) => ({
    row,
    isSelf: row.kind === "staff" && row.id === currentStaffId,
    search: `${row.name} ${row.email}`.toLowerCase(),
    ...splitName(row.name),
    role: row.kind === "staff" ? (row.roleLabel as StaffRole) : null,
  }));

  return (
    <div className="space-y-3">
      <UserSearchBox />

      <div data-users-table>
        {/* Phone: one card per person. */}
        <ul className="space-y-2.5 sm:hidden">
          {prepared.map(({ row, isSelf, search, first, last, role }) => (
            <li
              key={`m-${row.kind}-${row.id}`}
              data-search={search}
              className="rounded-lg border border-line bg-surface p-3"
            >
              <div className="flex items-start gap-2.5">
                <Avatar firstName={first} lastName={last} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-medium text-ink">{row.name}</p>
                  <p className="truncate text-[12px] text-muted">{row.email}</p>
                </div>
                <Badge tone={row.statusTone} className="shrink-0">
                  {row.statusLabel}
                </Badge>
              </div>

              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                <Badge tone={KIND_TONE[row.kind]}>{KIND_LABEL[row.kind]}</Badge>
                {role ? (
                  <>
                    <Badge tone={ROLE_TONE[role]}>{STAFF_ROLE_LABELS[role]}</Badge>
                    <span className="nums text-[12px] text-muted">
                      {permissionCount(role)} of {ALL_PERMISSIONS.length} permissions
                    </span>
                  </>
                ) : (
                  <span className="nums text-[12px] text-muted">{row.roleLabel}</span>
                )}
              </div>

              <div className="mt-3 border-t border-line pt-3">
                <RowControls row={row} isSelf={isSelf} />
              </div>
            </li>
          ))}
        </ul>

        {/* Tablet and up: the full table. */}
        <TableWrap className="hidden sm:block">
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
              {prepared.map(({ row, isSelf, search, first, last, role }) => (
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
                    <RowControls row={row} isSelf={isSelf} />
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      </div>
    </div>
  );
}

/**
 * The mutation controls for one person, shared by both renderings so the
 * card and the table row can never drift apart in what they allow.
 */
function RowControls({ row, isSelf }: { row: DirectoryUser; isSelf: boolean }) {
  if (!row.mutable) return <span className="text-[12.5px] text-faint">—</span>;
  if (isSelf) {
    return (
      <span className="whitespace-nowrap text-[12.5px] text-faint">This is you</span>
    );
  }

  if (row.kind === "student") {
    return (
      <form action={changeStudentStatus} className="flex items-center gap-1.5">
        <input type="hidden" name="id" value={row.id} />
        <select
          name="status"
          defaultValue={row.statusLabel}
          aria-label={`Status for ${row.name}`}
          className="h-9 min-w-0 flex-1 rounded border border-line-strong bg-surface px-2 text-[12.5px] text-ink sm:h-8 sm:flex-none"
        >
          <option value="active">active</option>
          <option value="suspended">suspended</option>
          <option value="graduated">graduated</option>
          <option value="deferred">deferred</option>
        </select>
        <RowButton>Save</RowButton>
      </form>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <form action={changeStaffRole} className="flex min-w-0 flex-1 items-center gap-1.5 sm:flex-none">
        <input type="hidden" name="id" value={row.id} />
        <select
          name="staffRole"
          defaultValue={row.roleLabel}
          aria-label={`Role for ${row.name}`}
          className="h-9 min-w-0 flex-1 rounded border border-line-strong bg-surface px-2 text-[12.5px] text-ink sm:h-8 sm:flex-none"
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
  );
}

/**
 * Row-scale button. Smaller than the shared Button (which is built for a
 * 44px touch target in forms); a table row that used those would be twice
 * the height for controls that are secondary to reading the row. On a phone
 * it grows back to a 36px target, where it is the primary control.
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
        "h-9 shrink-0 whitespace-nowrap rounded border border-line-strong bg-surface px-2.5 text-[12.5px] font-medium transition-colors sm:h-8 sm:py-1.5 " +
        (danger
          ? "text-ink-soft hover:border-red-600/40 hover:bg-red-100 hover:text-red-700"
          : "text-ink-soft hover:bg-sunken")
      }
    >
      {children}
    </button>
  );
}
