import type { Metadata } from "next";
import Link from "next/link";
import {
  Award,
  Banknote,
  ClipboardCheck,
  GraduationCap,
  LifeBuoy,
  Presentation,
  ShieldCheck,
  Stamp,
  UserPlus,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Wordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardFooter } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, type DemoAccountKey } from "@/lib/demo-accounts";
import { institution } from "@/lib/institution";
import { getBranding } from "@/lib/data/repo";
import { signIn, signInAsDemo } from "./actions";
import { SignInForm } from "./form";

export const metadata: Metadata = { title: "Sign in" };

/** Icon per seeded account, in the order they read as a hierarchy. */
const DEMO_ICONS: Array<{ key: DemoAccountKey; icon: LucideIcon }> = [
  { key: "student", icon: GraduationCap },
  { key: "applicant", icon: UserPlus },
  { key: "alumni", icon: Award },
  { key: "admin", icon: ShieldCheck },
  { key: "registrar", icon: ClipboardCheck },
  { key: "head_of_department", icon: Stamp },
  { key: "lecturer", icon: Presentation },
  { key: "bursar", icon: Banknote },
  { key: "it_support", icon: LifeBuoy },
];

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const branding = await getBranding();

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
          Use the email address registered with {branding.short}.
        </p>

        {error ? (
          <Callout tone="error" className="mt-4" title="Could not sign in">
            {error}
          </Callout>
        ) : null}

        <SignInForm action={signIn} className="mt-6" />

        <p className="mt-3 text-[12.5px] text-muted">
          <Link
            href="/forgot-password"
            className="font-medium text-brand-700 underline underline-offset-2"
          >
            Forgot your password?
          </Link>
        </p>

        <div className="my-7 flex items-center gap-3" aria-hidden>
          <span className="h-px flex-1 bg-line" />
          <span className="text-[12px] font-medium uppercase tracking-wide text-faint">
            or explore a seeded account
          </span>
          <span className="h-px flex-1 bg-line" />
        </div>

        <Callout tone="info" className="mb-4" title="Demonstration data">
          Every seeded account below uses the password{" "}
          <span className="nums font-semibold">{DEMO_PASSWORD}</span>, and these
          buttons sign in with it through the same password check as the form
          above. Seed accounts belong in a demo only — a real deployment starts
          with none.
        </Callout>

        <div className="space-y-2.5">
          {DEMO_ICONS.map(({ key, icon: Icon }) => (
            <form action={signInAsDemo} key={key}>
              <input type="hidden" name="role" value={key} />
              <Button type="submit" variant="secondary" block>
                <Icon className="h-4 w-4" aria-hidden />
                {DEMO_ACCOUNTS[key].label}
              </Button>
            </form>
          ))}
        </div>

        <p className="mt-4 text-center text-[12.5px] text-muted">
          Admissions Office also has its{" "}
          <Link href="/admissions/login" className="font-medium text-brand-700 underline underline-offset-2">
            own dedicated sign-in
          </Link>
          .
        </p>

        <Card className="mt-8">
          <CardBody>
            <h2 className="text-[14px] font-semibold text-ink">
              Applying for the first time?
            </h2>
            <p className="mt-1 text-[13px] leading-snug text-muted">
              Create an applicant account with your email address, then start
              your application. You can come back to it any time.
            </p>
          </CardBody>
          <CardFooter>
            <ButtonLink href="/register" size="sm">
              Create an account
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
