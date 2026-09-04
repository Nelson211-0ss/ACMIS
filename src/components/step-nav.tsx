"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check } from "lucide-react";
import { cn } from "@/lib/cn";
import { STEPS, type StepSlug } from "@/lib/application";

/**
 * Wizard navigation.
 *
 * Steps are never locked: an applicant may fill them in any order, and hiding
 * later steps behind earlier ones just makes people abandon the form when they
 * cannot find the marksheet they need for step 2.
 *
 * On a phone this is a horizontally scrolling strip of numbered pills; from
 * `lg` it becomes a vertical list with hints.
 */
export function StepNav({
  applicationId,
  completed,
  readOnly,
}: {
  applicationId: string;
  completed: StepSlug[];
  /** Submitted applications show the strip but cannot be edited. */
  readOnly?: boolean;
}) {
  const pathname = usePathname();
  const done = new Set(completed);
  const currentIndex = STEPS.findIndex((s) =>
    pathname.endsWith(`/${s.slug}`),
  );

  return (
    <>
      {/* Phone: scrolling pills */}
      <nav aria-label="Application steps" className="lg:hidden">
        <ol className="scroll-thin -mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
          {STEPS.map((step, i) => {
            const active = i === currentIndex;
            const complete = done.has(step.slug);
            return (
              <li key={step.slug} className="shrink-0">
                <Link
                  href={`/apply/${applicationId}/${step.slug}`}
                  aria-current={active ? "step" : undefined}
                  className={cn(
                    "flex items-center gap-2 rounded-full border px-3 py-2 text-[12.5px] font-medium transition-colors",
                    active
                      ? "border-brand-700 bg-brand-700 text-white"
                      : complete
                        ? "border-green-600/30 bg-green-100 text-green-700"
                        : "border-line-strong bg-surface text-muted",
                  )}
                >
                  {complete && !active ? (
                    <Check className="h-3.5 w-3.5" aria-hidden />
                  ) : (
                    <span className="nums">{i + 1}</span>
                  )}
                  <span className="whitespace-nowrap">{step.label}</span>
                </Link>
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Desktop: vertical list */}
      <nav aria-label="Application steps" className="hidden lg:block">
        <ol className="space-y-1">
          {STEPS.map((step, i) => {
            const active = i === currentIndex;
            const complete = done.has(step.slug);
            return (
              <li key={step.slug}>
                <Link
                  href={`/apply/${applicationId}/${step.slug}`}
                  aria-current={active ? "step" : undefined}
                  className={cn(
                    "relative flex items-start gap-3 rounded-[--radius] px-3 py-2.5 transition-colors",
                    active ? "bg-brand-50" : "hover:bg-sunken",
                  )}
                >
                  {active ? (
                    <span
                      className="absolute left-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-r bg-brand-700"
                      aria-hidden
                    />
                  ) : null}
                  <span
                    className={cn(
                      "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold",
                      complete
                        ? "border-green-600 bg-green-600 text-white"
                        : active
                          ? "border-brand-700 bg-brand-700 text-white"
                          : "border-line-strong bg-surface text-muted",
                    )}
                  >
                    {complete ? (
                      <Check className="h-3 w-3" aria-hidden />
                    ) : (
                      <span className="nums">{i + 1}</span>
                    )}
                  </span>
                  <span className="min-w-0">
                    <span
                      className={cn(
                        "block text-[13.5px] leading-snug",
                        active ? "font-semibold text-brand-800" : "font-medium text-ink",
                      )}
                    >
                      {step.label}
                    </span>
                    <span className="mt-0.5 block text-[12px] leading-snug text-muted">
                      {step.hint}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
        {readOnly ? (
          <p className="mt-3 px-3 text-[12px] leading-snug text-muted">
            This application has been submitted and can no longer be edited.
          </p>
        ) : null}
      </nav>
    </>
  );
}
