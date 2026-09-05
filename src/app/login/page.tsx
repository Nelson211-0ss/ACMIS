import type { Metadata } from "next";
import Link from "next/link";
import { GraduationCap, ShieldCheck, UserPlus } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardFooter } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { DEMO_ACCOUNTS } from "@/lib/auth";
import { institution } from "@/lib/institution";
import { signIn, signInAsDemo } from "./actions";
import { SignInForm } from "./form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
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
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Sign in
        </h1>
        <p className="mt-1.5 text-[13.5px] text-muted">
          Use the email address registered with {institution.short}, or your
          student number.
        </p>

        <SignInForm action={signIn} className="mt-6" />

        <div className="my-7 flex items-center gap-3" aria-hidden>
          <span className="h-px flex-1 bg-line" />
          <span className="text-[12px] font-medium uppercase tracking-wide text-faint">
            or explore a seeded account
          </span>
          <span className="h-px flex-1 bg-line" />
        </div>

        <Callout tone="warning" className="mb-4" title="Development build">
          Passwords are not checked in this build. Do not connect it to real
          student records until mock authentication is replaced.
        </Callout>

        <div className="space-y-2.5">
          <form action={signInAsDemo}>
            <input type="hidden" name="role" value="student" />
            <Button type="submit" variant="secondary" block>
              <GraduationCap className="h-4 w-4" aria-hidden />
              {DEMO_ACCOUNTS.student.label}
            </Button>
          </form>
          <form action={signInAsDemo}>
            <input type="hidden" name="role" value="applicant" />
            <Button type="submit" variant="secondary" block>
              <UserPlus className="h-4 w-4" aria-hidden />
              {DEMO_ACCOUNTS.applicant.label}
            </Button>
          </form>
          <form action={signInAsDemo}>
            <input type="hidden" name="role" value="admin" />
            <Button type="submit" variant="secondary" block>
              <ShieldCheck className="h-4 w-4" aria-hidden />
              {DEMO_ACCOUNTS.admin.label}
            </Button>
          </form>
        </div>

        <p className="mt-4 text-center text-[12.5px] text-muted">
          Work in the Admissions Office?{" "}
          <Link href="/admissions/login" className="font-medium text-brand-700 underline underline-offset-2">
            Sign in there instead
          </Link>
          .
        </p>

        <Card className="mt-8">
          <CardBody>
            <h2 className="text-[14px] font-semibold text-ink">
              Applying for the first time?
            </h2>
            <p className="mt-1 text-[13px] leading-snug text-muted">
              You do not need an account to start. Begin an application and we
              will create one for you.
            </p>
          </CardBody>
          <CardFooter>
            <ButtonLink href="/apply" size="sm">
              Start an application
            </ButtonLink>
          </CardFooter>
        </Card>

        <p className="mt-6 text-center text-[12.5px] text-muted">
          Trouble signing in? Call{" "}
          <a
            href={`tel:${institution.supportPhone.replace(/\s/g, "")}`}
            className="font-medium text-brand-700 underline underline-offset-2"
          >
            {institution.supportPhone}
          </a>{" "}
          or{" "}
          <Link href="/" className="font-medium text-brand-700 underline underline-offset-2">
            go back
          </Link>
          .
        </p>
      </main>
    </div>
  );
}
