"""QC historical MNA roster backfill.

Quebec's Assemblée nationale publishes an alphabetical "Liste des
députés depuis 1764" at:

    https://www.assnat.qc.ca/fr/membres/notices/index.html
    https://www.assnat.qc.ca/fr/membres/notices/index-{b,c,d,ef,g,hi,
                                                     jk,l,m,no,p,qr,
                                                     s,tu,vz}.html

That's 16 letter-pages covering ~2,500 MNAs since 1764. Every link on
those pages goes to a per-MNA detail page using one of two URL shapes
that share the same numeric trailer:

    /fr/deputes/{slug}-{id}/index.html               (most members)
    /fr/patrimoine/anciens-parlementaires/{slug}-{id}.html  (some pre-Confederation)

The trailing integer is ``qc_assnat_id``: the assembly's stable
per-MNA identifier (the same one ``qc_mnas.py`` already uses for
current 124 MNAs and ``qc_bills.py`` joins on for sponsor FK).

Unlike Ontario (per-parliament listings → one row per (member,
parliament) edge), QC publishes only the alphabetical roster + per-MNA
biography pages. Per-legislature membership data is **not exposed
structurally** — it only appears in the bio's prose. We therefore:

1. Walk the 16 letter-pages, collect every (slug, qc_assnat_id,
   raw_name, is_current) tuple.
2. For each non-current MNA, GET the bio page once and extract a
   coarse career span via prose-regex (first ``Élu(e) ... en YYYY``
   for ``started_at``, last of ``Défait(e) en YYYY``, ``Démissionna
   ... YYYY``, or ``Décéda ... YYYY`` for ``ended_at``; NULL if no end
   marker is detected).
3. Upsert ``politicians`` keyed on ``qc_assnat_id``. Existing QC
   politicians (typically Open North current-roster rows that
   ``qc_mnas.py`` has already stamped with ``qc_assnat_id``) are
   updated in place; new historical rows go in with
   ``is_active=false``.
4. Insert one ``politician_terms`` row per MNA with a single wide span
   covering their entire career — ``source =
   'assnat.qc.ca:former-mnas'``. The dated post-pass resolver in
   ``qc_hansard.py`` joins on this term.

Why one wide span instead of one row per legislature: the bios narrate
careers as prose, with electoral defeats and re-elections embedded in
running text ("Élue ... en 1981. ... Défaite en 1985. ... Élue ...
en 1989"). Reconstructing each discrete mandate from prose is brittle
and the date-windowed resolver is satisfied by a single span — gaps
within the span (1985-1989 in the example) just don't have any
Hansard speeches to attribute, so over-including them is harmless.

Idempotency: politicians upserted on qc_assnat_id; politician_terms
upserted on (politician_id, office, started_at, source). A full
re-run is a no-op.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timezone
from typing import Optional

import httpx

from ..db import Database
from .ab_former_mlas import _get_with_retry

log = logging.getLogger(__name__)

LETTER_INDEX_URLS: list[str] = [
    "https://www.assnat.qc.ca/fr/membres/notices/index.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-b.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-c.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-d.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-ef.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-g.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-hi.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-jk.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-l.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-m.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-no.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-p.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-qr.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-s.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-tu.html",
    "https://www.assnat.qc.ca/fr/membres/notices/index-vz.html",
]

BIO_URL_DEPUTES_TMPL = "https://www.assnat.qc.ca/fr/deputes/{slug}-{id}/biographie.html"
BIO_URL_PATRIMOINE_TMPL = (
    "https://www.assnat.qc.ca/fr/patrimoine/anciens-parlementaires/{slug}-{id}.html"
)

HEADERS = {
    "User-Agent": "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.ca)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.5",
}

REQUEST_DELAY_SECONDS = 1.5  # Polite to assnat.qc.ca

# Both URL shapes carry the same numeric MNA id at the end. Capture
# (slug, id, kind) so the bio fetcher can reconstruct the right URL.
_LISTING_LINK_RE = re.compile(
    r'href="https?://www\.assnat\.qc\.ca'
    r'/fr/(?P<kind>deputes|patrimoine/anciens-parlementaires)/'
    r'(?P<slug>[a-z0-9][a-z0-9-]*)-(?P<id>\d+)'
    r'(?:/index\.html|\.html)"'
    r'[^>]*>(?P<name>[^<]+)</a>'
    r'(?P<after>[^<]*)',  # Captures "&nbsp;(en fonction)" trailing
    re.IGNORECASE,
)

# Career-bracket regexes operating on de-tagged bio text.
# The bio prose follows a standard pattern; matches are conservative.
_ELU_RE = re.compile(
    r"\b(?:[Éé]lue?|R[ée]{1,2}lue?)\b[^.]{0,160}?\ben\s+(\d{4})\b",
)
_DEFAITE_RE = re.compile(
    r"\b[Dd][ée]fait[ee]?\b[^.]{0,80}?\ben\s+(\d{4})\b",
)
_DEMISSION_RE = re.compile(
    r"\b[Dd][ée]missionna\b[^.]{0,200}?\b(\d{4})\b",
)
_DECES_RE = re.compile(
    r"\b[Dd][ée]c[ée]da\b[^.]{0,160}?\b(\d{4})\b",
)


@dataclass
class _ListingMember:
    slug: str
    qc_assnat_id: int
    raw_name: str       # "Last, First" form from the listing
    bio_kind: str       # "deputes" or "patrimoine/anciens-parlementaires"
    is_current: bool    # True if "(en fonction)" suffix present


@dataclass
class _CareerSpan:
    started_at: Optional[date]
    ended_at: Optional[date]


@dataclass
class Stats:
    letter_pages_scanned: int = 0
    listing_rows_seen: int = 0
    unique_mnas: int = 0
    bios_fetched: int = 0
    bios_failed: int = 0
    bios_skipped_current: int = 0
    bios_skipped_existing: int = 0
    spans_extracted: int = 0
    spans_no_match: int = 0
    politicians_inserted: int = 0
    politicians_updated: int = 0
    politicians_name_matched: int = 0
    terms_inserted: int = 0
    terms_skipped_existing: int = 0
    fail_samples: list[str] = dc_field(default_factory=list)


# ── Listing parse ──────────────────────────────────────────────────


def _parse_listing(html: str) -> list[_ListingMember]:
    """Extract (slug, qc_assnat_id, raw_name, bio_kind, is_current) tuples
    from one alphabet-letter index page.
    """
    seen: dict[int, _ListingMember] = {}
    for m in _LISTING_LINK_RE.finditer(html):
        try:
            mna_id = int(m.group("id"))
        except (TypeError, ValueError):
            continue
        slug = m.group("slug").strip().lower()
        # Normalise NBSP, decode the few HTML entities the page uses.
        name = (m.group("name") or "").replace(" ", " ").replace("&nbsp;", " ")
        name = re.sub(r"\s+", " ", name).strip()
        after = (m.group("after") or "").lower()
        is_current = "(en fonction)" in after
        kind = m.group("kind")
        # Same MNA can appear multiple times on a letter page (no
        # known reason but defensive). Keep first; trust same-id
        # entries are the same person.
        if mna_id in seen:
            continue
        seen[mna_id] = _ListingMember(
            slug=slug, qc_assnat_id=mna_id, raw_name=name,
            bio_kind=kind, is_current=is_current,
        )
    return list(seen.values())


# ── Bio parse ──────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    """Crude tag stripper. Sufficient for prose-scanning regex; we
    don't care about preserving structure, only about reaching the
    text inside <p> tags.
    """
    text = _HTML_TAG_RE.sub(" ", html)
    text = text.replace(" ", " ").replace("&nbsp;", " ")
    text = text.replace("&amp;", "&").replace("&eacute;", "é")
    text = re.sub(r"\s+", " ", text)
    return text


def _extract_career_span(bio_html: str) -> _CareerSpan:
    """Parse the bio prose for first/last career-bracket years.

    Returns ``_CareerSpan(started_at=None, ended_at=None)`` if no
    "Élu(e) ... en YYYY" pattern is found — in that case the caller
    skips term insertion and the politician is added without a span.
    """
    text = _strip_html(bio_html)

    elu_years = [int(m.group(1)) for m in _ELU_RE.finditer(text) if 1750 <= int(m.group(1)) <= 2100]
    defait_years = [int(m.group(1)) for m in _DEFAITE_RE.finditer(text) if 1750 <= int(m.group(1)) <= 2100]
    demis_years = [int(m.group(1)) for m in _DEMISSION_RE.finditer(text) if 1750 <= int(m.group(1)) <= 2100]
    deces_years = [int(m.group(1)) for m in _DECES_RE.finditer(text) if 1750 <= int(m.group(1)) <= 2100]

    if not elu_years:
        return _CareerSpan(started_at=None, ended_at=None)

    start_year = min(elu_years)
    end_candidates: list[int] = []
    if defait_years:
        end_candidates.append(max(defait_years))
    if demis_years:
        end_candidates.append(max(demis_years))
    if deces_years:
        end_candidates.append(max(deces_years))

    # End must be >= start to be plausible; otherwise treat as
    # "career still ongoing in record" → NULL ended_at.
    end_year = max((y for y in end_candidates if y >= start_year), default=None)

    started = date(start_year, 1, 1)
    ended = date(end_year, 12, 31) if end_year else None
    return _CareerSpan(started_at=started, ended_at=ended)


# ── Top-level ingest ───────────────────────────────────────────────


def _bio_url(member: _ListingMember) -> str:
    if member.bio_kind == "deputes":
        return BIO_URL_DEPUTES_TMPL.format(slug=member.slug, id=member.qc_assnat_id)
    return BIO_URL_PATRIMOINE_TMPL.format(slug=member.slug, id=member.qc_assnat_id)


def _split_listing_name(raw: str) -> tuple[str, str, str]:
    """Parse "Last, First" or "Last, First Middle" → (display, first, last).

    Listing names use "Last,&nbsp;First" with NBSP. We normalise to a
    plain space before this is called.
    """
    if "," in raw:
        last, _, first = raw.partition(",")
        last = last.strip()
        first = first.strip()
        # Drop any honorific suffix tokens (rare on QC listings, but
        # be defensive: "Hon.", "K.C.", etc.)
        first = re.sub(r"\b(?:Hon\.?|K\.C\.?|C\.R\.?)\b", "", first).strip()
        display = f"{first} {last}".strip() if first else last
        return display, first, last
    # No comma — treat whole string as last name.
    return raw.strip(), "", raw.strip()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


async def ingest_qc_former_mnas(
    db: Database,
    *,
    delay: float = REQUEST_DELAY_SECONDS,
    limit: Optional[int] = None,
    skip_bio_for_existing: bool = True,
) -> Stats:
    """Walk the 16 alphabet-index pages + per-MNA bio pages, upsert.

    Parameters
    ----------
    delay
        Seconds between page fetches.
    limit
        If set, cap the total number of MNAs processed (after the
        listing-walk dedup). Useful for smoke tests.
    skip_bio_for_existing
        When True (default), MNAs already in ``politicians`` with
        non-NULL ``qc_assnat_id`` skip the bio fetch entirely — saves
        ~125 requests on every re-run when no new MNAs landed.
    """
    stats = Stats()

    # Pass 1: walk 16 alphabet indexes, build the unique-MNA map.
    members: dict[int, _ListingMember] = {}
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for url in LETTER_INDEX_URLS:
            try:
                r = await _get_with_retry(client, url)
            except Exception as exc:
                log.warning("qc_former_mnas: letter index failed %s: %s", url, exc)
                continue
            stats.letter_pages_scanned += 1
            page_members = _parse_listing(r.text)
            stats.listing_rows_seen += len(page_members)
            for m in page_members:
                # Same MNA can appear across different letter indexes
                # only via DOM-injected cross-references, which is
                # rare. First-seen wins (earlier alphabet wins).
                members.setdefault(m.qc_assnat_id, m)
            log.info(
                "qc_former_mnas: %s yielded %d MNAs (cumulative=%d)",
                url, len(page_members), len(members),
            )
            await asyncio.sleep(delay)

        stats.unique_mnas = len(members)
        if not members:
            log.warning("qc_former_mnas: no MNAs gathered from listings")
            return stats

        # Pre-fetch existing politicians to inform skip_bio_for_existing
        # and the politicians-upsert name-match step.
        existing_rows = await db.fetch(
            """
            SELECT id::text AS id, qc_assnat_id, name, first_name, last_name
              FROM politicians
             WHERE level = 'provincial' AND province_territory = 'QC'
            """
        )
        existing_by_id: dict[int, dict] = {}
        existing_by_name: dict[str, dict] = {}
        for r in existing_rows:
            if r["qc_assnat_id"] is not None:
                existing_by_id[r["qc_assnat_id"]] = dict(r)
            full = _norm(f"{r['first_name'] or ''} {r['last_name'] or ''}")
            if full:
                existing_by_name.setdefault(full, dict(r))

        # Pass 2: bio fetch + career-span extraction. Skip current
        # MNAs (we trust qc_mnas.py's enrichment for their qc_assnat_id)
        # and skip any already-known qc_assnat_id when configured.
        order = sorted(members.values(), key=lambda m: m.qc_assnat_id)
        if limit is not None:
            order = order[: int(limit)]

        spans: dict[int, _CareerSpan] = {}
        for i, m in enumerate(order):
            if m.is_current:
                stats.bios_skipped_current += 1
                # Current MNAs implicitly span "now → null" already
                # via opennorth term; no extra span needed.
                continue
            if skip_bio_for_existing and m.qc_assnat_id in existing_by_id:
                stats.bios_skipped_existing += 1
                continue
            url = _bio_url(m)
            try:
                r = await _get_with_retry(client, url)
            except Exception as exc:
                stats.bios_failed += 1
                if len(stats.fail_samples) < 5:
                    stats.fail_samples.append(
                        f"id={m.qc_assnat_id} slug={m.slug}: {type(exc).__name__}"
                    )
                log.warning("qc_former_mnas: bio fetch failed for %s: %s", m.slug, exc)
                if i + 1 < len(order):
                    await asyncio.sleep(delay)
                continue
            stats.bios_fetched += 1
            span = _extract_career_span(r.text)
            if span.started_at is None:
                stats.spans_no_match += 1
            else:
                stats.spans_extracted += 1
                spans[m.qc_assnat_id] = span
            if i + 1 < len(order):
                await asyncio.sleep(delay)

    # Pass 3: politicians upsert.
    qc_id_to_pol_id: dict[int, str] = {}
    for m in order:
        # Re-scope: we still want to upsert all order members, even
        # those we skipped bio fetching for, so terms can attach.
        existing = existing_by_id.get(m.qc_assnat_id)
        if existing is not None:
            qc_id_to_pol_id[m.qc_assnat_id] = existing["id"]
            continue

        display, first, last = _split_listing_name(m.raw_name)

        # Name-match against existing rows that might have qc_assnat_id
        # NULL (defensive — current ingester should have stamped them
        # already, but covers any drift).
        full_norm = _norm(f"{first} {last}")
        nm_hit = existing_by_name.get(full_norm) if full_norm else None
        if nm_hit is not None and nm_hit.get("qc_assnat_id") in (None, m.qc_assnat_id):
            pol_id = nm_hit["id"]
            await db.execute(
                """
                UPDATE politicians
                   SET qc_assnat_id = COALESCE(qc_assnat_id, $2),
                       updated_at   = now()
                 WHERE id = $1::uuid
                """,
                pol_id, m.qc_assnat_id,
            )
            stats.politicians_name_matched += 1
            stats.politicians_updated += 1
            qc_id_to_pol_id[m.qc_assnat_id] = pol_id
            existing_by_id[m.qc_assnat_id] = {
                "id": pol_id, "qc_assnat_id": m.qc_assnat_id,
                "name": display, "first_name": first, "last_name": last,
            }
            continue

        is_active = m.is_current
        source_id = f"assnat.qc.ca:former-mnas:qc_assnat_id={m.qc_assnat_id}"
        row = await db.fetchrow(
            """
            INSERT INTO politicians
                (name, first_name, last_name, level, province_territory,
                 qc_assnat_id, is_active, source_id)
            VALUES
                ($1, $2, $3, 'provincial', 'QC', $4, $5, $6)
            ON CONFLICT (qc_assnat_id) WHERE qc_assnat_id IS NOT NULL
            DO UPDATE SET
                name       = COALESCE(NULLIF(politicians.name, ''),       EXCLUDED.name),
                first_name = COALESCE(NULLIF(politicians.first_name, ''), EXCLUDED.first_name),
                last_name  = COALESCE(NULLIF(politicians.last_name, ''),  EXCLUDED.last_name),
                updated_at = now()
            RETURNING id::text AS id, (xmax = 0) AS inserted
            """,
            display, first, last, m.qc_assnat_id, is_active, source_id,
        )
        pol_id = row["id"]
        if row["inserted"]:
            stats.politicians_inserted += 1
        else:
            stats.politicians_updated += 1
        qc_id_to_pol_id[m.qc_assnat_id] = pol_id

    # Pass 4: politician_terms upsert — single career-span per MNA.
    # Skip current MNAs (their term comes from opennorth ingest).
    for m in order:
        if m.is_current:
            continue
        pol_id = qc_id_to_pol_id.get(m.qc_assnat_id)
        if pol_id is None:
            continue
        span = spans.get(m.qc_assnat_id)
        if span is None or span.started_at is None:
            # No prose match → no span. Politician row exists but
            # won't be a candidate in the dated post-pass.
            continue
        start_dt = datetime(
            span.started_at.year, span.started_at.month, span.started_at.day,
            tzinfo=timezone.utc,
        )
        end_dt = (
            datetime(
                span.ended_at.year, span.ended_at.month, span.ended_at.day,
                23, 59, 59, tzinfo=timezone.utc,
            )
            if span.ended_at else None
        )
        existing = await db.fetchrow(
            """
            SELECT 1 FROM politician_terms
             WHERE politician_id = $1::uuid
               AND office = 'MNA'
               AND source = 'assnat.qc.ca:former-mnas'
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
                ($1::uuid, 'MNA', 'provincial', 'QC',
                 $2, $3, 'assnat.qc.ca:former-mnas')
            """,
            pol_id, start_dt, end_dt,
        )
        stats.terms_inserted += 1

    log.info(
        "qc_former_mnas: pages=%d listing_rows=%d unique=%d "
        "bios=%d bio_fail=%d bio_skip_current=%d bio_skip_existing=%d "
        "spans=%d span_miss=%d "
        "pols_inserted=%d pols_updated=%d pols_name_matched=%d "
        "terms_inserted=%d terms_skipped=%d",
        stats.letter_pages_scanned, stats.listing_rows_seen, stats.unique_mnas,
        stats.bios_fetched, stats.bios_failed,
        stats.bios_skipped_current, stats.bios_skipped_existing,
        stats.spans_extracted, stats.spans_no_match,
        stats.politicians_inserted, stats.politicians_updated,
        stats.politicians_name_matched,
        stats.terms_inserted, stats.terms_skipped_existing,
    )
    return stats
