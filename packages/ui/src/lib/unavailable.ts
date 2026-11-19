/**
 * What a data surface is told when the figures did not arrive.
 *
 * Structurally the same shape as `Problem` from `@acmis/api-client`, so a page
 * writes `unavailable={outcome.problem}` with no adapter in between — but
 * declared here, and narrower, because this package is imported by thirteen
 * apps and must not depend on the client they happen to share. A design system
 * that needs an HTTP library to render a tile is not a design system.
 */
export interface Unavailable {
  /** One sentence, written for the reader. "The ledger did not respond." */
  reason: string
  /** Quoted to support, so one failure can be found in the logs. */
  requestId?: string | null
  /**
   * Whether trying again could plausibly help. A surface shows a retry only
   * when this is true: an affordance that cannot work is worse than none,
   * because it will be used four times before anybody is asked.
   */
  retryable?: boolean
}
