import {
  Activity,
  KeyRound,
  LayoutDashboard,
  Megaphone,
  Palette,
  ScrollText,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { Permission } from "./types";

/**
 * Plain data, deliberately not in admin-nav.tsx: that file is "use client"
 * (it needs usePathname for the active-link state), and a Server Component
 * importing a plain constant from a client module gets a client-reference
 * proxy back instead of the real array — the same trap `lib/theme.ts` exists
 * to avoid for the theme-init script.
 */
export interface AdminNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Undefined means every signed-in staff member can see it. */
  permission?: Permission;
}

export const ADMIN_NAV: AdminNavItem[] = [
  { href: "/admin", label: "Overview", icon: LayoutDashboard },
  { href: "/admin/users", label: "Users", icon: Users, permission: "manage_users" },
  { href: "/admin/roles", label: "Roles & permissions", icon: KeyRound, permission: "manage_roles" },
  { href: "/admin/announcements", label: "Announcements", icon: Megaphone, permission: "manage_announcements" },
  { href: "/admin/settings", label: "System settings", icon: Settings, permission: "manage_settings" },
  { href: "/admin/theme", label: "Appearance", icon: Palette, permission: "manage_appearance" },
  { href: "/admin/monitoring", label: "Monitoring", icon: Activity, permission: "view_monitoring" },
  { href: "/admin/audit", label: "Audit log", icon: ScrollText, permission: "view_audit_log" },
];
