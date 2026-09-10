import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "warning" | "error";

const TONES: Record<Tone, { box: string; icon: string; Icon: typeof Info }> = {
  info: {
    box: "border-brand-200 bg-brand-50 text-brand-900",
    icon: "text-brand-600",
    Icon: Info,
  },
  success: {
    box: "border-green-600/25 bg-green-100 text-green-700",
    icon: "text-green-600",
    Icon: CheckCircle2,
  },
  warning: {
    box: "border-gold-200 bg-gold-100 text-gold-700",
    icon: "text-gold-600",
    Icon: AlertTriangle,
  },
  error: {
    box: "border-red-600/25 bg-red-100 text-red-700",
    icon: "text-red-600",
    Icon: XCircle,
  },
};

/**
 * Inline message. Flat tinted fill plus a hairline border in the same hue —
 * no gradient, and the icon repeats the meaning so colour is never the only
 * signal.
 */
export function Callout({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const { box, icon, Icon } = TONES[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded border px-3.5 py-3",
        box,
        className,
      )}
    >
      <Icon className={cn("mt-0.5 h-[18px] w-[18px] shrink-0", icon)} aria-hidden />
      <div className="min-w-0 text-[13.5px] leading-snug">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className={cn(title && "mt-1")}>{children}</div> : null}
      </div>
    </div>
  );
}
