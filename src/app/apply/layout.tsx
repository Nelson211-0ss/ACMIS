import { LogOut, Phone } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { OfflineBanner } from "@/components/offline-form";
import { currentSession } from "@/lib/auth";
import { institution } from "@/lib/institution";
import { signOut } from "@/app/login/actions";

export default async function ApplyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await currentSession();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-surface">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Wordmark href="/" />
          {session ? (
            <form action={signOut}>
              <button
                type="submit"
                className="inline-flex items-center gap-1.5 rounded-[--radius] px-2.5 py-2 text-[13px] font-medium text-muted transition-colors hover:bg-sunken hover:text-ink"
              >
                <LogOut className="h-4 w-4" aria-hidden />
                <span className="hidden sm:inline">Sign out</span>
              </button>
            </form>
          ) : null}
        </div>
      </header>

      <OfflineBanner />

      <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-4 py-5 sm:px-6">
        {children}
      </main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-4xl flex-col gap-2 px-4 py-5 text-[12.5px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>
            {institution.name} · Admissions office, {institution.city}
          </p>
          <p className="flex items-center gap-1.5">
            <Phone className="h-3.5 w-3.5" aria-hidden />
            <a
              href={`tel:${institution.supportPhone.replace(/\s/g, "")}`}
              className="font-medium text-brand-700 underline underline-offset-2"
            >
              {institution.supportPhone}
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
