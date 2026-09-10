/**
 * The error envelope every ACMIS endpoint returns, as a typed class.
 *
 * Branching on `code` rather than on a message is the whole point of the
 * envelope: nine apps and any number of integrations depend on these, and
 * matching on a human-readable string is how an integration breaks when
 * somebody fixes a typo.
 */
export interface ApiErrorPayload {
  code: string
  message: string
  details?: Record<string, unknown>
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>
  /** Echoed from `x-request-id`, so a support ticket can name one request. */
  readonly requestId: string | null

  constructor(
    status: number,
    payload: ApiErrorPayload,
    requestId: string | null = null,
  ) {
    super(payload.message)
    this.name = "ApiError"
    this.status = status
    this.code = payload.code
    this.details = payload.details ?? {}
    this.requestId = requestId
  }

  /** Authentication failed or lapsed — the caller should sign in again. */
  get isUnauthenticated() {
    return this.status === 401
  }

  /**
   * The rules refused this. Deliberately says nothing about why, and nothing
   * about whether the record exists — the API withholds both unless the
   * deployment has opted into explanations.
   */
  get isForbidden() {
    return this.status === 403
  }

  /**
   * An academic or financial regulation refused the action, as opposed to the
   * payload being malformed. These are shown differently: the fix is an
   * approval or a waiver, not a corrected field.
   */
  get isRuleViolation() {
    return this.code === "rule_violation"
  }

  /** Which grants could authorise an exception, when the API says so. */
  get waivableBy(): string[] {
    const value = this.details.waivable_by
    return Array.isArray(value) ? (value as string[]) : []
  }

  /** Field-level validation errors, keyed by dotted field path. */
  get fieldErrors(): Record<string, string[]> {
    const fields = this.details.fields
    return typeof fields === "object" && fields !== null
      ? (fields as Record<string, string[]>)
      : {}
  }

  /** Someone else changed the record first. */
  get isConflict() {
    return this.status === 409
  }
}

/** A network failure or a non-JSON response — distinct from an API refusal. */
export class TransportError extends Error {
  override readonly cause?: unknown
  constructor(message: string, cause?: unknown) {
    super(message)
    this.name = "TransportError"
    this.cause = cause
  }
}
