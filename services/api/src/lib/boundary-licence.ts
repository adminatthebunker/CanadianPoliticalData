/**
 * Licence attribution for boundary data served through the public API.
 *
 * `/api/public/v1/boundaries/*` serves polygons under permissive CORS with no
 * terms attached. The 2026-08-18 research phase audited every source and found
 * that obligation unmet across the board, and the position varies far more than
 * "it's government data" suggests:
 *
 *   - Some sources are cleanly open and explicitly permit redistribution
 *     (Elections Canada OGL, Elections BC, Elections Ontario Open Use).
 *   - **Four provinces publish no licence at all** — NS, SK, MB and PE. NS, SK
 *     and PE are silent; **Manitoba states "© 2026. All rights reserved."**,
 *     which is an affirmative reservation rather than an omission.
 *   - Open North's own "permission to redistribute" is **theirs and
 *     non-transferable**, so every row still mirrored from them inherits nothing.
 *
 * The operator's decision (2026-08-18) was to serve the data with attribution
 * rather than suppress the unlicensed provinces. This module implements that.
 * It also *is* the suppression seam if that changes: `boundaryLicence()` is the
 * single place that knows a source's terms, so gating on
 * `redistribution !== "permitted"` would be a one-line filter.
 *
 * ⚠ Two rules learned the hard way:
 *
 *   1. **Never trust a portal's machine-readable licence field.** Winnipeg's
 *      Socrata dataset declares "Open Government Licence – Prince Edward Island"
 *      on a *Manitoba* product. Every entry below cites a terms page a human
 *      read, not a metadata tag.
 *   2. **`source_set` is not stable for shared rows.** The loader upserts
 *      `census-subdivisions/*` rows from whichever representative set ingested
 *      last, so those rows' `source_set` is last-writer-wins. That is exactly why
 *      `DEFAULT_LICENCE` below is mandatory rather than optional.
 */

export interface BoundaryLicence {
  /** Short licence name as the issuer states it. */
  name: string;
  /** Canonical terms URL, or null when the issuer publishes none. */
  url: string | null;
  /**
   * Attribution string, quoted verbatim from the licence where one is
   * prescribed. ⚠ Elections BC terminates rights across *all* their datasets on
   * breach, so their wording — including their spelling of "licenced" — is exact.
   */
  attribution: string | null;
  /** Whether the terms permit us to redistribute, i.e. to serve this publicly. */
  redistribution: "permitted" | "unlicensed" | "reserved";
}

/**
 * Used when a `source_set` has no entry — including every row whose `source_set`
 * is unreliable. Deliberately claims nothing.
 */
export const DEFAULT_LICENCE: BoundaryLicence = {
  name: "Unspecified — see source",
  url: null,
  attribution: null,
  redistribution: "unlicensed",
};

const OGL_CANADA = "https://open.canada.ca/en/open-government-licence-canada";

export const BOUNDARY_LICENCES: Record<string, BoundaryLicence> = {
  // ── Cleanly open, redistribution explicit ────────────────────────────────
  "federal-electoral-districts": {
    name: "Open Government Licence – Canada 2.0",
    url: OGL_CANADA,
    attribution: "Contains information licensed under the Open Government Licence – Canada.",
    redistribution: "permitted",
  },
  "ontario-electoral-districts": {
    // Elections Ontario serves TWO agreements from the same page. Electoral
    // district boundaries get "Open Use" — commercial use and distribution both
    // explicit, and no attribution clause at all. Polling divisions get the
    // separate, more restrictive "Limited Use" agreement.
    name: "Elections Ontario Open Use Data Product Licence Agreement",
    url: "https://www.elections.on.ca/en/voting-in-ontario/electoral-district-shapefiles.html",
    attribution: null,
    redistribution: "permitted",
  },
  "alberta-electoral-districts": {
    name: "Open Government Licence – Alberta",
    url: "https://open.alberta.ca/licence",
    // ⚠ Attribution is a hard condition here: non-compliance terminates the
    // grant automatically.
    attribution: "Contains information licensed under the Open Government Licence – Alberta.",
    redistribution: "permitted",
  },
  "british-columbia-electoral-districts": {
    // ⚠ NOT OGL-BC, which the upstream audit assumed. Elections BC publishes its
    // own licence, and cl. 5 terminates rights across every Elections BC dataset
    // on any breach — so the string below must be exact, their spelling included.
    name: "Elections BC Open Data Licence",
    url: "https://www.elections.bc.ca/docs/EBC-Open-Data-Licence.pdf",
    attribution: "Contains information licenced under the Elections BC Open Data Licence",
    redistribution: "permitted",
  },
  "new-brunswick-electoral-districts": {
    // The GeoNB flow-down clause (§ II.5) that Open North reproduces belongs to
    // a 2012 click-through agreement Open North entered. GeoNB replaced it in
    // 2015 with a unilateral open grant carrying no flow-down. We never accepted
    // the 2012 terms, so sourcing direct from GeoNB removes the obligation
    // rather than mitigating it. Both attribution strings are printed because
    // the bundle and the catalogue page name different licences.
    name: "GeoNB Open Data Licence v1.0 / Open Government Licence – New Brunswick",
    url: "https://geonb.snb.ca/documents/license/geonb-odl_en.pdf",
    attribution:
      "Contains information licenced under the GeoNB Open Data Licence. " +
      "Contains information licensed under the Open Government Licence – New Brunswick.",
    redistribution: "permitted",
  },
  "newfoundland-and-labrador-electoral-districts": {
    name: "Open Government Licence – Newfoundland and Labrador v1.0",
    url: "https://opendata.gov.nl.ca/public/opendata/page/?page-id=licence",
    attribution:
      "Contains information licensed under the Open Government Licence – Newfoundland and Labrador.",
    redistribution: "permitted",
  },
  "northwest-territories-electoral-districts": {
    name: "Open Government Licence – Northwest Territories",
    url: "https://www.gov.nt.ca/en/open-government-licence",
    attribution: "Contains information licensed under the Open Government Licence – Northwest Territories. Elections NWT, NWTCG.",
    redistribution: "permitted",
  },
  "yukon-electoral-districts": {
    // ⚠ Identity confirmed from CKAN metadata only — every Yukon government URL
    // returns Cloudflare 403, so the licence text itself could not be read.
    // Recorded rather than guessed.
    name: "Open Government Licence – Yukon 2.0",
    url: "https://yukon.ca/en/your-government/open-government/open-government-licence-yukon",
    attribution: "Contains information licensed under the Open Government Licence – Yukon.",
    redistribution: "permitted",
  },
  "nunavut-electoral-districts": {
    name: "Elections Nunavut — open, no gate",
    url: "https://www.elections.nu.ca/en/constituencies",
    attribution: "Contains information from Elections Nunavut.",
    redistribution: "permitted",
  },

  // ── ⛔ No licence exists. Served per operator decision, 2026-08-18. ───────
  "nova-scotia-electoral-districts": {
    // Elections NS's only machine-readable surface is an internal AGOL service
    // with licenseInfo: null and copyrightText: "", described "DO NOT DELETE …
    // for refence in applications". ⚠ ArcGIS `access: public` is a sharing
    // setting, not a licence. The NS open-data portal carries only *municipal*
    // polling districts. Research cannot unlock this; it needs an email.
    name: "No licence published — Elections Nova Scotia",
    url: null,
    attribution: "Boundary data from Elections Nova Scotia. No licence terms are published by the issuer.",
    redistribution: "unlicensed",
  },
  "saskatchewan-electoral-districts": {
    name: "No licence published — Elections Saskatchewan",
    url: null,
    attribution: "Boundary data from Elections Saskatchewan (© Elections Saskatchewan). No licence terms are published by the issuer.",
    redistribution: "unlicensed",
  },
  "manitoba-electoral-districts": {
    // ⚠ The strongest of the four. Not silence — an affirmative reservation.
    name: "All rights reserved — Elections Manitoba",
    url: null,
    attribution: "Boundary data from Elections Manitoba (© 2026, all rights reserved).",
    redistribution: "reserved",
  },
  "prince-edward-island-electoral-districts": {
    name: "No licence published — Elections PEI",
    url: null,
    attribution: "Boundary data from Elections Prince Edward Island. No licence terms are published by the issuer.",
    redistribution: "unlicensed",
  },
  "quebec-electoral-districts": {
    name: "Élections Québec — open data",
    url: "https://donnees.electionsquebec.qc.ca/",
    attribution: "Contient des informations d'Élections Québec.",
    redistribution: "permitted",
  },
};

/**
 * Legacy `source_set` values -> the generation-free key above.
 *
 * ⚠ Needed because the licence keys are generation-free (ruling A6) but the rows
 * in the table are not yet: 12 of 13 provincial/federal `source_set` values still
 * carry a generation suffix, and they are renamed only as each jurisdiction is
 * cut over to an authoritative source.
 *
 * Without this map, 8 of 13 jurisdictions fall through to `DEFAULT_LICENCE` and
 * are reported as "unlicensed" — including Ontario, BC, Quebec and Yukon, all of
 * which are genuinely open. That is an error in the conservative direction, but
 * still an error: it understates rights we actually have and misattributes data
 * whose issuers require attribution.
 *
 * An issuer's terms do not depend on our internal naming, so the mapping is by
 * jurisdiction, not by string shape. Delete an entry once its rows are renamed.
 */
const LEGACY_SOURCE_SETS: Record<string, string> = {
  "british-columbia-electoral-districts-2015-redistribution":
    "british-columbia-electoral-districts",
  "manitoba-electoral-districts-2018": "manitoba-electoral-districts",
  "new-brunswick-electoral-districts-2024": "new-brunswick-electoral-districts",
  "northwest-territories-electoral-districts-2013":
    "northwest-territories-electoral-districts",
  "nova-scotia-electoral-districts-2019": "nova-scotia-electoral-districts",
  "ontario-electoral-districts-representation-act-2015":
    "ontario-electoral-districts",
  "prince-edward-island-electoral-districts-2017":
    "prince-edward-island-electoral-districts",
  "quebec-electoral-districts-2017": "quebec-electoral-districts",
  "saskatchewan-electoral-districts-representation-act-2012":
    "saskatchewan-electoral-districts",
  "yukon-electoral-districts-2015": "yukon-electoral-districts",
  // Federal and Alberta are already generation-free in `source_set` (their
  // generation lives only in the constituency_id prefix), and NL never had one.
};

/**
 * Licence for a boundary row.
 *
 * @param sourceSet the row's `source_set`. Unknown or unreliable values fall
 *                  through to `DEFAULT_LICENCE`, which claims nothing. That
 *                  fallback is mandatory rather than defensive: shared
 *                  `census-subdivisions` rows have a last-writer-wins
 *                  `source_set`, so for those it is not a reliable attribute.
 */
export function boundaryLicence(sourceSet: string | null | undefined): BoundaryLicence {
  if (!sourceSet) return DEFAULT_LICENCE;
  const key = LEGACY_SOURCE_SETS[sourceSet] ?? sourceSet;
  return BOUNDARY_LICENCES[key] ?? DEFAULT_LICENCE;
}
