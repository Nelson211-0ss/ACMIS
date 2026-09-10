import { ApiError, TransportError, type ApiErrorPayload } from "./errors"

/**
 * The HTTP client every app shares.
 *
 * Deliberately small: `fetch`, the standard error envelope, and the three
 * headers this platform runs on. No caching layer and no query library — those
 * belong in the apps, where React Server Components and `next/cache` already
 * solve them better than a client-side store would.
 */

export interface ClientOptions {
  /** Base URL of the API, without a trailing slash. */
  baseUrl: string
  /**
   * Which tenant this request is for. In production the API resolves this from
   * the Host header and ignores the header entirely; in development nine dev
   * servers share `localhost`, so a header is the only way. The API refuses to
   * honour it outside local/test — see `core/tenant_resolver.py`.
   */
  tenant?: string
  /**
   * Which module app is calling. Recorded in the audit trail, so "who changed
   * this" also answers "from where", and readable by policies — a rule can
   * forbid mark entry from the public portal.
   */
  module: string
  /** Bearer access token. Omitted for the genuinely public endpoints. */
  token?: string | null
  /** Correlates a browser request with the API's logs. */
  requestId?: string
  fetchImpl?: typeof fetch
  /** Milliseconds before a request is abandoned. */
  timeoutMs?: number
}

export interface RequestOptions {
  query?: Record<string, unknown>
  body?: unknown
  signal?: AbortSignal
  /** Next.js fetch cache hints, passed straight through. */
  cache?: RequestCache
  next?: { revalidate?: number | false; tags?: string[] }
  headers?: Record<string, string>
}

const DEFAULT_TIMEOUT_MS = 30_000

export class AcmisClient {
  private readonly options: ClientOptions

  constructor(options: ClientOptions) {
    this.options = { timeoutMs: DEFAULT_TIMEOUT_MS, ...options }
  }

  /** A copy of this client with a different token — used after a refresh. */
  withToken(token: string | null): AcmisClient {
    return new AcmisClient({ ...this.options, token })
  }

  get<T>(path: string, options: RequestOptions = {}) {
    return this.request<T>("GET", path, options)
  }

  post<T>(path: string, body?: unknown, options: RequestOptions = {}) {
    return this.request<T>("POST", path, { ...options, body })
  }

  patch<T>(path: string, body?: unknown, options: RequestOptions = {}) {
    return this.request<T>("PATCH", path, { ...options, body })
  }

  put<T>(path: string, body?: unknown, options: RequestOptions = {}) {
    return this.request<T>("PUT", path, { ...options, body })
  }

  delete<T>(path: string, options: RequestOptions = {}) {
    return this.request<T>("DELETE", path, options)
  }

  private async request<T>(
    method: string,
    path: string,
    options: RequestOptions,
  ): Promise<T> {
    const { baseUrl, tenant, module, token, requestId, fetchImpl, timeoutMs } =
      this.options
    const doFetch = fetchImpl ?? fetch

    const url = new URL(
      path.startsWith("/") ? path : `/${path}`,
      baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`,
    )
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value === undefined || value === null || value === "") continue
      if (Array.isArray(value)) {
        // Repeated keys rather than a comma-joined list: FastAPI reads
        // `?id=a&id=b` as a list and `?id=a,b` as one string.
        for (const item of value) url.searchParams.append(key, String(item))
      } else {
        url.searchParams.set(key, String(value))
      }
    }

    const headers: Record<string, string> = {
      accept: "application/json",
      "x-acmis-module": module,
      ...options.headers,
    }
    if (options.body !== undefined) headers["content-type"] = "application/json"
    if (token) headers.authorization = `Bearer ${token}`
    if (tenant) headers["x-acmis-tenant"] = tenant
    if (requestId) headers["x-request-id"] = requestId

    // A caller's own signal and the timeout both have to be able to abort.
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    if (options.signal) {
      options.signal.addEventListener("abort", () => controller.abort(), {
        once: true,
      })
    }

    let response: Response
    try {
      response = await doFetch(url, {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
        cache: options.cache,
        // `next` is a Next.js augmentation of RequestInit; harmless elsewhere.
        ...(options.next ? { next: options.next } : {}),
      })
    } catch (cause) {
      if (controller.signal.aborted) {
        throw new TransportError(
          `The request to ${method} ${path} timed out.`,
          cause,
        )
      }
      throw new TransportError(
        `Could not reach the ACMIS API at ${baseUrl}.`,
        cause,
      )
    } finally {
      clearTimeout(timer)
    }

    const echoedRequestId = response.headers.get("x-request-id")

    if (response.status === 204) return undefined as T

    const text = await response.text()
    let parsed: unknown = null
    if (text) {
      try {
        parsed = JSON.parse(text)
      } catch {
        // A non-JSON body from a JSON API means something in front of it
        // answered — a proxy error page, usually. Surfaced as transport
        // rather than mislabelled as an API refusal.
        throw new TransportError(
          `The API returned a non-JSON response (${response.status}).`,
        )
      }
    }

    if (!response.ok) {
      const envelope = (parsed ?? {}) as { error?: ApiErrorPayload }
      throw new ApiError(
        response.status,
        envelope.error ?? {
          code: "unknown_error",
          message: `Request failed with status ${response.status}.`,
        },
        echoedRequestId,
      )
    }

    return parsed as T
  }
}
