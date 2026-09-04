"use server";

import { revalidatePath } from "next/cache";
import { currentStudent } from "@/lib/auth";
import { recordFeePayment } from "@/lib/data/repo";
import { confirmPayment, initiatePayment, methodName } from "@/lib/data/payments";
import type { PaymentMethod } from "@/lib/types";
import { ssp } from "@/lib/format";

export type PayState =
  | { ok: true; message: string }
  | { ok: false; message: string }
  | undefined;

const METHODS: PaymentMethod[] = ["mgurush", "nilepay", "bank_slip"];

/**
 * Pay against the fee account.
 *
 * Mobile money is initiated then confirmed in one call here because the mock
 * provider settles instantly. With a live provider the confirmation arrives on
 * a webhook, so the second half moves out of this action and the payment sits
 * at `pending` until then — which the UI already renders correctly.
 */
export async function payFees(
  _prev: PayState,
  formData: FormData,
): Promise<PayState> {
  const student = await currentStudent();
  if (!student) return { ok: false, message: "Your session has expired. Sign in again." };

  const method = String(formData.get("method") ?? "") as PaymentMethod;
  if (!METHODS.includes(method)) {
    return { ok: false, message: "Choose how you want to pay." };
  }

  const amount = Number(formData.get("amount"));
  if (!Number.isFinite(amount) || amount <= 0) {
    return { ok: false, message: "Enter the amount you are paying." };
  }

  const initiated = await initiatePayment({
    method,
    amountSSP: Math.round(amount),
    phone: String(formData.get("phone") ?? ""),
    slipReference: String(formData.get("slip") ?? ""),
  });

  if (!initiated.ok) return { ok: false, message: initiated.error };

  const settled =
    method === "bank_slip" ? initiated.payment : await confirmPayment(initiated.payment);

  await recordFeePayment(
    student.id,
    settled.amountSSP,
    method,
    settled.reference ?? "—",
  );

  revalidatePath("/portal/finance");
  revalidatePath("/portal");
  revalidatePath("/portal/results");
  revalidatePath("/portal/registration");

  return {
    ok: true,
    message:
      method === "bank_slip"
        ? `Slip ${settled.reference} recorded for ${ssp(settled.amountSSP)}. The bursary will confirm it within two working days.`
        : `${ssp(settled.amountSSP)} received by ${methodName(method)}. Reference ${settled.reference}.`,
  };
}
