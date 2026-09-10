import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/**
 * Table in a horizontally scrollable shell.
 *
 * Wide data is the one thing that breaks a phone layout, so every table scrolls
 * inside its own box rather than letting the page scroll sideways.
 */
export function TableWrap({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn("scroll-thin -mx-px overflow-x-auto", className)}
      {...props}
    />
  );
}

export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <table
      className={cn("w-full min-w-full border-collapse text-sm", className)}
      {...props}
    />
  );
}

export function Th({ className, ...props }: ComponentProps<"th">) {
  return (
    <th
      className={cn(
        "border-b border-line bg-sunken px-3 py-2.5 text-left text-[12px] font-semibold uppercase tracking-wide text-muted whitespace-nowrap first:pl-4 last:pr-4",
        className,
      )}
      {...props}
    />
  );
}

export function Td({ className, ...props }: ComponentProps<"td">) {
  return (
    <td
      className={cn(
        "border-b border-line px-3 py-3 align-middle text-ink first:pl-4 last:pr-4",
        className,
      )}
      {...props}
    />
  );
}

export function Tr({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      className={cn("transition-colors hover:bg-brand-50/60 last:[&>td]:border-0", className)}
      {...props}
    />
  );
}
