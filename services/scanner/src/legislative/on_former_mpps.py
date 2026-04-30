"""ON historical MPP roster backfill.

The Ontario Legislative Assembly publishes a per-parliament roster
listing at:

    https://www.ola.org/en/members/parliament-{N}        for N=1..44

Each page is a single-page table (no pagination, no JS) of every MPP
who served in that parliament. Rows look like:

    <a href="/en/members/all/{slug}">Last, First [Hon.]</a>   {Riding}

Per-member JSON at ``/en/members/all/{slug}?_format=json`` then
exposes the stable ``field_member_id`` (immutable integer the Assembly
assigns once and never reuses), plus clean ``field_first_name`` /
``field_last_name`` and a ``field_url_segment`` matching the slug.

We iterate parliaments 1..44, enumerate every (slug, parliament) edge
from the listings, fetch each unique slug's JSON for the member_id,
and:

1. Upsert ``politicians`` keyed on ``ola_member_id``.
   Existing ON politicians (typically from Open North current-roster
   ingest) are name-matched first; if found we stamp ola_member_id +
   ola_slug onto the existing row rather than spawning a duplicate.
2. Insert ``politician_terms`` rows per (politician, parliament) using
   the parliament's official start/end dates from the hard-coded date
   map below. ``source = 'ola.org:parliament-{N}'`` mirrors AB's
   per-legl source so the legl-keyed resolver in on_hansard.py can
   join cleanly.

Why this matters: ON Hansard's name-only resolver hits 98 % on the
current parliament because the current 124-MPP roster is fully
populated. Pre-current-Parliament Hansard collapses to ~0 % without
historical MPPs in ``politicians``. This ingester is the prerequisite
for backfilling Hansard parliaments 32-43 (1981-2025).

Idempotency: politicians upserted on ola_member_id; politician_terms
upserted on (politician_id, office, started_at). A full re-run is
a no-op.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timezone
from typing import Optional

import httpx

from ..db import Database
from .ab_former_mlas import _get_with_retry, _split_last_first

log = logging.getLogger(__name__)

LISTING_URL_TMPL = "https://www.ola.org/en/members/parliament-{n}"
MEMBER_JSON_URL_TMPL = "https://www.ola.org/en/members/all/{slug}?_format=json"

HEADERS = {
    "User-Agent": "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.org)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-CA,en;q=0.9",
}
JSON_HEADERS = {**HEADERS, "Accept": "application/json"}

REQUEST_DELAY_SECONDS = 1.0  # Polite to ola.org

# Parliament number → (started_at, ended_at) UTC datetimes. The dates
# come straight from the dropdown table on /en/members/all (verified
# 2026-04-26 against per-page headers like "All members serving in
# the 44th Parliament: April 14, 2025 – present"). Ended_at is None
# for the still-in-session parliament — the resolver treats NULL as
# "ongoing".
PARLIAMENT_DATES: dict[int, tuple[date, Optional[date]]] = {
    44: (date(2025, 4, 14),  None),
    43: (date(2022, 8, 8),   date(2025, 1, 28)),
    42: (date(2018, 7, 11),  date(2022, 5, 3)),
    41: (date(2014, 7, 2),   date(2018, 5, 8)),
    40: (date(2011, 11, 21), date(2014, 5, 2)),
    39: (date(2007, 11, 28), date(2011, 9, 7)),
    38: (date(2003, 11, 19), date(2007, 9, 10)),
    37: (date(1999, 10, 20), date(2003, 9, 2)),
    36: (date(1995, 9, 26),  date(1999, 5, 5)),
    35: (date(1990, 11, 19), date(1995, 4, 28)),
    34: (date(1987, 11, 3),  date(1990, 7, 30)),
    33: (date(1985, 6, 4),   date(1987, 7, 31)),
    32: (date(1981, 4, 21),  date(1985, 3, 25)),
    31: (date(1977, 6, 27),  date(1981, 2, 2)),
    30: (date(1975, 10, 28), date(1977, 4, 29)),
    29: (date(1971, 12, 13), date(1975, 8, 11)),
    28: (date(1968, 2, 14),  date(1971, 9, 13)),
    27: (date(1963, 10, 29), date(1967, 9, 5)),
    26: (date(1960, 1, 26),  date(1963, 8, 16)),
    25: (date(1955, 9, 8),   date(1959, 5, 4)),
    24: (date(1952, 2, 21),  date(1955, 5, 2)),
    23: (date(1949, 2, 10),  date(1951, 10, 6)),
    22: (date(1945, 7, 16),  date(1948, 4, 27)),
    21: (date(1944, 2, 22),  date(1945, 3, 24)),
    20: (date(1937, 12, 1),  date(1943, 6, 30)),
    19: (date(1935, 2, 20),  date(1937, 8, 25)),
    18: (date(1930, 2, 5),   date(1934, 5, 16)),
    17: (date(1927, 2, 2),   date(1929, 9, 17)),
    16: (date(1924, 2, 6),   date(1926, 10, 18)),
    15: (date(1920, 3, 9),   date(1923, 5, 10)),
    14: (date(1915, 2, 16),  date(1919, 9, 23)),
    13: (date(1912, 2, 7),   date(1914, 5, 29)),
    12: (date(1909, 2, 16),  date(1911, 11, 13)),
    11: (date(1905, 3, 22),  date(1908, 5, 2)),
    10: (date(1903, 3, 10),  date(1904, 12, 13)),
    9:  (date(1898, 8, 3),   date(1902, 4, 19)),
    8:  (date(1895, 2, 21),  date(1898, 1, 28)),
    7:  (date(1891, 2, 11),  date(1894, 5, 29)),
    6:  (date(1887, 2, 10),  date(1890, 4, 26)),
    5:  (date(1884, 1, 23),  date(1886, 11, 15)),
    4:  (date(1880, 1, 7),   date(1883, 2, 1)),
    3:  (date(1875, 11, 24), date(1879, 4, 25)),
    2:  (date(1871, 12, 7),  date(1874, 12, 23)),
    1:  (date(1867, 12, 27), date(1871, 2, 25)),
}

# Listing-row anchor: <a href="/en/members/all/{slug}" hreflang="en">{Last, First}</a>
_MEMBER_LINK_RE = re.compile(
    r'<a\s+href="/en/members/all/(?P<slug>[a-z0-9][-a-z0-9]*)"'
    r'[^>]*>(?P<name>[^<]+)</a>',
    re.IGNORECASE,
)


@dataclass
class _ListingMember:
    slug: str
    raw_name: str   # "Last, First" with optional honorifics


@dataclass
class _MemberDetail:
    slug: str
    member_id: int           # field_member_id
    first_name: str          # field_first_name
    last_name: str           # field_last_name
    title: str               # title (display name)


@dataclass
class Stats:
    parliaments_scanned: int = 0
    listing_rows_seen: int = 0
    unique_slugs: int = 0
    member_json_fetches: int = 0
    member_json_failures: int = 0
    politicians_inserted: int = 0
    politicians_updated: int = 0
    politicians_name_matched: int = 0
    terms_inserted: int = 0
    terms_skipped_existing: int = 0
    parliaments_missing_listing: list[int] = dc_field(default_factory=list)
    fail_samples: list[str] = dc_field(default_factory=list)


# ── Listing parse ──────────────────────────────────────────────────


def _parse_listing(html: str) -> list[_ListingMember]:
    """Extract (slug, raw_name) tuples from one parliament's listing page.

    The page is a Drupal Views table — each row has an `<a>` tag whose
    href is exactly `/en/members/all/<slug>` and whose text is the
    `"Last, First"` form (sometimes with an `Hon.` honorific between
    the comma and the first name). The rest of the row is just the
    riding name, which we don't need for the v1 backfill.
    """
    seen: dict[str, str] = {}
    for m in _MEMBER_LINK_RE.finditer(html):
        slug = m.group("slug").strip().lower()
        name = re.sub(r"\s+", " ", m.group("name") or "").strip()
        if not slug or not name:
            continue
        # Same slug appears once per row; if a future template change
        # repeats it, keep the longest name we saw (likeliest to carry
        # honorific context).
        prev = seen.get(slug)
        if prev is None or len(name) > len(prev):
            seen[slug] = name
    return [_ListingMember(slug=s, raw_name=n) for s, n in seen.items()]


# ── Per-member JSON ────────────────────────────────────────────────


def _extract_first(field: list, key: str = "value") -> Optional[str]:
    """Pull the first scalar from a Drupal-JSON field array, or None."""
    if not field:
        return None
    entry = field[0]
    if not isinstance(entry, dict):
        return None
    val = entry.get(key)
    if val is None:
        return None
    return str(val)


def _parse_member_json(slug: str, payload: dict) -> Optional[_MemberDetail]:
    """Return a _MemberDetail or None if the JSON is missing required fields."""
    member_id_raw = _extract_first(payload.get("field_member_id") or [])
    if not member_id_raw:
        return None
    try:
        member_id = int(member_id_raw)
    except (TypeError, ValueError):
        return None
    first = _extract_first(payload.get("field_first_name") or []) or ""
    last = _extract_first(payload.get("field_last_name") or []) or ""
    title = _extract_first(payload.get("title") or []) or ""
    return _MemberDetail(
        slug=slug, member_id=member_id,
        first_name=first.strip(), last_name=last.strip(),
        title=title.strip(),
    )


# ── Top-level ingest ───────────────────────────────────────────────


async def ingest_on_former_mpps(
    db: Database,
    *,
    from_parliament: int = 1,
    until_parliament: int = 44,
    delay: float = REQUEST_DELAY_SECONDS,
) -> Stats:
    """Scrape parliament-{N} listings + per-member JSON, upsert.

    Parameters
    ----------
    from_parliament, until_parliament
        Inclusive parliament range. Defaults cover all of ON history
        1867 → present (44 parliaments). Limit-friendly: pass
        ``--from-parliament 32 --until-parliament 43`` for a smoke
        test that aligns with the Hansard backwards-extension scope.
    delay
        Seconds between page fetches.
    """
    stats = Stats()

    # Pass 1: per-parliament listing scrape. Build (slug → set of parliaments)
    # AND keep the longest raw_name we see across listings (later
    # parliaments tend to have the freshest honorifics, but any name
    # is fine since per-member JSON gives us cleaner first/last).
    edges: dict[str, set[int]] = {}     # slug → {parliament_numbers}
    raw_names: dict[str, str] = {}       # slug → "Last, First"
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for n in range(from_parliament, until_parliament + 1):
            url = LISTING_URL_TMPL.format(n=n)
            try:
                r = await _get_with_retry(client, url)
            except Exception as exc:
                stats.parliaments_missing_listing.append(n)
                log.warning("on_former_mpps: parliament-%d listing failed: %s", n, exc)
                continue
            members = _parse_listing(r.text)
            if not members:
                stats.parliaments_missing_listing.append(n)
                log.warning("on_former_mpps: parliament-%d listing parsed 0 members", n)
                continue
            stats.parliaments_scanned += 1
            stats.listing_rows_seen += len(members)
            for m in members:
                edges.setdefault(m.slug, set()).add(n)
                prev = raw_names.get(m.slug)
                if prev is None or len(m.raw_name) > len(prev):
                    raw_names[m.slug] = m.raw_name
            log.info(
                "on_former_mpps: parliament-%d members=%d (cumulative unique slugs=%d)",
                n, len(members), len(edges),
            )
            if n < until_parliament:
                await asyncio.sleep(delay)

        stats.unique_slugs = len(edges)
        if not edges:
            log.warning("on_former_mpps: no listings ingested")
            return stats

        # Pass 2: fetch per-member JSON for every unique slug, in slug
        # order (deterministic across runs). The current parliament
        # is the only one whose members are sourced as
        # ``is_active=True``; everyone else lands inactive even if
        # they have an open-ended dates_of_service.
        details: dict[str, _MemberDetail] = {}
        slugs_sorted = sorted(edges.keys())
        for i, slug in enumerate(slugs_sorted):
            json_url = MEMBER_JSON_URL_TMPL.format(slug=slug)
            try:
                r = await _get_with_retry(client, json_url)
                payload = r.json()
            except Exception as exc:
                stats.member_json_failures += 1
                if len(stats.fail_samples) < 5:
                    stats.fail_samples.append(
                        f"slug={slug}: {type(exc).__name__}: {exc}"
                    )
                log.warning("on_former_mpps: member JSON failed for %s: %s", slug, exc)
                if i + 1 < len(slugs_sorted):
                    await asyncio.sleep(delay)
                continue
            stats.member_json_fetches += 1
            detail = _parse_member_json(slug, payload)
            if detail is not None:
                details[slug] = detail
            else:
                stats.member_json_failures += 1
                log.warning("on_former_mpps: member JSON missing field_member_id for %s", slug)
            if i + 1 < len(slugs_sorted):
                await asyncio.sleep(delay)

    # Pass 3: upsert politicians.
    #
    # Active-membership semantics: a politician is is_active=True iff
    # they appear in the *current* (--until-parliament if it's a full
    # 44 scan; else the highest parliament with a non-None ended_at
    # of None in the date map). Partial scans of historical ranges
    # must NOT flip is_active for current MPPs — the helper finds the
    # current parliament from the date map, not from the scan range.
    current_parliament = max(
        (n for n, (_, end) in PARLIAMENT_DATES.items() if end is None),
        default=44,
    )
    current_slugs = {slug for slug, parls in edges.items() if current_parliament in parls}

    slug_to_politician_id: dict[str, str] = {}
    for slug in slugs_sorted:
        detail = details.get(slug)
        if detail is None:
            # No member JSON → can't get a stable member_id. Skip
            # politician upsert (terms can still attach if the same
            # slug already has an existing politicians row from a
            # previous run that succeeded).
            existing = await db.fetchrow(
                "SELECT id FROM politicians WHERE ola_slug = $1 LIMIT 1",
                slug,
            )
            if existing is not None:
                slug_to_politician_id[slug] = str(existing["id"])
            continue

        is_active = slug in current_slugs

        # Prefer per-member JSON for first/last (clean form). Fall
        # back to listing-derived "Last, First" parse for the very
        # rare case where the JSON omits them.
        first = detail.first_name or ""
        last = detail.last_name or ""
        if not first or not last:
            display, parsed_first, parsed_last = _split_last_first(
                raw_names.get(slug, "")
            )
            first = first or parsed_first
            last = last or parsed_last
            display_name = detail.title or display
        else:
            display_name = detail.title or f"{first} {last}".strip()

        # Step 1 — name-match against existing ON politicians (Open
        # North current-roster rows have first/last but no
        # ola_member_id yet). On a hit, stamp ola_member_id +
        # ola_slug onto the existing row rather than inserting a
        # duplicate. Mirrors MB's pattern.
        existing = await db.fetchrow(
            """
            SELECT id, ola_member_id
              FROM politicians
             WHERE province_territory='ON' AND level='provincial'
               AND lower(unaccent(split_part(first_name, ' ', 1))) =
                   lower(unaccent(split_part($1, ' ', 1)))
               AND lower(unaccent(last_name)) = lower(unaccent($2))
               AND (ola_member_id IS NULL OR ola_member_id = $3)
             ORDER BY (ola_member_id = $3) DESC NULLS LAST,
                      (ola_slug = $4) DESC NULLS LAST
             LIMIT 1
            """,
            first, last, detail.member_id, slug,
        )

        if existing is not None:
            pol_id = str(existing["id"])
            await db.execute(
                """
                UPDATE politicians
                   SET ola_member_id = COALESCE(ola_member_id, $2),
                       ola_slug      = COALESCE(ola_slug,      $3),
                       updated_at    = now()
                 WHERE id = $1::uuid
                """,
                pol_id, detail.member_id, slug,
            )
            stats.politicians_name_matched += 1
            stats.politicians_updated += 1
        else:
            # Step 2 — net-new historical MPP. UPSERT keyed on
            # ola_member_id (migration 0037 makes the partial index
            # UNIQUE).
            source_id = f"ola.org:former-mpps:member_id={detail.member_id}"
            row = await db.fetchrow(
                """
                INSERT INTO politicians
                    (name, first_name, last_name, level, province_territory,
                     ola_member_id, ola_slug, is_active, source_id)
                VALUES
                    ($1, $2, $3, 'provincial', 'ON', $4, $5, $6, $7)
                ON CONFLICT (ola_member_id) WHERE ola_member_id IS NOT NULL
                DO UPDATE SET
                    name       = COALESCE(NULLIF(politicians.name, ''),       EXCLUDED.name),
                    first_name = COALESCE(NULLIF(politicians.first_name, ''), EXCLUDED.first_name),
                    last_name  = COALESCE(NULLIF(politicians.last_name, ''),  EXCLUDED.last_name),
                    ola_slug   = COALESCE(politicians.ola_slug,               EXCLUDED.ola_slug),
                    updated_at = now()
                RETURNING id, (xmax = 0) AS inserted
                """,
                display_name, first, last, detail.member_id, slug, is_active, source_id,
            )
            pol_id = str(row["id"])
            if row["inserted"]:
                stats.politicians_inserted += 1
            else:
                stats.politicians_updated += 1
        slug_to_politician_id[slug] = pol_id

    # Pass 4: upsert politician_terms — one row per (politician,
    # parliament) edge. Use the parliament's official start/end dates
    # from PARLIAMENT_DATES. ``source = 'ola.org:parliament-N'``
    # mirrors AB's `assembly.ab.ca:legl-N` convention so the
    # legl-keyed resolver in on_hansard.py can join on it.
    for slug, parls in edges.items():
        pol_id = slug_to_politician_id.get(slug)
        if pol_id is None:
            continue
        for n in sorted(parls):
            dates = PARLIAMENT_DATES.get(n)
            if dates is None:
                continue
            start_d, end_d = dates
            start_dt = datetime(
                start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc,
            )
            end_dt = (
                datetime(end_d.year, end_d.month, end_d.day, 23, 59, 59,
                         tzinfo=timezone.utc)
                if end_d else None
            )
            existing = await db.fetchrow(
                """
                SELECT 1 FROM politician_terms
                 WHERE politician_id = $1::uuid AND office = 'MPP'
                   AND started_at = $2
                """,
                pol_id, start_dt,
            )
            if existing is not None:
                stats.terms_skipped_existing += 1
                continue
            await db.execute(
                """
                INSERT INTO politician_terms
                    (politician_id, office, level, province_territory,
                     started_at, ended_at, source)
                VALUES
                    ($1::uuid, 'MPP', 'provincial', 'ON',
                     $2, $3, 'ola.org:parliament-' || $4::text)
                """,
                pol_id, start_dt, end_dt, str(n),
            )
            stats.terms_inserted += 1

    log.info(
        "on_former_mpps: parliaments=%d listing_rows=%d unique_slugs=%d "
        "json_fetches=%d json_failures=%d "
        "inserted=%d updated=%d name_matched=%d "
        "terms_inserted=%d terms_skipped=%d "
        "missing_listings=%s",
        stats.parliaments_scanned, stats.listing_rows_seen, stats.unique_slugs,
        stats.member_json_fetches, stats.member_json_failures,
        stats.politicians_inserted, stats.politicians_updated,
        stats.politicians_name_matched,
        stats.terms_inserted, stats.terms_skipped_existing,
        stats.parliaments_missing_listing,
    )
    return stats
