import {
  createHmac,
  randomBytes,
  scrypt as scryptCallback,
  timingSafeEqual,
} from "node:crypto";
import { promisify } from "node:util";

/**
 * Password hashing and cookie signing, on Node's own crypto.
 *
 * Deliberately no dependency. scrypt is a memory-hard KDF built into Node and
 * is a genuine answer to offline cracking; bcrypt/argon2 would be defensible
 * too but each drags in a native build, and this app is meant to deploy onto
 * a cheap VPS with `node server.js` and nothing else. Auth.js is still the
 * right call the day this needs university SSO — that is a provider problem,
 * not a hashing one, and it can sit on top of these same primitives.
 *
 * WHAT THIS IS NOT: rate limiting, lockout after repeated failures, or 2FA.
 * A real deployment needs all three at the edge.
 */

const scrypt = promisify(scryptCallback) as (
  password: string | Buffer,
  salt: string | Buffer,
  keylen: number,
  options: { N: number; r: number; p: number; maxmem: number },
) => Promise<Buffer>;

/**
 * N=2^16 rather than OWASP's 2^17 floor. 2^17 wants ~128MB *per concurrent
 * hash*, and the deployment target here is a 1-2GB VPS (see next.config.ts) —
 * a handful of simultaneous logins at that size is an out-of-memory kill, and
 * a login you cannot complete is worse security than a slightly cheaper KDF.
 * 2^16 costs ~64MB and ~150ms, which is still far beyond bcrypt's work factor.
 * The parameters are stored per-hash, so raising this later costs nothing.
 */
const SCRYPT_N = 1 << 16;
const SCRYPT_r = 8;
const SCRYPT_p = 1;
const KEY_BYTES = 32;
const SALT_BYTES = 16;
const MAXMEM = 256 * 1024 * 1024;

/**
 * Async, not `scryptSync`. Node is single-threaded: a sync hash blocks every
 * other in-flight request for the whole ~150ms, so one person signing in
 * would stall everyone else's page loads. The async form runs on libuv's
 * threadpool instead.
 *
 * Format is `scrypt$<N>$<r>$<p>$<salt-hex>$<key-hex>` — the parameters travel
 * with the hash so raising the cost later does not invalidate every existing
 * password.
 */
export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(SALT_BYTES);
  const key = await scrypt(password.normalize("NFKC"), salt, KEY_BYTES, {
    N: SCRYPT_N,
    r: SCRYPT_r,
    p: SCRYPT_p,
    maxmem: MAXMEM,
  });
  return [
    "scrypt",
    SCRYPT_N,
    SCRYPT_r,
    SCRYPT_p,
    salt.toString("hex"),
    key.toString("hex"),
  ].join("$");
}

/** Constant-time. Returns false on a malformed hash rather than throwing. */
export async function verifyPassword(
  password: string,
  stored: string,
): Promise<boolean> {
  const parts = stored.split("$");
  if (parts.length !== 6 || parts[0] !== "scrypt") return false;

  const [, nRaw, rRaw, pRaw, saltHex, keyHex] = parts;
  const N = Number(nRaw);
  const r = Number(rRaw);
  const p = Number(pRaw);
  if (!Number.isInteger(N) || !Number.isInteger(r) || !Number.isInteger(p)) {
    return false;
  }
  // A hash claiming a huge N would otherwise let a crafted record exhaust
  // memory on every verify attempt.
  if (N > 1 << 20 || r > 32 || p > 16) return false;

  const expected = Buffer.from(keyHex, "hex");
  if (expected.length === 0) return false;

  try {
    const actual = await scrypt(
      password.normalize("NFKC"),
      Buffer.from(saltHex, "hex"),
      expected.length,
      { N, r, p, maxmem: MAXMEM },
    );
    return timingSafeEqual(actual, expected);
  } catch {
    return false;
  }
}

/**
 * The secret behind session signatures and reset tokens.
 *
 * In production an unset SESSION_SECRET is fatal: falling back to a generated
 * one would mean every deploy silently signs with a different key, logging
 * everyone out, and a standalone deploy running two instances behind a load
 * balancer would reject each other's cookies. In dev a per-boot random key is
 * fine and saves setting up an env file to click around.
 */
let devSecret: string | null = null;
function sessionSecret(): string {
  const fromEnv = process.env.SESSION_SECRET;
  if (fromEnv && fromEnv.length >= 32) return fromEnv;

  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "SESSION_SECRET must be set to at least 32 characters in production.",
    );
  }
  devSecret ??= randomBytes(32).toString("hex");
  return devSecret;
}

export function sign(value: string): string {
  return createHmac("sha256", sessionSecret()).update(value).digest("base64url");
}

/** Constant-time signature check. */
export function verifySignature(value: string, signature: string): boolean {
  const expected = Buffer.from(sign(value));
  const actual = Buffer.from(signature);
  if (expected.length !== actual.length) return false;
  return timingSafeEqual(actual, expected);
}

/** URL-safe random token, for password resets. */
export function randomToken(): string {
  return randomBytes(32).toString("base64url");
}
