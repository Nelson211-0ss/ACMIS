import type { ComponentProps, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Flat surface, hairline border, no shadow by default — a static card never
 * lifts, because nothing happens when you touch it.
 *
 * `interactive` is for the ones that are actually a link or button in
 * disguise (a nav tile, a course card): a one-step border shift plus the
 * single soft shadow the design already reserves for popovers, so a whole
 * card reads as "pressable" the same way a button does.
 */
export function Card({
  interactive,
  className,
  ...props
}: ComponentProps<"section"> & { interactive?: boolean }) {
  return (
    <section
      className={cn(
        "rounded-lg border border-line bg-surface",
        interactive &&
          "transition-[border-color,box-shadow,transform] duration-150 hover:border-brand-300 hover:shadow-soft motion-safe:hover:-translate-y-px",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  /** Reserved for a card whose subject isn't obvious from the title alone — skip it on repeated list items. */
  icon?: LucideIcon;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 border-b border-line px-4 py-3.5 sm:px-5",
        className,
      )}
    >
      <div className="flex min-w-0 items-start gap-3">
        {Icon ? (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded border border-brand-200 bg-brand-50">
            <Icon className="h-4 w-4 text-brand-700" aria-hidden />
          </span>
        ) : null}
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold leading-tight text-ink">{title}</h2>
          {description ? (
            <p className="mt-1 text-[13px] leading-snug text-muted">{description}</p>
          ) : null}
        </div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function CardBody({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("px-4 py-4 sm:px-5", className)} {...props} />;
}

export function CardFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 border-t border-line bg-sunken px-4 py-3 sm:px-5",
        className,
      )}
      {...props}
    />
  );
}

/** Single figure with a label — the icon at top right is the only accent. */
export function Stat({
  icon: Icon,
  label,
  value,
  note,
}: {
  icon?: LucideIcon;
  label: string;
  value: ReactNode;
  note?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[12px] font-medium uppercase tracking-wide text-muted">
          {label}
        </p>
        {Icon ? <Icon className="h-4 w-4 shrink-0 text-faint" aria-hidden /> : null}
      </div>
      <p className="nums mt-1 text-2xl font-semibold leading-none text-ink">{value}</p>
      {note ? <p className="mt-1.5 text-[12.5px] text-muted">{note}</p> : null}
    </div>
  );
}
