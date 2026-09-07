import { LogOut, Phone } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { OfflineBanner } from "@/components/offline-form";
import { ThemeToggle } from "@/components/theme-toggle";
import { currentSession } from "@/lib/auth";
import { institution } from "@/lib/institution";
import { getBranding } from "@/lib/data/repo";
import { signOut } from "@/app/login/actions";

export default async function ApplyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await currentSession();
  const branding = await getBranding();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 rounded-b-sm border-b border-line bg-surface">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Wordmark href="/" />
          <div className="flex shrink-0 items-center gap-1">
            <ThemeToggle />
            {session ? (
              <form action={signOut}>
                <button
                  type="submit"
                  className="inline-flex items-center gap-1.5 rounded px-2.5 py-2 text-[13px] font-medium text-muted transition-colors hover:bg-sunken hover:text-ink"
                >
                  <LogOut className="h-4 w-4" aria-hidden />
                  <span className="hidden sm:inline">Sign out</span>
                </button>
              </form>
            ) : null}
          </div>
        </div>
      </header>

      <OfflineBanner />

      <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        {children}
      </main>

      {/* Static, not sticky: a form this long should not spend ~60px of a
          phone screen on a phone number wanted once, at the end. */}
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-4xl flex-col gap-2 px-4 py-5 text-[12.5px] text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>
            {branding.name} · Admissions office, {branding.city}
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
