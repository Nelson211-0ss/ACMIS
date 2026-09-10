import { Inbox, Layers, type LucideIcon } from "lucide-react";

/** Plain data for the same reason lib/admin-nav.ts is: a Server Component
 *  can't hand a Client Component a prop holding icon function references. */
export interface AdmissionsNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const ADMISSIONS_NAV: AdmissionsNavItem[] = [
  { href: "/admissions", label: "Applications queue", icon: Inbox },
  { href: "/admissions/schemes", label: "Admission schemes", icon: Layers },
];
