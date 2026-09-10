import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

const CONTROL =
  "w-full rounded border border-line-strong bg-surface px-3 text-[15px] text-ink " +
  "placeholder:text-faint transition-colors " +
  "hover:border-brand-300 focus:border-brand-500 focus:outline-none " +
  "focus:ring-2 focus:ring-brand-500/25 " +
  "disabled:bg-sunken disabled:text-muted " +
  "aria-[invalid=true]:border-red-600 aria-[invalid=true]:ring-red-600/20";

/**
 * Label, control and message wrapper.
 *
 * `error` is rendered with `role="alert"` and wired to the control through
 * aria-describedby by the caller passing the same `name`, so screen readers
 * announce validation failures. 16px control text keeps iOS from zooming the
 * viewport on focus.
 */
export function Field({
  label,
  name,
  hint,
  error,
  required,
  children,
  className,
}: {
  label: string;
  name: string;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <label
        htmlFor={name}
        className="mb-1.5 block text-[13px] font-medium text-ink-soft"
      >
        {label}
        {required ? (
          <span className="ml-1 text-red-600" aria-hidden>
            *
          </span>
        ) : (
          <span className="ml-1.5 text-[12px] font-normal text-faint">optional</span>
        )}
      </label>
      {children}
      {hint && !error ? (
        <p id={`${name}-hint`} className="mt-1.5 text-[12.5px] text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p
          id={`${name}-error`}
          role="alert"
          className="mt-1.5 text-[12.5px] font-medium text-red-700"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(CONTROL, "h-11", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(CONTROL, "min-h-24 py-2.5", className)} {...props} />;
}

export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <div className="relative">
      <select
        className={cn(CONTROL, "h-11 appearance-none pr-9", className)}
        {...props}
      >
        {children}
      </select>
      <svg
        aria-hidden
        viewBox="0 0 20 20"
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
      >
        <path d="M6 8l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

/** Radio or checkbox rendered as a tappable bordered row. */
export function ChoiceRow({
  label,
  description,
  checked,
  disabled,
  children,
}: {
  label: ReactNode;
  description?: ReactNode;
  checked?: boolean;
  disabled?: boolean;
  /** The actual input element. */
  children: ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded border px-3.5 py-3 transition-colors",
        checked
          ? "border-brand-500 bg-brand-50"
          : "border-line-strong bg-surface hover:border-brand-300 hover:bg-brand-50/50",
        disabled && "cursor-not-allowed opacity-55 hover:border-line-strong hover:bg-surface",
      )}
    >
      <span className="mt-0.5 shrink-0">{children}</span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink">{label}</span>
        {description ? (
          <span className="mt-0.5 block text-[12.5px] leading-snug text-muted">
            {description}
          </span>
        ) : null}
      </span>
    </label>
  );
}

/** Consistent grid for form rows: one column on phones, two from `sm`. */
export function FieldGrid({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn("grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2", className)}
      {...props}
    />
  );
}
