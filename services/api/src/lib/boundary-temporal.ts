/**
 * Temporal predicate for `constituency_boundaries`.
 *
 * Migration `0021` made boundaries history-aware: one `constituency_id` exists
 * once per generation, distinguished by `boundaries_version`, and the unique key
 * is `(constituency_id, boundaries_version)`. The documented query contract in
 * that migration is:
 *
 *     effective_from <= :date AND (effective_to IS NULL OR effective_to >= :date)
 *
 * Until 2026-08-18 nothing honoured it, because a second generation had never
 * existed — every row was `boundaries_version='current'`, `effective_to=NULL`.
 * Nine read paths had drifted into two different wrong shapes:
 *
 *   - Four had **no filter at all** (`routes/politicians.ts`,
 *     `routes/public/politicians.ts`, `routes/map.ts` ×2). These return one row
 *     per generation the moment a second exists — duplicated rep lists and
 *     doubled map polygons.
 *   - Five used **`effective_to IS NULL`** (`lib/postcode-reps.ts`,
 *     `routes/public/postcodes.ts`, `routes/public/boundaries.ts` ×3). Subtler and
 *     worse: when a generation is retired its `effective_to` is set, so a
 *     *future-dated* incoming generation becomes the only row with a NULL
 *     `effective_to` and goes live **immediately** rather than on its in-force
 *     date. Quebec's 2026 map (in force at dissolution, ~2026-10-05) would have
 *     activated the day it was loaded.
 *
 * Both bugs are fixed by using this predicate everywhere. It also *enables*
 * dated cutover: load a generation with a future `effective_from`, set the
 * outgoing generation's `effective_to` to the day before, and the switch happens
 * by itself on the day with no operator present.
 *
 * `CURRENT_DATE` is evaluated by Postgres in the server's timezone, so there are
 * no bind parameters and this composes into any WHERE clause without disturbing
 * positional argument numbering.
 *
 * ⚠ There is a hand-duplicated copy of the point-in-polygon query in
 * `services/scanner/src/alerts_worker.py`. Keep the two in sync.
 */

/**
 * SQL fragment selecting the generation in force today.
 *
 * @param alias Table alias used in the query (e.g. `"cb"`). Omit for unaliased
 *              references.
 *
 * @example
 *   `SELECT ... FROM constituency_boundaries WHERE ${currentBoundary()}`
 *   `SELECT ... FROM constituency_boundaries cb WHERE ${currentBoundary("cb")}`
 */
export function currentBoundary(alias?: string): string {
  const p = alias ? `${alias}.` : "";
  return `${p}effective_from <= CURRENT_DATE
      AND (${p}effective_to IS NULL OR ${p}effective_to >= CURRENT_DATE)`;
}

/**
 * Same predicate at an arbitrary date, for "who represented this address in
 * 2019?" queries. Takes the positional placeholder rather than a value so the
 * caller keeps control of argument numbering.
 *
 * @param placeholder e.g. `"$3"`
 * @param alias       Table alias, if any.
 */
export function boundaryAtDate(placeholder: string, alias?: string): string {
  const p = alias ? `${alias}.` : "";
  return `${p}effective_from <= ${placeholder}::date
      AND (${p}effective_to IS NULL OR ${p}effective_to >= ${placeholder}::date)`;
}
