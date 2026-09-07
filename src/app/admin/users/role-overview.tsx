import { Check, Minus } from "lucide-react";
import { ALL_PERMISSIONS, PERMISSION_LABELS, STAFF_ROLE_LABELS, STAFF_ROLES } from "@/lib/permissions";
import type { Permission, StaffRole, SystemSettings } from "@/lib/types";
import { cn } from "@/lib/cn";

/**
 * What each role actually grants, next to how many people hold it.
 *
 * The Roles & permissions page is where this gets *edited*; this is the
 * read-only companion on the Users page, because "what does bursar mean" is
 * the question you have while looking at the directory, not one worth a
 * separate navigation to answer.
 */
export function RoleOverview({
  settings,
  counts,
}: {
  settings: SystemSettings;
  counts: Record<StaffRole, number>;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {STAFF_ROLES.map((role) => (
        <RoleCard
          key={role}
          role={role}
          count={counts[role] ?? 0}
          permissions={
            role === "super_admin"
              ? ALL_PERMISSIONS
              : (settings.rolePermissions[role] ?? [])
          }
        />
      ))}
    </div>
  );
}

function RoleCard({
  role,
  count,
  permissions,
}: {
  role: StaffRole;
  count: number;
  permissions: Permission[];
}) {
  const held = new Set(permissions);
  const isSuper = role === "super_admin";

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface">
      <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-[13.5px] font-semibold text-ink">
            {STAFF_ROLE_LABELS[role]}
          </p>
          <p className="nums mt-0.5 text-[12px] text-muted">
            {count} {count === 1 ? "account" : "accounts"} ·{" "}
            {permissions.length} of {ALL_PERMISSIONS.length} permissions
          </p>
        </div>
        {/* A filled ring reads the privilege level at a glance without
            needing to count the ticks below. */}
        <span
          className={cn(
            "nums flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-[11.5px] font-semibold",
            isSuper
              ? "border-gold-200 bg-gold-100 text-gold-700"
              : permissions.length === 0
                ? "border-line-strong bg-sunken text-faint"
                : "border-brand-200 bg-brand-50 text-brand-700",
          )}
        >
          {permissions.length}
        </span>
      </div>

      <ul className="space-y-1.5 px-4 py-3">
        {ALL_PERMISSIONS.map((permission) => {
          const on = held.has(permission);
          return (
            <li
              key={permission}
              className={cn(
                "flex items-center gap-2 text-[12.5px]",
                on ? "text-ink-soft" : "text-faint",
              )}
            >
              {on ? (
                <Check className="h-3.5 w-3.5 shrink-0 text-green-600" aria-hidden />
              ) : (
                <Minus className="h-3.5 w-3.5 shrink-0 text-line-strong" aria-hidden />
              )}
              <span className={cn(!on && "line-through decoration-line-strong")}>
                {PERMISSION_LABELS[permission]}
              </span>
            </li>
          );
        })}
      </ul>

      {isSuper ? (
        <p className="mt-auto border-t border-line px-4 py-2.5 text-[11.5px] text-muted">
          Fixed at every permission — a role that could lower its own ceiling
          would not be a ceiling.
        </p>
      ) : null}
    </div>
  );
}
