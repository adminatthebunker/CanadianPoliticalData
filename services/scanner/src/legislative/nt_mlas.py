"""NT MLA roster ingester — current 19 + ~100+ former MLAs.

Two URL paths on ntlegislativeassembly.ca expose MLA bios:

    /members/members-legislative-assembly/members      — listing of current 19
    /meet-members/mla/{slug}                           — current MLA bio
    /members/former-members                            — listing of ~100+ former
    /former-members/{slug}                             — former MLA bio

The slug itself is consistent across the two paths — the same MLA rolling
from sitting → former retains the same kebab-case ``first-last`` slug. We
key on the slug, not the path. The slug also lines up with the per-turn
``<a href="/meet-members/mla/{slug}">`` wrappers the Hansard parser sees,
so attributing speaker turns at parse time becomes an exact-string FK
join against ``politicians.nt_mla_slug``.

Idempotency: politicians upserted on (slug, source_id) — current MLAs
typically already exist via Open North (``opennorth:northwest-territories-
legislature:{slug}``) using the same slug; we stamp ``nt_mla_slug`` on
those existing rows. Former MLAs without an Open North row are inserted
fresh with ``is_active=false``.

NT runs consensus government — no party affiliation. ``party`` stays NULL
on every row inserted by this ingester. ``level='provincial'`` matches the
existing NT bills-pipeline convention (the ``province_territory`` column
already discriminates territory).
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from typing import Optional

import httpx

from ..db import Database

log = logging.getLogger(__name__)

BASE = "https://www.ntlegislativeassembly.ca"
CURRENT_LISTING = f"{BASE}/members/members-legislative-assembly/members"
FORMER_LISTING = f"{BASE}/members/former-members"

REQUEST_TIMEOUT = 30
HEADERS = {
    "User-Agent": "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.ca; admin@thebunkerops.ca)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-CA,en;q=0.9",
}

# Listing-page anchor → /meet-members/mla/{slug} (current) or
# /former-members/{slug} (former). Match either; capture the slug.
_CURRENT_HREF_RE = re.compile(
    r"href=\"/meet-members/mla/([a-z0-9-]+)\"", re.IGNORECASE,
)
_FORMER_HREF_RE = re.compile(
    r"href=\"/former-members/([a-z0-9-]+)\"", re.IGNORECASE,
)

_WS_RE = re.compile(r"\s+")
_HONORIFIC_RE = re.compile(
    r"^(?:hon\.?|honourable|mr\.?|mrs\.?|ms\.?|miss|madam|dr\.?|premier)\s+",
    re.IGNORECASE,
)


def _norm_name(name: str) -> str:
    if not name:
        return ""
    text = _HONORIFIC_RE.sub("", name.strip())
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^\w\s-]", " ", text)
    return _WS_RE.sub(" ", text).strip()


def _slug_to_name(slug: str) -> tuple[str, str, str]:
    """Convert kebab-case slug → (display, first, last).

    Best-effort fallback when bio-page fetch fails or hasn't run.
    "caitlin-cleveland" → ("Caitlin Cleveland", "Caitlin", "Cleveland").
    """
    parts = [p for p in slug.split("-") if p]
    if not parts:
        return slug, "", slug
    titled = [p.capitalize() for p in parts]
    if len(titled) == 1:
        return titled[0], "", titled[0]
    return " ".join(titled), titled[0], titled[-1]


@dataclass
class NTMember:
    slug: str               # canonical kebab-case identifier
    is_current: bool        # True if from /meet-members/mla/, False if /former-members/
    display_name: str       # best-effort title-cased name
    first_name: str
    last_name: str


@dataclass
class IngestStats:
    listings_fetched: int = 0
    current_slugs_seen: int = 0
    former_slugs_seen: int = 0
    politicians_stamped: int = 0     # existing row → nt_mla_slug attached
    politicians_inserted: int = 0    # net-new row
    politicians_skipped: int = 0     # already had a different slug, conservative skip
    failures: list[str] = dc_field(default_factory=list)


# ── Listing fetch ───────────────────────────────────────────────────


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        log.warning("nt_mlas: fetch %s failed: %s", url, exc)
        return None


async def _harvest_current_slugs(client: httpx.AsyncClient) -> set[str]:
    html = await _fetch(client, CURRENT_LISTING)
    if not html:
        return set()
    return set(_CURRENT_HREF_RE.findall(html))


async def _harvest_former_slugs(client: httpx.AsyncClient) -> set[str]:
    """Walk paginated /members/former-members?page=N until empty."""
    seen: set[str] = set()
    page = 0
    while True:
        url = FORMER_LISTING if page == 0 else f"{FORMER_LISTING}?page={page}"
        html = await _fetch(client, url)
        if not html:
            break
        slugs = set(_FORMER_HREF_RE.findall(html))
        new = slugs - seen
        if not new:
            break
        seen |= new
        page += 1
        if page > 30:  # defensive cap
            log.warning("nt_mlas: former-members listing exceeded 30 pages — stopping")
            break
        await asyncio.sleep(0.5)
    return seen


# ── Politicians upsert ──────────────────────────────────────────────


async def _stamp_or_insert(
    db: Database, m: NTMember, stats: IngestStats,
) -> Optional[str]:
    """Return politicians.id (uuid as text), or None on skip."""

    # 1. Already stamped with same slug → idempotent no-op.
    row = await db.fetchrow(
        "SELECT id::text AS id FROM politicians WHERE nt_mla_slug = $1",
        m.slug,
    )
    if row:
        return row["id"]

    # 2. Open North roster usually contains current MLAs. Match by
    #    source_id pattern that mirrors the slug, OR by normalised name.
    on_source = f"opennorth:northwest-territories-legislature:{m.slug}"
    row = await db.fetchrow(
        """
        SELECT id::text AS id, nt_mla_slug
          FROM politicians
         WHERE province_territory = 'NT'
           AND source_id = $1
        """,
        on_source,
    )
    if row is None:
        # Name-match fallback (slug normalisation drift, accent issues).
        norm = _norm_name(f"{m.first_name} {m.last_name}")
        if norm:
            cands = await db.fetch(
                """
                SELECT id::text AS id, nt_mla_slug
                  FROM politicians
                 WHERE province_territory = 'NT'
                   AND lower(unaccent(coalesce(first_name, '') || ' ' || coalesce(last_name, ''))) = $1
                """,
                norm,
            )
            if len(cands) == 1:
                row = cands[0]

    if row is not None:
        if row["nt_mla_slug"] and row["nt_mla_slug"] != m.slug:
            stats.politicians_skipped += 1
            stats.failures.append(
                f"politicians.{row['id']} already has nt_mla_slug="
                f"{row['nt_mla_slug']}, refusing to overwrite with {m.slug}"
            )
            return None
        await db.execute(
            """
            UPDATE politicians
               SET nt_mla_slug = $2,
                   is_active   = $3,
                   updated_at  = now()
             WHERE id = $1::uuid
            """,
            row["id"], m.slug, m.is_current,
        )
        stats.politicians_stamped += 1
        return row["id"]

    # 3. Fresh insert (former MLA not in Open North roster).
    src_id = (
        f"ntlegislativeassembly.ca:mla:{m.slug}" if m.is_current
        else f"ntlegislativeassembly.ca:former-member:{m.slug}"
    )
    inserted = await db.fetchrow(
        """
        INSERT INTO politicians
            (name, first_name, last_name, level, province_territory,
             nt_mla_slug, is_active, source_id)
        VALUES
            ($1, $2, $3, 'provincial', 'NT', $4, $5, $6)
        ON CONFLICT (nt_mla_slug) WHERE nt_mla_slug IS NOT NULL
        DO UPDATE SET updated_at = now()
        RETURNING id::text AS id
        """,
        m.display_name, m.first_name, m.last_name,
        m.slug, m.is_current, src_id,
    )
    stats.politicians_inserted += 1
    return inserted["id"]


# ── Public entry point ──────────────────────────────────────────────


async def ingest_nt_mlas(
    db: Database, *, include_former: bool = True,
) -> IngestStats:
    """Stamp ``nt_mla_slug`` on existing NT politicians + insert any
    former MLAs not yet in the table.

    Re-runs are no-ops on the slug-already-stamped path; on the
    former-MLA insert path the partial UNIQUE index catches duplicates.
    """
    stats = IngestStats()

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        current = await _harvest_current_slugs(client)
        stats.listings_fetched += 1
        stats.current_slugs_seen = len(current)
        log.info("nt_mlas: harvested %d current slugs", len(current))

        former: set[str] = set()
        if include_former:
            former = await _harvest_former_slugs(client)
            stats.listings_fetched += 1
            stats.former_slugs_seen = len(former)
            log.info("nt_mlas: harvested %d former slugs", len(former))

    # Process current first so already-existing Open North rows get
    # is_active=true; former runs after so any slug appearing on both
    # listings (a returning politician) keeps is_active=true.
    members: list[NTMember] = []
    for slug in sorted(former):
        if slug in current:
            continue  # de-dup; current pass takes precedence
        display, first, last = _slug_to_name(slug)
        members.append(NTMember(
            slug=slug, is_current=False,
            display_name=display, first_name=first, last_name=last,
        ))
    for slug in sorted(current):
        display, first, last = _slug_to_name(slug)
        members.append(NTMember(
            slug=slug, is_current=True,
            display_name=display, first_name=first, last_name=last,
        ))

    for m in members:
        await _stamp_or_insert(db, m, stats)

    log.info(
        "nt_mlas: current=%d former=%d stamped=%d inserted=%d skipped=%d",
        stats.current_slugs_seen, stats.former_slugs_seen,
        stats.politicians_stamped, stats.politicians_inserted,
        stats.politicians_skipped,
    )
    return stats
