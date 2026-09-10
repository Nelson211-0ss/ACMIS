import Link from "next/link";
import { Wordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { institution } from "@/lib/institution";

/**
 * Chrome for the account pages that sit outside a session — registering,
 * asking for a reset link, and setting a new password. Same shape as the
 * sign-in screen so the three read as one flow rather than three detours.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 rounded-b-sm border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
          <Wordmark />
          <ThemeToggle />
        </div>
      </header>

      <main
        id="main"
        className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-10"
      >
        {children}

        <p className="mt-8 text-center text-[12.5px] text-muted">
          Stuck? Call{" "}
          <a
            href={`tel:${institution.supportPhone.replace(/\s/g, "")}`}
            className="font-medium text-brand-700 underline underline-offset-2"
          >
            {institution.supportPhone}
          </a>{" "}
          or{" "}
          <Link
            href="/login"
            className="font-medium text-brand-700 underline underline-offset-2"
          >
            go back to sign in
          </Link>
          .
        </p>
      </main>
    </div>
  );
}
