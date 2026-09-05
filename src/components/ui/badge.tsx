import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import type { ApplicationStatus, LetterGrade, PaymentStatus } from "@/lib/types";

type Tone = "neutral" | "brand" | "gold" | "green" | "red";

const TONES: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-soft border-line-strong",
  brand: "bg-brand-100 text-brand-800 border-brand-200",
  gold: "bg-gold-100 text-gold-700 border-gold-200",
  green: "bg-green-100 text-green-700 border-green-600/25",
  red: "bg-red-100 text-red-700 border-red-600/25",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[12px] font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const APPLICATION_STATUS: Record<
  ApplicationStatus,
  { label: string; tone: Tone }
> = {
  draft: { label: "Draft", tone: "neutral" },
  submitted: { label: "Submitted", tone: "brand" },
  under_review: { label: "Under review", tone: "brand" },
  interview: { label: "Interview scheduled", tone: "gold" },
  admitted: { label: "Admitted", tone: "green" },
  waitlisted: { label: "Waitlisted", tone: "gold" },
  rejected: { label: "Not offered", tone: "red" },
};

export function ApplicationStatusBadge({ status }: { status: ApplicationStatus }) {
  const { label, tone } = APPLICATION_STATUS[status];
  return <Badge tone={tone}>{label}</Badge>;
}

const PAYMENT_STATUS: Record<PaymentStatus, { label: string; tone: Tone }> = {
  unpaid: { label: "Unpaid", tone: "red" },
  pending: { label: "Awaiting confirmation", tone: "gold" },
  confirmed: { label: "Paid", tone: "green" },
  failed: { label: "Failed", tone: "red" },
};

export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  const { label, tone } = PAYMENT_STATUS[status];
  return <Badge tone={tone}>{label}</Badge>;
}

/**
 * Grade chip. Colour is a secondary cue only — the letter itself carries the
 * meaning, so this stays readable for colour-blind students and in print.
 */
export function GradeBadge({ grade }: { grade: LetterGrade }) {
  const tone: Tone =
    grade === "A" || grade === "B+"
      ? "green"
      : grade === "F" || grade === "E"
        ? "red"
        : "neutral";
  return (
    <span
      className={cn(
        "nums inline-flex h-6 min-w-8 items-center justify-center rounded-sm border px-1.5 text-[12.5px] font-semibold",
        TONES[tone],
      )}
    >
      {grade}
    </span>
  );
}
