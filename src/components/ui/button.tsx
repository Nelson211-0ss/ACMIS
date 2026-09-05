import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "gold";
type Size = "sm" | "md" | "lg";

/**
 * Flat button. Depth comes from a solid fill and a hairline border — never a
 * gradient. Hover shifts the fill one step; active shifts it two.
 */
const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand-700 text-white border-brand-700 hover:bg-brand-800 hover:border-brand-800 active:bg-brand-900 dark:text-brand-50",
  secondary:
    "bg-surface text-ink border-line-strong hover:bg-sunken active:bg-sunken",
  ghost:
    "bg-transparent text-ink-soft border-transparent hover:bg-sunken hover:text-ink",
  danger:
    "bg-red-600 text-white border-red-600 hover:bg-red-700 hover:border-red-700",
  gold:
    "bg-gold-500 text-brand-900 border-gold-500 hover:bg-gold-600 hover:border-gold-600 hover:text-white",
};

const SIZES: Record<Size, string> = {
  // 44px minimum touch target on md and up — these will be tapped with thumbs.
  sm: "h-9 px-3 text-[13px] gap-1.5",
  md: "h-11 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-[15px] gap-2",
};

const BASE =
  "inline-flex items-center justify-center rounded border font-medium " +
  "transition-[color,background-color,border-color,transform] duration-100 select-none " +
  "motion-safe:active:scale-[0.97] " +
  "disabled:opacity-50 disabled:pointer-events-none " +
  "aria-disabled:opacity-50 aria-disabled:pointer-events-none";

interface Common {
  variant?: Variant;
  size?: Size;
  /** Stretch to the container. Used for the mobile form footers. */
  block?: boolean;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  block,
  className,
  ...props
}: Common & ComponentProps<"button">) {
  return (
    <button
      className={cn(BASE, VARIANTS[variant], SIZES[size], block && "w-full", className)}
      {...props}
    />
  );
}

export function ButtonLink({
  variant = "primary",
  size = "md",
  block,
  className,
  ...props
}: Common & ComponentProps<typeof Link>) {
  return (
    <Link
      className={cn(BASE, VARIANTS[variant], SIZES[size], block && "w-full", className)}
      {...props}
    />
  );
}
