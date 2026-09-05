import type { ComponentProps, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

/** Flat surface, hairline border, no shadow by default. */
export function Card({ className, ...props }: ComponentProps<"section">) {
  return (
    <section
      className={cn(
        "rounded-lg border border-line bg-surface",
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

/**
 * Single figure with a label. The accent bar on the left is a solid 3px fill —
 * the flat-design substitute for a coloured gradient header.
 */
export function Stat({
  icon: Icon,
  label,
  value,
  note,
  accent = "brand",
}: {
  icon?: LucideIcon;
  label: string;
  value: ReactNode;
  note?: ReactNode;
  accent?: "brand" | "gold" | "green" | "red" | "none";
}) {
  const bar = {
    brand: "bg-brand-700",
    gold: "bg-gold-500",
    green: "bg-green-600",
    red: "bg-red-600",
    none: "bg-line-strong",
  }[accent];

  return (
    <div className="relative overflow-hidden rounded-lg border border-line bg-surface px-4 py-3.5 pl-5">
      <span className={cn("absolute inset-y-0 left-0 w-[3px]", bar)} aria-hidden />
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
