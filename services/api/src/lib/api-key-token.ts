import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { config } from "../config.js";

/**
 * Public developer-API key minting + verification.
 *
 * Token shape: `cpd_<env>_<22-char-base62>_<6-char-checksum>`.
 *   - `cpd` prefix is brand-namespaced so a leaked token in logs is greppable.
 *   - `<env>` is `live` or `test`, sourced from NODE_ENV. Mixing live + test
 *     tokens (Stripe-shaped lesson from 2026-05-05) is caught at parse time.
 *   - `<22-char-base62>` is 132 bits of entropy from crypto.randomBytes(17).
 *   - `<6-char-checksum>` is the first 6 base62 chars of HMAC-SHA256(pepper,
 *     prefix-and-body). Lets verifyApiKey reject malformed / typo'd tokens
 *     without a DB hit.
 *
 * Storage discipline: only `prefix` (cpd_<env>_<random>) is plaintext in DB;
 * the full token is HMAC-SHA256(API_KEY_PEPPER, full_token) and stored as
 * `private.api_keys.token_hash`. The full token is shown to the user once
 * at create/rotate time and never again.
 *
 * This module is a sibling of `auth-token.ts` (session JWTs). They use
 * different primitives — JWTs for short-lived browser sessions, HMAC'd
 * opaque tokens for long-lived API keys — by design.
 */

const BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
const RANDOM_BYTES = 17;       // → 22 base62 chars (132 bits entropy)
const RANDOM_LEN = 22;
const CHECKSUM_LEN = 6;

export interface MintedKey {
  /** Full token, e.g. "cpd_live_abc123XYZ987def012ghi3_4Bz9Q1". Show once. */
  token: string;
  /** Plaintext, indexed for revoke/lookup, e.g. "cpd_live_abc123XYZ987def012ghi3". */
  prefix: string;
  /** HMAC-SHA256 hash of the full token; stored as `token_hash`. */
  hash: Buffer;
}

export interface VerifiedToken {
  /** Plaintext prefix, looked up against `private.api_keys.prefix`. */
  prefix: string;
  /** HMAC hash, compared timing-safe against `private.api_keys.token_hash`. */
  hash: Buffer;
}

export class ApiKeyPepperUnsetError extends Error {
  constructor() {
    super("API_KEY_PEPPER not configured");
    this.name = "ApiKeyPepperUnsetError";
  }
}

export function isConfigured(): boolean {
  return Boolean(config.apiKeyPepper);
}

function getPepper(): Buffer {
  if (!config.apiKeyPepper) throw new ApiKeyPepperUnsetError();
  return Buffer.from(config.apiKeyPepper, "utf8");
}

function envTag(): "live" | "test" {
  return config.env === "production" ? "live" : "test";
}

function base62(bytes: Buffer, length: number): string {
  // Bigint-radix encoding. Pad with leading "0" to a fixed `length` so
  // every token has the same shape and lookups are predictable.
  let n = 0n;
  for (const b of bytes) n = (n << 8n) | BigInt(b);
  let s = "";
  while (n > 0n) {
    s = BASE62[Number(n % 62n)] + s;
    n /= 62n;
  }
  return s.padStart(length, "0").slice(0, length);
}

function checksum(prefixAndBody: string): string {
  // Separate from the storage hash on purpose — checksum exists to catch
  // typos / truncation cheaply at parse time, NOT to gate authentication.
  // A correct checksum still requires DB lookup + timing-safe hash compare.
  const mac = createHmac("sha256", getPepper()).update(prefixAndBody).digest();
  return base62(mac, CHECKSUM_LEN);
}

export function hashToken(token: string): Buffer {
  return createHmac("sha256", getPepper()).update(token).digest();
}

/** Mint a fresh API key. Returns the full token, prefix, and storage hash. */
export function mintApiKey(): MintedKey {
  const body = base62(randomBytes(RANDOM_BYTES), RANDOM_LEN);
  const prefix = `cpd_${envTag()}_${body}`;
  const cs = checksum(prefix);
  const token = `${prefix}_${cs}`;
  return { token, prefix, hash: hashToken(token) };
}

/**
 * Validate a presented token's shape + checksum without hitting the DB.
 * Returns null on any malformed / bad-checksum input. Does NOT confirm
 * the token exists or is unrevoked — caller must do the DB lookup using
 * the returned `prefix` and `hash`.
 */
export function verifyApiKey(token: string): VerifiedToken | null {
  if (typeof token !== "string") return null;
  // Fast structural checks first — cheaper than the HMAC.
  const parts = token.split("_");
  if (parts.length !== 4) return null;
  const scheme = parts[0]!;
  const env = parts[1]!;
  const body = parts[2]!;
  const cs = parts[3]!;
  if (scheme !== "cpd") return null;
  if (env !== envTag()) return null;     // wrong-environment token
  if (body.length !== RANDOM_LEN) return null;
  if (cs.length !== CHECKSUM_LEN) return null;
  for (const ch of body + cs) {
    if (BASE62.indexOf(ch) < 0) return null;
  }
  const prefix = `${scheme}_${env}_${body}`;
  // timing-safe compare on the checksum so attackers can't probe one
  // base62 character at a time.
  const expectedCs = Buffer.from(checksum(prefix));
  const presentedCs = Buffer.from(cs);
  if (
    expectedCs.length !== presentedCs.length ||
    !timingSafeEqual(expectedCs, presentedCs)
  ) {
    return null;
  }
  return { prefix, hash: hashToken(token) };
}
