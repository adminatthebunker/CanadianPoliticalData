---
title: Boundary licences
description: Per-source licence terms for the electoral boundary data served by the Canadian Political Data API, and what each one requires of you.
---

# Boundary licences

Every boundary object returned by the API carries a `licence` field. This page
explains what is in it and what it asks of you.

There is no single answer, because there is no single source. Canadian electoral
boundaries are published by fourteen different agencies under at least nine
different sets of terms, and **four provinces publish no terms at all.**

## The `licence` object

```json
"licence": {
  "name": "Open Government Licence – Canada 2.0",
  "url": "https://open.canada.ca/en/open-government-licence-canada",
  "attribution": "Contains information licensed under the Open Government Licence – Canada.",
  "redistribution": "permitted"
}
```

| Field | Meaning |
|---|---|
| `name` | The licence as the issuing agency names it. |
| `url` | Canonical terms page, or `null` when the issuer publishes none. |
| `attribution` | The string to display. Where a licence prescribes exact wording, this is quoted verbatim — reproduce it as-is. |
| `redistribution` | `permitted`, `unlicensed`, or `reserved`. See below. |

Responses also carry a `Link: <…>; rel="license"` header pointing here, for
clients that read headers rather than parsing bodies.

## `redistribution` values

**`permitted`** — the issuer's terms explicitly allow copying, modifying and
distributing, generally including commercial use. Follow the `attribution`
string and you are fine.

**`unlicensed`** — the issuer publishes **no terms whatsoever**. Not a permissive
licence; an absence of one. The data is public and served without a gate, but no
agency has granted anyone rights to it. Attribute the source and take your own
view of the risk.

**`reserved`** — the issuer has affirmatively reserved rights. Currently only
Manitoba, which publishes "© 2026. All rights reserved." That is a stronger
statement than silence and should be treated accordingly.

!!! warning "We serve `unlicensed` and `reserved` data, and we tell you so"

    We could have suppressed the four provinces without a licence. We chose to
    serve them, because a citizen looking up their MLA in Halifax or Winnipeg is
    poorly served by a blank, and because the boundaries themselves are public
    records published without a gate.

    But we are not going to pretend the terms exist. If your use depends on
    having a licence — a commercial product, redistribution to your own users —
    the `redistribution` field is the flag to check, and contacting the agency
    directly is the way to resolve it.

## Current position by jurisdiction

| Jurisdiction | Licence | Redistribution |
|---|---|---|
| Federal | Open Government Licence – Canada 2.0 | ✅ permitted |
| Alberta | Open Government Licence – Alberta | ✅ permitted (attribution is a **hard condition** — breach terminates the grant) |
| British Columbia | Elections BC Open Data Licence | ✅ permitted (exact wording required) |
| Ontario | Elections Ontario **Open Use** Data Product Licence | ✅ permitted (no attribution clause) |
| Quebec | Élections Québec open data | ✅ permitted |
| New Brunswick | GeoNB Open Data Licence v1.0 / OGL – New Brunswick | ✅ permitted |
| Newfoundland & Labrador | OGL – Newfoundland and Labrador v1.0 | ✅ permitted |
| Northwest Territories | OGL – Northwest Territories | ✅ permitted |
| Yukon | OGL – Yukon 2.0 | ✅ permitted |
| Nunavut | Elections Nunavut, open, no gate | ✅ permitted |
| **Nova Scotia** | None published | ⛔ unlicensed |
| **Saskatchewan** | None published | ⛔ unlicensed |
| **Prince Edward Island** | None published | ⛔ unlicensed |
| **Manitoba** | "© 2026. All rights reserved." | ⛔ reserved |

Municipal boundaries vary further and many are unaudited; those return the
conservative default until each is verified.

## Two things worth knowing

**A portal's licence metadata can be flatly wrong.** Winnipeg's open-data portal
declares its ward boundaries under the "Open Government Licence – Prince Edward
Island" — on a Manitoba dataset. Every entry in our table cites a terms page a
human read, never a machine-readable tag.

**Ontario publishes two different agreements from the same page.** Electoral
*district* boundaries fall under the permissive **Open Use** agreement; polling
*division* boundaries fall under a separate and more restrictive **Limited Use**
agreement. Confusing the two is easy and consequential.

## Provenance

Boundary rows also expose `source_set`, `boundaries_version`, `effective_from`
and `effective_to`, so you can tell which generation of a district you have and
when it was in force. See [Boundaries](./boundaries.md).
