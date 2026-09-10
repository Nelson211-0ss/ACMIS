import type { Metadata } from "next";
import Link from "next/link";
import { Callout } from "@/components/ui/callout";
import { ResetPasswordForm } from "./form";

export const metadata: Metadata = { title: "Set a new password" };

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  if (!token) {
    return (
      <>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          Set a new password
        </h1>
        <Callout tone="error" className="mt-4" title="This link is incomplete">
          <p>
            It is missing the token that proves it came from us — usually a
            sign the address was copied only in part.
          </p>
          <Link
            href="/forgot-password"
            className="mt-2 inline-block font-semibold underline underline-offset-2"
          >
            Request a new link
          </Link>
        </Callout>
      </>
    );
  }

  return (
    <>
      <h1 className="text-[22px] font-semibold tracking-tight text-ink">
        Set a new password
      </h1>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">
        Choose something you have not used on this portal before. The link you
        followed stops working once this is saved.
      </p>

      <ResetPasswordForm token={token} />
    </>
  );
}
