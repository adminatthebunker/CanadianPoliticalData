/** Shared Canadian-postal-code helpers.
 *
 * One home for the validation regex + canonicalization that were
 * previously copy-pasted across Lander / PostalLookupBar, plus the
 * localStorage persistence for the "my reps" search filter. The stored
 * postcode never leaves the browser except as a search filter param —
 * it is deliberately not tied to the user account.
 */

export const POSTAL_RE = /^[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d$/;

const STORAGE_KEY = "cpd_postcode";

/** "k1a 0a6" / "K1A-0A6" → "K1A0A6" */
export function canonicalizePostal(s: string): string {
  return s.replace(/[\s-]/g, "").toUpperCase();
}

/** "K1A0A6" → "K1A 0A6" (display form; passes through anything odd) */
export function formatPostal(s: string): string {
  const c = canonicalizePostal(s);
  return c.length === 6 ? `${c.slice(0, 3)} ${c.slice(3)}` : c;
}

/** Last-used postcode, canonical form, or null. try/catch: localStorage
 *  throws in some private-browsing modes — treat as "not stored". */
export function loadStoredPostcode(): string | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v && POSTAL_RE.test(v)) return canonicalizePostal(v);
  } catch {
    /* ignore */
  }
  return null;
}

export function storePostcode(code: string): void {
  if (!POSTAL_RE.test(code)) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, canonicalizePostal(code));
  } catch {
    /* ignore */
  }
}
