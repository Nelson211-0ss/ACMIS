import type { Metadata } from "next";
import Link from "next/link";
import { getBranding } from "@/lib/data/repo";
import { RegisterForm } from "./form";

export const metadata: Metadata = { title: "Create an account" };

export default async function RegisterPage() {
  const branding = await getBranding();

  return (
    <>
      <h1 className="text-[22px] font-semibold tracking-tight text-ink">
        Create an applicant account
      </h1>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">
        One account for every application you make to {branding.short}. You can
        save an application part-finished and come back to it.
      </p>

      <RegisterForm />

      <p className="mt-4 text-center text-[12.5px] text-muted">
        Already have one?{" "}
        <Link
          href="/login"
          className="font-medium text-brand-700 underline underline-offset-2"
        >
          Sign in instead
        </Link>
        .
      </p>
    </>
  );
}
