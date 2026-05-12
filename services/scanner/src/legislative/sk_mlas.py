"""SK MLA roster ingester — sourced from the Hansard speaker index.

Saskatchewan publishes no per-MLA stable identifier on legassembly.sk.ca:
the public MLA detail page URL is ``?first=Scott&last=Moe`` and the photo
asset path uses opaque CMS IDs. The cleanest roster source we found is
the per-legislature **Hansard speaker index** at:

    https://docs.legassembly.sk.ca/legdocs/Assembly/Debates/Indexes/{N}/{N}L-SP-full.html

That file lists every MLA who has spoken during the parliament, in this
shape:

    <li id='1'><b><a href='30L-SP-B.html#1'>Beaudry, Hon. Chris (Sask Party,
        Kelvington-Wadena) <i>s.2</i>: Minister of Energy and Resources</a></b>...

We synthesise the slug ``firstname-lastname`` (lowercased + diacritic-
stripped + dashes) and persist it as ``politicians.sk_assembly_slug``,
which the SK Hansard speaker resolver then uses to attach speaker turns.

Idempotency: ON CONFLICT on the ``sk_assembly_slug`` partial unique
index. Re-runs upsert.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from typing import Optional

import httpx
import orjson

from ..db import Database

log = logging.getLogger(__name__)

INDEX_URL_TMPL = (
    "https://docs.legassembly.sk.ca/legdocs/Assembly/Debates/Indexes/"
    "{n}/{n}L-SP-full.html"
)

REQUEST_TIMEOUT = 30
HEADERS = {
    "User-Agent": "CanadianPoliticalDataBot/1.0 (+https://canadianpoliticaldata.ca; admin@thebunkerops.ca)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-CA,en;q=0.9",
}

# Match a single speaker-index entry. The entries are linked anchor blocks:
#   <a href='30L-SP-B.html#85'>Beck, Carla (NDP, Regina Lakeview) <i>s.1, 2</i>:
#       Leader of the Opposition</a>
# Some entries have multiple <i>...</i> portfolio blocks (cabinet ministers
# with split responsibilities) or trailing punctuation after the
# constituency. Capture everything up to </a> as `remainder` and pull
# session participation + cabinet role out of it post-match.
#
# Honorifics: 30th-leg index uses bare names (only Hon./Dr. as prefix).
# Older legislatures (29L and below) sometimes use Mr./Ms./Mrs./Miss
# prefixes ("Goudy, Mr. Todd"). Capture all of them so the synthesised
# slug stays clean (todd-goudy, not mr-todd-goudy).
_ENTRY_RE = re.compile(
    r"<a\s+href='[^']+'>"
    r"(?P<last>[^,<]+),\s+"
    r"(?P<honorific>Hon\.|Dr\.|Mr\.|Mrs\.|Ms\.|Miss)?\s*"
    r"(?P<first>[^(<]+?)\s*"
    r"\((?P<party>[^,)]+),\s*(?P<constituency>[^)]+)\)"
    r"(?P<remainder>.*?)"
    r"</a>",
    re.IGNORECASE | re.DOTALL,
)

# Sessions: <i>s.1, 2</i> — find every italic-wrapped session list.
_SESSION_TAG_RE = re.compile(r"<i>s\.([\d,\s]+)</i>", re.IGNORECASE)

# Cabinet role text follows ":" and stops at the next "<" or end.
# Multiple roles separated by ". " stay joined.
_ROLE_RE = re.compile(r":\s*([^<]+?)(?=\s*<|\s*$)", re.IGNORECASE | re.DOTALL)

_WS_RE = re.compile(r"\s+")


def _norm_slug(first: str, last: str) -> str:
    """Synthesise kebab-case slug from name (e.g. "carla-beck")."""
    text = f"{first} {last}".strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    return text


def _normalise_party(raw: str) -> str:
    """SK speaker index emits "Sask Party" / "NDP" / "Independent". Keep as-is."""
    return _WS_RE.sub(" ", raw).strip()


@dataclass
class SKMember:
    slug: str
    last_name: str
    first_name: str
    display_name: str
    honorific: Optional[str]      # "Hon." / "Dr." / None
    party: str
    constituency: str
    sessions: list[int]            # [1, 2] from "s.1, 2"
    cabinet_role: Optional[str]    # "Minister of Health" / "Speaker" / None


@dataclass
class IngestStats:
    parliaments_fetched: int = 0
    entries_parsed: int = 0
    politicians_inserted: int = 0
    politicians_updated: int = 0
    politicians_retired: int = 0
    failures: list[str] = dc_field(default_factory=list)


# ── Index fetch + parse ─────────────────────────────────────────────


async def _fetch_index(client: httpx.AsyncClient, parliament: int) -> Optional[str]:
    url = INDEX_URL_TMPL.format(n=parliament)
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        log.warning("sk_mlas: fetch %s failed: %s", url, exc)
        return None


def _parse_index(html: str) -> list[SKMember]:
    members: list[SKMember] = []
    seen: set[str] = set()
    for m in _ENTRY_RE.finditer(html):
        last = _WS_RE.sub(" ", m.group("last")).strip()
        first = _WS_RE.sub(" ", m.group("first")).strip()
        honorific = m.group("honorific")
        party = _normalise_party(m.group("party"))
        constituency = _WS_RE.sub(" ", m.group("constituency")).strip()
        if last.lower() == "speaker" and not first:
            continue

        remainder = m.group("remainder") or ""
        sessions: list[int] = []
        for tag in _SESSION_TAG_RE.findall(remainder):
            sessions.extend(int(s) for s in re.findall(r"\d+", tag))

        # Concatenate cabinet roles — index uses `<i>s.X</i>: Role 1.
        # <i>s.Y</i>: Role 2` for ministers whose portfolios changed.
        roles = [
            _WS_RE.sub(" ", r).strip().rstrip(".")
            for r in _ROLE_RE.findall(remainder)
        ]
        roles = [r for r in roles if r]
        cabinet_role = "; ".join(roles) if roles else None

        slug = _norm_slug(first, last)
        if not slug or slug in seen:
            continue
        seen.add(slug)

        # Only "Hon." / "Dr." flag a meaningful prefix on display name
        # (cabinet minister / honorary title). "Mr./Ms./Mrs./Miss" are
        # editorial conventions in older indexes — drop them.
        prefix = ""
        if honorific and honorific.lower().startswith(("hon", "dr")):
            prefix = f"{honorific} "
        display = f"{prefix}{first} {last}".strip()

        members.append(SKMember(
            slug=slug, last_name=last, first_name=first,
            display_name=display, honorific=honorific,
            party=party, constituency=constituency,
            sessions=sorted(set(sessions)), cabinet_role=cabinet_role,
        ))
    return members


# ── Politicians upsert ──────────────────────────────────────────────


async def _upsert_member(
    db: Database, m: SKMember, parliament: int, stats: IngestStats,
) -> Optional[str]:
    extras = {
        "cabinet_role": m.cabinet_role,
        "session_participation": [f"{parliament}L{s}S" for s in m.sessions],
        "honorific": m.honorific,
    }
    extras = {k: v for k, v in extras.items() if v}
    extras_json = orjson.dumps(extras).decode("utf-8")

    source_id = f"legassembly.sk.ca:{parliament}L-speaker-index:{m.slug}"

    row = await db.fetchrow(
        """
        INSERT INTO politicians
            (name, first_name, last_name, level, province_territory,
             party, constituency_name, elected_office,
             sk_assembly_slug, is_active, source_id, extras)
        VALUES
            ($1, $2, $3, 'provincial', 'SK',
             $4, $5, 'MLA',
             $6, true, $7, $8::jsonb)
        ON CONFLICT (sk_assembly_slug) WHERE sk_assembly_slug IS NOT NULL
        DO UPDATE SET
            name              = EXCLUDED.name,
            first_name        = EXCLUDED.first_name,
            last_name         = EXCLUDED.last_name,
            party             = EXCLUDED.party,
            constituency_name = EXCLUDED.constituency_name,
            elected_office    = EXCLUDED.elected_office,
            is_active         = EXCLUDED.is_active,
            extras            = politicians.extras || EXCLUDED.extras,
            updated_at        = now()
        RETURNING id::text AS id, (xmax = 0) AS inserted
        """,
        m.display_name, m.first_name, m.last_name,
        m.party, m.constituency,
        m.slug, source_id, extras_json,
    )
    if row is None:
        stats.failures.append(f"upsert returned no row for {m.slug}")
        return None
    if row["inserted"]:
        stats.politicians_inserted += 1
    else:
        stats.politicians_updated += 1
    return row["id"]


# ── Public entry point ──────────────────────────────────────────────


# Current SK chamber is 61 seats. We require the parsed roster to be at
# least this large before flipping anyone retired — the Hansard speaker
# index only lists members who have spoken, so a transient fetch issue or
# a sitting-but-silent MLA early in a parliament could leave the set
# under-populated. Below the floor we skip the retirement pass entirely.
SK_CURRENT_PARLIAMENT = 30
SK_RETIREMENT_ROSTER_FLOOR = 55


async def _detect_sk_retirements(
    db: Database, current_ids: set[str], stats: IngestStats,
) -> None:
    """Mark SK politicians retired when they're active in the DB but were
    not in the current-parliament roster snapshot.

    Mirrors the body of compare_politicians.detect_retirements but
    identifies the candidate set by (level, province_territory, is_active)
    rather than by source_id prefix — SK politicians are keyed on
    sk_assembly_slug with no opennorth source_id, so the canonical helper
    can't see them.
    """
    if len(current_ids) < SK_RETIREMENT_ROSTER_FLOOR:
        msg = (
            f"retirement pass skipped — current roster only "
            f"{len(current_ids)} members (floor {SK_RETIREMENT_ROSTER_FLOOR}); "
            f"likely fetch issue or sparse speaker index"
        )
        log.warning("sk_mlas: %s", msg)
        stats.failures.append(msg)
        return

    rows = await db.fetch(
        """
        SELECT id::text AS id, name, party, elected_office, level,
               province_territory, constituency_id
          FROM politicians
         WHERE level = 'provincial'
           AND province_territory = 'SK'
           AND is_active = true
        """,
    )
    retired = [r for r in rows if r["id"] not in current_ids]
    if not retired:
        return

    log.info("sk_mlas: marking %d SK politician(s) retired", len(retired))

    for row in retired:
        pid = row["id"]
        old_value = {
            "name": row.get("name"),
            "party": row.get("party"),
            "office": row.get("elected_office"),
            "level": row.get("level"),
            "province_territory": row.get("province_territory"),
            "constituency_id": row.get("constituency_id"),
        }
        try:
            await db.execute(
                """
                INSERT INTO politician_changes
                  (politician_id, change_type, old_value, new_value, severity)
                VALUES ($1, 'retired', $2, NULL, 'notable')
                """,
                pid,
                orjson.dumps(old_value).decode(),
            )
            await db.execute(
                """
                UPDATE politician_terms
                   SET ended_at = now()
                 WHERE politician_id = $1
                   AND ended_at IS NULL
                """,
                pid,
            )
            await db.execute(
                """
                UPDATE politicians
                   SET is_active = false,
                       updated_at = now()
                 WHERE id = $1
                """,
                pid,
            )
            stats.politicians_retired += 1
        except Exception as exc:  # pragma: no cover - defensive
            log.exception(
                "sk_mlas: failed to retire politician %s: %s", pid, exc,
            )
            stats.failures.append(f"retire failed for {pid}: {exc}")


async def ingest_sk_mlas(
    db: Database, *, parliaments: Optional[list[int]] = None,
) -> IngestStats:
    """Fetch SK Hansard speaker index for the given parliaments and
    upsert each MLA listing. Default: 30th legislature only.

    Re-runs are idempotent (UPSERT keyed on sk_assembly_slug). Cabinet
    roles update; ``extras`` merges to preserve prior keys.

    When the current parliament (30L) is in the parliaments list, runs a
    retirement pass at the end: any SK politician with is_active=true who
    is NOT in the freshly-parsed current roster gets soft-closed (open
    politician_terms.ended_at set to NOW(), is_active flipped false,
    politician_changes audit row written). The pass is gated on
    SK_RETIREMENT_ROSTER_FLOOR so a sparse fetch can't accidentally
    retire sitting members.
    """
    stats = IngestStats()
    parls = parliaments or [SK_CURRENT_PARLIAMENT]
    current_roster_ids: set[str] = set()

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for parliament in parls:
            html = await _fetch_index(client, parliament)
            if html is None:
                stats.failures.append(f"speaker index fetch failed for {parliament}L")
                continue
            stats.parliaments_fetched += 1
            members = _parse_index(html)
            stats.entries_parsed += len(members)
            log.info(
                "sk_mlas: parliament=%dL parsed=%d members",
                parliament, len(members),
            )
            for m in members:
                pid = await _upsert_member(db, m, parliament, stats)
                if pid and parliament == SK_CURRENT_PARLIAMENT:
                    current_roster_ids.add(pid)
            # Polite gap between parliaments.
            await asyncio.sleep(0.3)

    if SK_CURRENT_PARLIAMENT in parls:
        await _detect_sk_retirements(db, current_roster_ids, stats)

    log.info(
        "sk_mlas: parliaments=%d entries=%d inserted=%d updated=%d "
        "retired=%d failures=%d",
        stats.parliaments_fetched, stats.entries_parsed,
        stats.politicians_inserted, stats.politicians_updated,
        stats.politicians_retired, len(stats.failures),
    )
    return stats
