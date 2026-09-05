import type { Metadata } from "next";
import Link from "next/link";
import { ClipboardCheck } from "lucide-react";
import { Crest } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { institution } from "@/lib/institution";
import { signInAdmissions, signInAdmissionsDemo } from "./actions";
import { SignInForm } from "@/app/login/form";

export const metadata: Metadata = { title: "Admissions Office sign-in" };

/**
 * The Admissions Office's own portal front door — a separate URL from the
 * general staff/student sign-in at `/login`, so the people who run intake do
 * not share a screen (or a mental model) with IT administration.
 */
export default function AdmissionsLoginPage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 rounded-b-sm border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
          <Link href="/" className="flex min-w-0 items-center gap-2.5">
            <Crest className="shrink-0" />
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-[14.5px] font-semibold text-ink">
                {institution.name}
              </span>
              <span className="block truncate text-[11.5px] text-muted">
                Admissions Office
              </span>
            </span>
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main
        id="main"
        className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-10"
      >
        <span className="mb-3 flex h-10 w-10 items-center justify-center rounded border border-brand-200 bg-brand-50">
          <ClipboardCheck className="h-5 w-5 text-brand-700" aria-hidden />
        </span>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Admissions Office sign-in
        </h1>
        <p className="mt-1.5 text-[13.5px] text-muted">
          For staff who publish admission schemes and review applications.
        </p>

        <SignInForm
          action={signInAdmissions}
          emailLabel="Work email address"
          emailPlaceholder="daniel.kuek@uoj.example.ss"
          className="mt-6"
        />

        <div className="my-7 flex items-center gap-3" aria-hidden>
          <span className="h-px flex-1 bg-line" />
          <span className="text-[12px] font-medium uppercase tracking-wide text-faint">
            or explore a seeded account
          </span>
          <span className="h-px flex-1 bg-line" />
        </div>

        <Callout tone="warning" className="mb-4" title="Development build">
          Passwords are not checked in this build. Do not connect it to real
          applicant records until mock authentication is replaced.
        </Callout>

        <form action={signInAdmissionsDemo}>
          <Button type="submit" variant="secondary" block>
            <ClipboardCheck className="h-4 w-4" aria-hidden />
            Daniel Kuek — Registrar
          </Button>
        </form>

        <p className="mt-6 text-center text-[12.5px] text-muted">
          Not admissions staff? Use the{" "}
          <Link href="/login" className="font-medium text-brand-700 underline underline-offset-2">
            general staff and student sign-in
          </Link>
          .
        </p>
      </main>
    </div>
  );
}
