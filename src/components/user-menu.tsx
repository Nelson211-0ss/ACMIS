import Link from "next/link";
import { LogOut } from "lucide-react";
import { Avatar } from "@/components/ui/avatar";
import { cn } from "@/lib/cn";
import { signOut } from "@/app/login/actions";

/** Just the fields this renders — a `Student` or a `StaffUser` both satisfy it. */
interface UserMenuSubject {
  firstName: string;
  lastName: string;
  /** Shown under the name: a student number for students, an email for staff. */
  identifier: string;
  photoUrl?: string;
}

/**
 * Who you are signed in as, top right.
 *
 * The name and identifier are hidden below `sm` — on a 360px screen the
 * avatar alone is the affordance, and the same details are one tap away on the
 * page it links to.
 */
export function UserMenu({
  subject,
  href = "/portal/profile",
  className,
}: {
  subject: UserMenuSubject;
  href?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Link
        href={href}
        className="flex items-center gap-2.5 rounded px-1.5 py-1 transition-colors hover:bg-sunken"
      >
        <span className="hidden min-w-0 text-right sm:block">
          <span className="block truncate text-[13px] font-medium text-ink">
            {subject.firstName} {subject.lastName}
          </span>
          <span className="nums block truncate text-[11.5px] text-muted">
            {subject.identifier}
          </span>
        </span>
        <Avatar
          firstName={subject.firstName}
          lastName={subject.lastName}
          photoUrl={subject.photoUrl}
        />
      </Link>

      <form action={signOut}>
        <button
          type="submit"
          title="Sign out"
          className="inline-flex h-9 w-9 items-center justify-center rounded text-muted transition-colors hover:bg-sunken hover:text-ink"
        >
          <LogOut className="h-4 w-4" aria-hidden />
          <span className="sr-only">Sign out</span>
        </button>
      </form>
    </div>
  );
}
