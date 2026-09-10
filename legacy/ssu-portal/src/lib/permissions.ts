import type { Permission, StaffRole, SystemSettings } from "./types";

export const STAFF_ROLE_LABELS: Record<StaffRole, string> = {
  super_admin: "Super administrator",
  head_of_department: "Head of department",
  registrar: "Registrar",
  bursar: "Bursar",
  lecturer: "Lecturer",
  it_support: "IT support",
  viewer: "Viewer",
};

export const PERMISSION_LABELS: Record<Permission, string> = {
  manage_users: "Manage users",
  manage_roles: "Manage roles & permissions",
  manage_settings: "Manage system settings",
  manage_appearance: "Manage appearance",
  manage_announcements: "Manage announcements",
  manage_admissions: "Manage admissions",
  manage_results: "Enter results",
  approve_results: "Approve & publish results",
  verify_payments: "Verify payments",
  manage_fees: "Adjust fees",
  manage_accounts: "Reset passwords & unlock accounts",
  view_monitoring: "View monitoring",
  view_audit_log: "View audit log",
};

export const ALL_PERMISSIONS = Object.keys(PERMISSION_LABELS) as Permission[];

/** Every assignable staff role, in the order they read as a hierarchy. */
export const STAFF_ROLES = Object.keys(STAFF_ROLE_LABELS) as StaffRole[];

/** super_admin always has every permission, regardless of what the matrix says — the one role that can't lock itself out. */
export function can(
  staffRole: StaffRole,
  permission: Permission,
  settings: Pick<SystemSettings, "rolePermissions">,
): boolean {
  if (staffRole === "super_admin") return true;
  return settings.rolePermissions[staffRole]?.includes(permission) ?? false;
}
