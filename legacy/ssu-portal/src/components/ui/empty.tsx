import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

/** Placeholder for an empty list. Flat, quiet, never a decorative illustration. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-full border border-line bg-sunken">
        <Icon className="h-5 w-5 text-muted" aria-hidden />
      </span>
      <p className="text-sm font-semibold text-ink">{title}</p>
      {children ? (
        <p className="mt-1.5 max-w-sm text-[13px] leading-snug text-muted">{children}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
