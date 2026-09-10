import { Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { STAFF_ROLE_LABELS } from "@/lib/permissions";
import type { SeededAccount } from "@/lib/data/repo";
import type { StaffRole } from "@/lib/types";
import { signInAsDemo } from "./actions";

const GROUP_ORDER: SeededAccount["group"][] = [
  "Students and applicants",
  "Administration",
  "Academic",
  "Support",
];

function roleLabel(role: string): string {
  return role in STAFF_ROLE_LABELS
    ? STAFF_ROLE_LABELS[role as StaffRole]
    : role;
}

/**
 * Every seeded account, grouped, each one a single tap.
 *
 * Rendered from the store rather than a hand-kept list — the previous
 * hardcoded set covered 9 of 20, so the rest were only reachable by digging
 * an email out of the users table and knowing the shared password.
 *
 * Suspended accounts are shown but not clickable: a locked account is a state
 * worth demonstrating, and leaving it as a button that silently refuses reads
 * as a broken demo rather than a working one.
 */
export function SeededAccountList({ accounts }: { accounts: SeededAccount[] }) {
  return (
    <div className="space-y-5">
      {GROUP_ORDER.map((group) => {
        const inGroup = accounts.filter((a) => a.group === group);
        if (inGroup.length === 0) return null;

        return (
          <section key={group}>
            <h3 className="text-[11.5px] font-semibold uppercase tracking-wide text-faint">
              {group}
            </h3>

            <ul className="mt-2 space-y-2">
              {inGroup.map((account) => (
                <li key={account.email}>
                  {account.suspended ? (
                    <div className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-line-strong bg-sunken px-3 py-2.5">
                      <div className="min-w-0">
                        <p className="truncate text-[13.5px] font-medium text-muted">
                          {account.name}
                        </p>
                        <p className="truncate text-[12px] text-faint">
                          {roleLabel(account.role)}
                        </p>
                      </div>
                      <Badge tone="red" className="shrink-0">
                        <Lock className="h-3 w-3" aria-hidden />
                        Suspended
                      </Badge>
                    </div>
                  ) : (
                    <form action={signInAsDemo}>
                      <input type="hidden" name="email" value={account.email} />
                      <button
                        type="submit"
                        className="flex w-full items-center justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2.5 text-left transition-[border-color,box-shadow] duration-150 hover:border-brand-300 hover:shadow-soft"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-[13.5px] font-medium text-ink">
                            {account.name}
                          </span>
                          <span className="block truncate text-[12px] text-muted">
                            {account.email}
                          </span>
                        </span>
                        <Badge tone="neutral" className="shrink-0">
                          {roleLabel(account.role)}
                        </Badge>
                      </button>
                    </form>
                  )}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
