import type { Metadata } from "next";
import { ForgotPasswordForm } from "./form";

export const metadata: Metadata = { title: "Forgot password" };

export default function ForgotPasswordPage() {
  return (
    <>
      <h1 className="text-[22px] font-semibold tracking-tight text-ink">
        Forgot your password
      </h1>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">
        Enter the address your account uses and we will send a link to set a
        new password. Students, applicants and staff all use this form.
      </p>

      <ForgotPasswordForm />
    </>
  );
}
