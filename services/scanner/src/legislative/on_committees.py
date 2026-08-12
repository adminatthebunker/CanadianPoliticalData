"""ON committee transcript ingester — ola.org Drupal JSON → ``speeches``.

Committee layer over the ON chamber pipeline (``on_hansard.py``), following
the federal/AB/BC/SK reuse-not-fork pattern. Probed 2026-08-12: ola.org's
Drupal ``?_format=json`` serializer works on committee transcript nodes
exactly as it does for chamber Hansard — full transcript HTML in
``body[0].value`` plus ``field_date`` / ``field_parliament`` /
``field_associated_committee`` metadata. Parsing reuses
``on_hansard_parse.extract_speeches`` verbatim (committee attribution
shapes — ``The Chair (Hon. Ernie Hardeman):``, ``Mr. Dave Smith:`` — are
the chamber shapes).

## Discovery

Per-committee listing pages, one GET each:

    /en/legislative-business/committees/{slug}/parliament-{N}/transcripts

listing hrefs shaped ``…/transcripts/committee-transcript-2026-may-25``
(lowercase month name, abbreviated or full). Eight standing committees in
P44 (slugs enumerated live 2026-08-12). Pre-P40 transcripts are PDF-only
uploads — out of scope here; the HTML/JSON era (P40+) is the pipeline's
floor.

## Session resolution

Committee listings are per parliament with no session component. Session
boundaries are derived empirically from the chamber corpus (first chamber
sitting date per session), same approach as ``sk_committees``.

## Speaker resolution — witness-safe

ON attribution is name-based (no member anchors). The chamber cascade's
surname fallback is DISABLED for plain-person labels here: committee
witnesses appear under the same ``Mr./Ms. First Last`` shapes as MPPs, so
a full-name miss means witness, and a surname fallback would re-introduce
the witness/MPP collision the full-name gate prevents (the AB "Mr. Lord"
lesson). Cascade:

  1. role + parens name (``The Chair (Hon. X)``) → full-name match → 0.95;
     unmatched parens → role bucket 0.5 (chairs are always MPPs).
  2. plain person → exact full-name single-hit → 1.0; miss → witness NULL.
  3. bare role → 0.5, NULL (presiding-resolver family territory).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Optional

import httpx
import orjson

from ..db import Database
from . import on_hansard_parse as parse_mod
from .on_hansard import (
    BASE_URL,
    HEADERS,
    REQUEST_DELAY_SECONDS,
    REQUEST_TIMEOUT,
    SOURCE_SYSTEM,
    SpeakerLookup,
    _get_with_retry,
    _norm,
    ensure_session,
    load_on_speaker_lookup,
)

log = logging.getLogger(__name__)

# Slug → display name, enumerated from ola.org/en/legislative-business/
# committees 2026-08-12 (P44). A slug missing here still ingests when
# passed via --committees, but the default walk covers only these — a
# new/renamed committee shows up as a discovery miss, so keep current.
STANDING_COMMITTEES: dict[str, str] = {
    "finance-economic-affairs":
        "Standing Committee on Finance and Economic Affairs",
    "government-agencies": "Standing Committee on Government Agencies",
    "heritage-infrastructure-cultural-policy":
        "Standing Committee on Heritage, Infrastructure and Cultural Policy",
    "interior": "Standing Committee on the Interior",
    "justice-policy": "Standing Committee on Justice Policy",
    "procedure-house-affairs":
        "Standing Committee on Procedure and House Affairs",
    "public-accounts": "Standing Committee on Public Accounts",
    "social-policy": "Standing Committee on Social Policy",
}

_TRANSCRIPT_HREF_RE = re.compile(
    r"href=\"(?P<href>/en/legislative-business/committees/"
    r"(?P<slug>[a-z0-9-]+)/parliament-(?P<parliament>\d+)/transcripts/"
    r"committee-transcript-(?P<year>\d{4})-(?P<month>[a-z]+)-(?P<day>\d{1,2})"
    r")\"",
    re.IGNORECASE,
)

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


@dataclass
class CommitteeTranscriptRef:
    slug: str
    parliament: int
    transcript_date: date
    url: str

    @property
    def committee_name(self) -> str:
        return STANDING_COMMITTEES.get(self.slug, self.slug)


@dataclass
class CommitteeIngestStats:
    committees_walked: int = 0
    transcripts_seen: int = 0
    transcripts_fetched: int = 0
    transcripts_skipped: int = 0
    speeches_inserted: int = 0
    speeches_updated: int = 0
    resolved: int = 0
    witnesses: int = 0
    sessions_touched: set[str] = dc_field(default_factory=set)
    fetch_failures: list[str] = dc_field(default_factory=list)
    parse_failures: list[str] = dc_field(default_factory=list)


async def discover_committee_transcripts(
    client: httpx.AsyncClient, *, parliament: int,
    committees: Optional[set[str]] = None,
) -> tuple[list[CommitteeTranscriptRef], int]:
    """One listing GET per committee; returns (refs, committees_walked)."""
    refs: list[CommitteeTranscriptRef] = []
    seen: set[str] = set()
    slugs = sorted(committees) if committees else sorted(STANDING_COMMITTEES)
    walked = 0
    for slug in slugs:
        listing_url = (
            f"{BASE_URL}/en/legislative-business/committees/"
            f"{slug}/parliament-{parliament}/transcripts"
        )
        try:
            r = await _get_with_retry(client, listing_url)
            r.raise_for_status()
        except Exception as exc:
            # A committee with no transcripts yet 404s — that's data, not
            # an error, but log it so a renamed slug can't hide.
            log.warning("on_committees: listing %s failed: %s",
                        listing_url, exc)
            continue
        walked += 1
        for m in _TRANSCRIPT_HREF_RE.finditer(r.text):
            href = m.group("href")
            if href in seen:
                continue
            seen.add(href)
            month = _MONTHS.get(m.group("month").lower())
            if month is None:
                log.error(
                    "on_committees: unparseable month in %s — extend "
                    "_MONTHS", href,
                )
                continue
            try:
                d = date(int(m.group("year")), month, int(m.group("day")))
            except ValueError:
                continue
            refs.append(CommitteeTranscriptRef(
                slug=m.group("slug").lower(),
                parliament=int(m.group("parliament")),
                transcript_date=d,
                url=BASE_URL + href,
            ))
        await asyncio.sleep(REQUEST_DELAY_SECONDS)
    refs.sort(key=lambda r: r.transcript_date)
    return refs, walked


async def _session_first_sittings(
    db: Database, parliament: int,
) -> list[tuple[int, date]]:
    rows = await db.fetch(
        """
        SELECT ls.session_number, min(s.spoken_at)::date AS first_sit
          FROM speeches s
          JOIN legislative_sessions ls ON ls.id = s.session_id
         WHERE s.level = 'provincial'
           AND s.province_territory = 'ON'
           AND s.source_system = $1
           AND s.speech_type <> 'committee'
           AND ls.parliament_number = $2
         GROUP BY 1
         ORDER BY 1
        """,
        SOURCE_SYSTEM, parliament,
    )
    return [(int(r["session_number"]), r["first_sit"]) for r in rows]


def _session_for_date(
    boundaries: list[tuple[int, date]], transcript_date: date,
) -> int:
    chosen = boundaries[0][0] if boundaries else 1
    for session, first_sit in boundaries:
        if first_sit <= transcript_date:
            chosen = session
    return chosen


def _resolve_committee_speech(
    lookup: SpeakerLookup, ps: parse_mod.ParsedSpeech,
) -> tuple[Optional[dict], float]:
    """Witness-safe variant of on_hansard._resolve_speech — full-name
    matching only; see module docstring."""

    def _full_name_single(name: Optional[str]) -> Optional[dict]:
        if not name:
            return None
        hits = lookup.by_full_name.get(_norm(name), [])
        return hits[0] if len(hits) == 1 else None

    if ps.speaker_role and ps.full_name:
        row = _full_name_single(ps.full_name)
        if row:
            return row, 0.95
        return None, 0.5
    if not ps.speaker_role and (ps.full_name or ps.surname):
        row = _full_name_single(ps.full_name)
        if row:
            return row, 1.0
        return None, 0.0  # witness
    if ps.speaker_role:
        return None, 0.5
    return None, 0.0


async def _upsert_committee_speech(
    db: Database, *, session_id: str, ref: CommitteeTranscriptRef,
    parsed: parse_mod.ParsedSpeech,
    politician: Optional[dict], confidence: float,
    page_html: Optional[str], node_id,
) -> str:
    if not parsed.text.strip():
        return "skipped"
    raw_payload = {
        "on_committee": {
            "committee_slug": ref.slug,
            "committee_name": ref.committee_name,
            "parliament": ref.parliament,
            "transcript_date": ref.transcript_date.isoformat(),
            "node_id": node_id,
            "speaker_role": parsed.speaker_role,
            "parens_name": parsed.parens_name,
            "honorific": parsed.honorific,
            "surname": parsed.surname,
            "full_name": parsed.full_name,
        }
    }
    # Keep the parser's staff/group classification; everything else is
    # committee (the parser's per-section types are chamber concepts).
    speech_type = (
        parsed.speech_type if parsed.speech_type in ("staff", "group")
        else "committee"
    )
    result = await db.fetchrow(
        """
        INSERT INTO speeches (
            session_id, politician_id, level, province_territory,
            speaker_name_raw, speaker_role, party_at_time, constituency_at_time,
            confidence, speech_type, spoken_at, sequence, language,
            text, word_count,
            source_system, source_url, source_anchor,
            raw, raw_html, content_hash
        ) VALUES (
            $1, $2, 'provincial', 'ON',
            $3, $4, $5, $6,
            $7, $8, $9, $10, $11,
            $12, $13,
            $14, $15, NULL,
            $16::jsonb, $17, $18
        )
        ON CONFLICT (source_system, source_url, sequence)
        DO UPDATE SET
            politician_id = EXCLUDED.politician_id,
            speaker_name_raw = EXCLUDED.speaker_name_raw,
            speaker_role = EXCLUDED.speaker_role,
            party_at_time = EXCLUDED.party_at_time,
            constituency_at_time = EXCLUDED.constituency_at_time,
            confidence = EXCLUDED.confidence,
            speech_type = EXCLUDED.speech_type,
            spoken_at = EXCLUDED.spoken_at,
            text = EXCLUDED.text,
            word_count = EXCLUDED.word_count,
            raw = EXCLUDED.raw,
            raw_html = EXCLUDED.raw_html,
            content_hash = EXCLUDED.content_hash,
            updated_at = now()
        RETURNING (xmax = 0) AS inserted
        """,
        session_id,
        politician["id"] if politician else None,
        parsed.speaker_name_raw,
        parsed.speaker_role,
        politician["party"] if politician else None,
        politician["constituency_name"] if politician else None,
        confidence,
        speech_type,
        parsed.spoken_at,
        parsed.sequence,
        parsed.language,
        parsed.text,
        parsed.word_count,
        SOURCE_SYSTEM,
        ref.url,
        orjson.dumps(raw_payload).decode("utf-8"),
        page_html if parsed.sequence == 1 else None,
        parsed.content_hash,
    )
    return "inserted" if result and result["inserted"] else "updated"


async def ingest_on_committees(
    db: Database,
    *,
    parliament: int,
    since: Optional[date] = None,
    until: Optional[date] = None,
    limit_transcripts: Optional[int] = None,
    committees: Optional[list[str]] = None,
    one_off_url: Optional[str] = None,
) -> CommitteeIngestStats:
    """Discover, fetch (Drupal JSON), parse, and upsert ON committee
    transcripts for one parliament. Flag-less runs re-list every
    committee's full transcript set — idempotent, no fixed windows."""
    stats = CommitteeIngestStats()
    lookup = await load_on_speaker_lookup(db)
    committees_filter = (
        {c.strip().lower() for c in committees if c.strip()}
        if committees else None
    )

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, headers=HEADERS, follow_redirects=True,
    ) as client:
        if one_off_url:
            m = _TRANSCRIPT_HREF_RE.search(f'href="{one_off_url.replace(BASE_URL, "")}"')
            if not m:
                stats.fetch_failures.append(
                    f"unrecognised ON committee transcript URL: {one_off_url}")
                return stats
            month = _MONTHS.get(m.group("month").lower())
            refs = [CommitteeTranscriptRef(
                slug=m.group("slug").lower(),
                parliament=int(m.group("parliament")),
                transcript_date=date(int(m.group("year")), month or 1,
                                     int(m.group("day"))),
                url=one_off_url,
            )]
        else:
            refs, stats.committees_walked = await discover_committee_transcripts(
                client, parliament=parliament, committees=committees_filter,
            )
        if since:
            refs = [r for r in refs if r.transcript_date >= since]
        if until:
            refs = [r for r in refs if r.transcript_date <= until]
        refs.sort(key=lambda r: r.transcript_date, reverse=True)
        if limit_transcripts:
            refs = refs[:limit_transcripts]
        stats.transcripts_seen = len(refs)
        log.info("on_committees: processing %d transcripts (parliament=%d)",
                 len(refs), parliament)

        boundaries = await _session_first_sittings(db, parliament)
        session_id_cache: dict[int, str] = {}

        for ref in refs:
            json_url = ref.url + "?_format=json"
            try:
                r = await _get_with_retry(client, json_url)
                r.raise_for_status()
                node = r.json()
            except Exception as exc:
                log.warning("on_committees: %s fetch failed: %s", ref.url, exc)
                stats.fetch_failures.append(ref.url)
                stats.transcripts_skipped += 1
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
                continue
            body_obj = (node.get("body") or [{}])[0]
            body_html = body_obj.get("value") or ""
            if not body_html:
                stats.parse_failures.append(f"empty body.value: {ref.url}")
                stats.transcripts_skipped += 1
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
                continue
            stats.transcripts_fetched += 1

            try:
                result = parse_mod.extract_speeches(
                    body_html,
                    sitting_url=ref.url,
                    sitting_date=ref.transcript_date,
                )
            except Exception as exc:
                stats.parse_failures.append(f"{ref.url}: {exc}")
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
                continue
            if len(result.speeches) < 3:
                # Closed-session meetings legitimately publish only an
                # opening fragment — skip quietly, don't count as error.
                log.info("on_committees: %s: only %d speeches (closed "
                         "session?) — skipped", ref.url, len(result.speeches))
                stats.transcripts_skipped += 1
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
                continue

            session = _session_for_date(boundaries, ref.transcript_date)
            sid = session_id_cache.get(session)
            if sid is None:
                sid = await ensure_session(
                    db, parliament=parliament, session=session)
                session_id_cache[session] = sid
            stats.sessions_touched.add(f"P{parliament}-S{session}")

            node_id = (node.get("nid") or [{}])[0].get("value")
            for ps in result.speeches:
                politician, conf = _resolve_committee_speech(lookup, ps)
                if politician:
                    stats.resolved += 1
                elif conf == 0.0 and (ps.full_name or ps.surname):
                    stats.witnesses += 1
                outcome = await _upsert_committee_speech(
                    db,
                    session_id=sid,
                    ref=ref,
                    parsed=ps,
                    politician=politician,
                    confidence=conf,
                    page_html=body_html,
                    node_id=node_id,
                )
                if outcome == "inserted":
                    stats.speeches_inserted += 1
                elif outcome == "updated":
                    stats.speeches_updated += 1
            await asyncio.sleep(REQUEST_DELAY_SECONDS)

    log.info(
        "on_committees: walked=%d seen=%d fetched=%d skipped=%d inserted=%d "
        "updated=%d resolved=%d witnesses=%d sessions=%s "
        "fetch_failures=%d parse_failures=%d",
        stats.committees_walked, stats.transcripts_seen,
        stats.transcripts_fetched, stats.transcripts_skipped,
        stats.speeches_inserted, stats.speeches_updated,
        stats.resolved, stats.witnesses, sorted(stats.sessions_touched),
        len(stats.fetch_failures), len(stats.parse_failures),
    )
    return stats
