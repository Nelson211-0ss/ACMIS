import Image from "next/image";
import { User } from "lucide-react";
import { cn } from "@/lib/cn";

type AvatarSize = "sm" | "md" | "lg" | "xl";

/** Box, icon scale and intrinsic pixel width per step. */
const SIZES: Record<AvatarSize, { box: string; icon: string; px: number }> = {
  sm: { box: "h-9 w-9", icon: "h-[18px] w-[18px]", px: 36 },
  md: { box: "h-14 w-14", icon: "h-7 w-7", px: 56 },
  lg: { box: "h-20 w-20", icon: "h-10 w-10", px: 80 },
  xl: { box: "h-28 w-28", icon: "h-14 w-14", px: 112 },
};

/**
 * Student avatar: the photograph on file, or a neutral person mark when there
 * is none.
 *
 * No photograph is the normal case rather than an error state — admissions
 * collects passport photos on paper, and a record digitised from a paper file
 * has no image at all. So the placeholder is a first-class rendering, not
 * something waiting to be replaced: a sunken tile with the same hairline every
 * other surface uses, rather than a loud brand-filled block.
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
  const { box, icon, px } = SIZES[size];

  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-lg",
        photoUrl ? "bg-sunken" : "border border-line bg-sunken text-muted",
        box,
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
        <>
          <User className={cn(icon, "shrink-0")} strokeWidth={1.75} aria-hidden />
          {/* UserMenu hides the name below `sm`, leaving the avatar as the
              link's only content — without this the link would have no
              accessible name at all on a phone. */}
          <span className="sr-only">{`${firstName} ${lastName}`}</span>
        </>
      )}
    </span>
  );
}
