import type { Payment, PaymentMethod } from "../types";
import { normalisePhone } from "../format";
import { nextId } from "./store";

/**
 * Mobile money, mocked.
 *
 * Real integration is a two-step dance neither m-GURUSH nor Nilepay completes
 * synchronously: you push an STK-style prompt to the subscriber's handset, then
 * wait for a webhook to tell you whether they entered their PIN. This module
 * models that shape — `initiate` returns `pending`, and confirmation arrives
 * separately — so wiring the live API later does not change the UI's states.
 *
 * When MGURUSH_API_KEY / NILEPAY_API_KEY are unset (development), the mock is
 * used and payments auto-confirm after a short delay.
 */

const LIVE_KEYS: Record<PaymentMethod, string | undefined> = {
  mgurush: process.env.MGURUSH_API_KEY,
  nilepay: process.env.NILEPAY_API_KEY,
  bank_slip: undefined, // always manual
};

export const PAYMENT_METHODS: ReadonlyArray<{
  id: PaymentMethod;
  name: string;
  detail: string;
  /** Manual methods need a human at the bursary to clear them. */
  manual: boolean;
}> = [
  {
    id: "mgurush",
    name: "m-GURUSH",
    detail: "A prompt is sent to your phone. Enter your PIN to approve.",
    manual: false,
  },
  {
    id: "nilepay",
    name: "Nilepay",
    detail: "A prompt is sent to your phone. Enter your PIN to approve.",
    manual: false,
  },
  {
    id: "bank_slip",
    name: "Bank deposit slip",
    detail: "Deposit at any branch, then upload the slip. Cleared in 2 working days.",
    manual: true,
  },
];

export function methodName(method: PaymentMethod): string {
  return PAYMENT_METHODS.find((m) => m.id === method)?.name ?? method;
}

export type InitiateResult =
  | { ok: true; payment: Payment }
  | { ok: false; error: string };

/**
 * Push a payment request. Returns a `pending` payment for mobile money — the
 * subscriber still has to approve it on their handset.
 */
export async function initiatePayment(input: {
  method: PaymentMethod;
  amountSSP: number;
  phone?: string;
  /** Slip number, for manual bank deposits. */
  slipReference?: string;
}): Promise<InitiateResult> {
  const { method, amountSSP } = input;

  if (amountSSP <= 0) return { ok: false, error: "Enter an amount greater than zero." };

  if (method === "bank_slip") {
    const reference = input.slipReference?.trim();
    if (!reference) {
      return { ok: false, error: "Enter the deposit slip number printed on your receipt." };
    }
    return {
      ok: true,
      payment: {
        id: nextId("appay"),
        method,
        amountSSP,
        status: "pending",
        reference,
        createdAt: new Date().toISOString(),
      },
    };
  }

  const phone = normalisePhone(input.phone ?? "");
  if (!phone) {
    return {
      ok: false,
      error: "Enter a valid South Sudanese mobile number, for example 0920 123 456.",
    };
  }

  if (LIVE_KEYS[method]) {
    // Live provider call goes here. Left unimplemented deliberately rather than
    // stubbed with a fake success, so a misconfigured production deploy fails
    // loudly instead of telling a student their fee is paid.
    throw new Error(
      `${methodName(method)} live integration is not implemented. Unset its API key to use the mock provider.`,
    );
  }

  return {
    ok: true,
    payment: {
      id: nextId("appay"),
      method,
      amountSSP,
      status: "pending",
      reference: mockProviderReference(method),
      phone,
      createdAt: new Date().toISOString(),
    },
  };
}

/**
 * Stand-in for the provider webhook. In the mock, approval always succeeds.
 */
export async function confirmPayment(payment: Payment): Promise<Payment> {
  return {
    ...payment,
    status: "confirmed",
    confirmedAt: new Date().toISOString(),
  };
}

function mockProviderReference(method: PaymentMethod): string {
  const prefix = method === "mgurush" ? "MG" : "NP";
  const body = Array.from({ length: 8 }, () =>
    "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ".charAt(
      Math.floor(Math.random() * 34),
    ),
  ).join("");
  return `${prefix}${body}`;
}
