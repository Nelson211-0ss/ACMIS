import { ApiError, TransportError } from "./errors"

/**
 * A call that was attempted, and what came back.
 *
 * ## Why this exists
 *
 * Every dashboard in ACMIS was written as
 *
 *     client.finance.unmatchedPayments().catch(() => null)
 *
 * and then summed over `?.items ?? []`. That collapses three different
 * outcomes — *no rows*, *you may not see this*, and *the service is down* —
 * into one value, before any component gets a chance to tell them apart. The
 * result is the most reassuring screen in the system: with the ledger
 * unreachable the bursar's overview reported `USh 0` unmatched and `0`
 * invoices overdue, which is not a smaller number than the truth, it is the
 * opposite of it.
 *
 * No component can draw a distinction the data no longer carries, so the fix
 * has to start here rather than in the markup. `attempt` keeps the distinction
 * and hands the page a `problem` it can pass straight to a `StatTile`,
 * a `ChartFrame` or a `DataTable`.
 *
 * ## What it deliberately does not catch
 *
 * Two classes of failure go straight past it.
 *
 * A **401** is not a problem a tile can draw. The session has lapsed and the
 * only useful response is to send the person to sign in, which the auth layer
 * already does when the error reaches it. Swallowing it here would replace
 * that redirect with a page of dashes.
 *
 * **Anything that is not an `ApiError` or a `TransportError`** is a defect in
 * our own code — a `TypeError` reading a field that moved, say. Those belong
 * in `error.tsx` where they are visible, not softened into "the service did
 * not respond", which would send staff chasing a network fault that does not
 * exist.
 */

export type ProblemKind =
  /** The API refused the read. It does not say why, and neither do we. */
  | "forbidden"
  /** The record is gone, or never existed under this id. */
  | "missing"
  /** An academic or financial rule refused — the fix is an approval. */
  | "refused"
  /** Nothing answered: a timeout, a DNS failure, a proxy error page. */
  | "unreachable"
  /** The service answered, with a failure. */
  | "failed"

export interface Problem {
  kind: ProblemKind
  /**
   * One sentence, addressed to a member of staff rather than to an engineer.
   * Short enough to sit under a figure in an 11px footnote.
   */
  reason: string
  /** Echoed from `x-request-id`, so a support ticket can name one request. */
  requestId: string | null
  /**
   * Whether trying again could plausibly work. A timeout, yes; a permission
   * refusal, no. Drives whether a surface offers a retry at all — an
   * affordance that cannot help is worse than none, because a clerk will use
   * it four times before asking anyone.
   */
  retryable: boolean
}

export type Outcome<T> =
  | { ok: true; data: T; problem: null }
  | { ok: false; data: null; problem: Problem; error: ApiError | TransportError }

/** "the ledger" -> "The ledger"; used to open a sentence. */
function opening(subject: string | undefined, fallback: string): string {
  if (!subject) return fallback
  return subject.charAt(0).toUpperCase() + subject.slice(1)
}

/**
 * Describe a failure in terms a registry clerk can act on.
 *
 * `subject` names the thing that was being fetched, as a noun phrase that can
 * open a sentence: `"the ledger"` gives "The ledger did not respond." Leave it
 * out and the message falls back to "The service", which is true but tells
 * nobody which of four calls on the page is the one that failed.
 */
export function describe(error: ApiError | TransportError, subject?: string): Problem {
  if (error instanceof TransportError) {
    return {
      kind: "unreachable",
      reason: `${opening(subject, "The service")} did not respond.`,
      requestId: null,
      retryable: true,
    }
  }

  if (error.isForbidden) {
    return {
      kind: "forbidden",
      reason: "You do not have permission to see this.",
      requestId: error.requestId,
      retryable: false,
    }
  }

  if (error.status === 404) {
    return {
      kind: "missing",
      reason: `${opening(subject, "This")} is no longer available.`,
      requestId: error.requestId,
      retryable: false,
    }
  }

  if (error.isRuleViolation) {
    // The API's own wording. A rule refusal is the one case where the message
    // is written for the reader rather than for the log, and rephrasing it
    // would lose the detail that makes it actionable.
    return {
      kind: "refused",
      reason: error.message,
      requestId: error.requestId,
      retryable: false,
    }
  }

  return {
    kind: "failed",
    reason: `${opening(subject, "The service")} could not return this.`,
    requestId: error.requestId,
    // 4xx will fail again the same way; 5xx may not.
    retryable: error.status >= 500,
  }
}

/**
 * Run a call and keep what happened.
 *
 * ```ts
 * const [unmatched, trial] = await Promise.all([
 *   attempt(client.finance.unmatchedPayments({ limit: 100 }), "the ledger"),
 *   attempt(client.finance.trialBalance(period), "the ledger"),
 * ])
 *
 * <StatTile
 *   label="Unmatched money"
 *   value={money(total(unmatched.data), currency)}
 *   unavailable={unmatched.problem}
 * />
 * ```
 *
 * `Promise.all` over attempts never rejects for an API failure, so one tile
 * failing does not cost the page the other three — which is the normal case on
 * a dashboard that fans out to four services.
 */
export async function attempt<T>(promise: Promise<T>, subject?: string): Promise<Outcome<T>> {
  try {
    const data = await promise
    return { ok: true, data, problem: null }
  } catch (error) {
    if (error instanceof ApiError) {
      // See the note above: a lapsed session is the auth layer's business.
      if (error.isUnauthenticated) throw error
      return { ok: false, data: null, problem: describe(error, subject), error }
    }
    if (error instanceof TransportError) {
      return { ok: false, data: null, problem: describe(error, subject), error }
    }
    throw error
  }
}

/**
 * The value, or a fallback when the call did not succeed.
 *
 * For the parts of a page where a fallback is genuinely correct — the
 * institution's crest, the current semester in a subtitle — rather than for
 * figures, where it is the bug this module exists to fix. Reach for
 * `outcome.problem` first and this second.
 */
export function dataOr<T, F>(outcome: Outcome<T>, fallback: F): T | F {
  return outcome.ok ? outcome.data : fallback
}

/**
 * The first problem among several calls, or `null` if all of them worked.
 *
 * For a surface fed by more than one call — a chart that needs both the
 * accounts and the period's totals — where any one of them failing means the
 * surface cannot be drawn.
 */
export function firstProblem(...outcomes: Array<Outcome<unknown>>): Problem | null {
  for (const outcome of outcomes) {
    if (!outcome.ok) return outcome.problem
  }
  return null
}
