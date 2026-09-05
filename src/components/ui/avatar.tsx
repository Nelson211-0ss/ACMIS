import Image from "next/image";
import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";

type AvatarSize = "sm" | "md" | "lg" | "xl";

/** Box, type scale and intrinsic pixel width per step. */
const SIZES: Record<AvatarSize, { box: string; text: string; px: number }> = {
  sm: { box: "h-9 w-9", text: "text-[13px]", px: 36 },
  md: { box: "h-14 w-14", text: "text-[18px]", px: 56 },
  lg: { box: "h-20 w-20", text: "text-[26px]", px: 80 },
  xl: { box: "h-28 w-28", text: "text-[34px]", px: 112 },
};

/**
 * Student avatar: the photograph on file, or initials when there is none.
 *
 * No photograph is the normal case rather than an error state — admissions
 * collects passport photos on paper, and a record digitised from a paper file
 * has no image at all. So the initials tile is a first-class rendering, not a
 * placeholder waiting to be replaced.
 */
export function Avatar({
  firstName,
  lastName,
  photoUrl,
  size = "sm",
  className,
}: {
  firstName: string;
  lastName: string;
  photoUrl?: string;
  size?: AvatarSize;
  className?: string;
}) {
  const { box, text, px } = SIZES[size];

  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-lg bg-brand-700 font-semibold text-white",
        box,
        text,
        className,
      )}
    >
      {photoUrl ? (
        <Image
          src={photoUrl}
          alt={`${firstName} ${lastName}`}
          width={px}
          height={px}
          className="h-full w-full object-cover"
        />
      ) : (
        initials(firstName, lastName)
      )}
    </span>
  );
}
