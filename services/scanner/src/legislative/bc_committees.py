"""British Columbia standing-committee transcripts → `speeches` table.

Provincial-committee analog of `ab_committees.ingest_committees`. BC's
chamber Hansard parser (`bc_hansard_parse`) handles committee HTML
without modification — the class taxonomy (SpeakerBegins / Time-Stamp /
Proceedings-Group) is identical between floor sittings and standing
committees. The two divergences are:

  1. Filename shape: floor is `{date}{half}-House-Blues.htm`, committee
     is `{date}{half}-{ShortName}-{Location}-Blues.htm` (location varies
     per meeting — Nelson, Victoria, Cranbrook, etc.).
  2. URL path: floor lives at /hdms/file/Debates/{parl}{sess}/, committee
     at /hdms/file/Committees/{parl}{sess}/{code}/.

## Discovery: operator-curated seed file

BC has no structured listing endpoint for standing-committee transcripts
(probed exhaustively 2026-05-19 — see scripts/seeds/bc-committee-meetings.json
for the rationale). v1 reads a JSON seed: a hand-maintained list of known
transcript URLs per (committee_code, parliament, session). The ingester is
idempotent on canonical_url, so re-running over the same seed is safe.

## Speaker resolution: chamber-wide fallback

BC has zero `politician_committees` membership rows today, so the AB-style
"committee-restricted lookup that correctly rejects witnesses" pattern
can't be replicated. Falls back to `bc_hansard.load_bc_speaker_lookup`
(chamber-wide). Consequences documented in the runbook:
  - Higher false-positive risk: a non-MLA witness named "Smith" will
    surname-match to an MLA "Smith" if one exists.
  - Expected MLA-FK rate ~85-90%, looking higher than AB's 31% but with
    witness bleed.
  - Full fix lands when BC `politician_committees` membership ingest lands.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

import httpx

from ..db import Database
from . import bc_hansard_parse as parse_mod
from .bc_hansard import (
    CANONICAL_URL,
    HEADERS,
    REQUEST_DELAY_SECONDS,
    REQUEST_TIMEOUT,
    SOURCE_SYSTEM,
    BC_PARLIAMENT_SPEAKER,
    SittingRef,
    _get_with_retry,
    _parl_slug,
    _sess_slug,
    _upsert_speech,
    ensure_session,
    load_bc_speaker_lookup,
)

log = logging.getLogger(__name__)


# ── Committee catalogue ──────────────────────────────────────────────
# Mapping of LIMS committee code → official BC name.
#
# Probed 2026-05-19 via site:lims.leg.bc.ca/hdms/file/Committees searches.
# Only committees with at least one HDMS transcript URL discovered through
# probing are listed here — committees that exist on paper (e.g. Aboriginal
# Affairs, Agriculture/Fish/Food) but have no LIMS-indexed transcripts are
# omitted from the catalog. New entries: add (code, full name) here and
# append seed URLs to scripts/seeds/bc-committee-meetings.json.
STANDING_COMMITTEES: dict[str, str] = {
    "cay": "Select Standing Committee on Children and Youth",
    "fgs": "Select Standing Committee on Finance and Government Services",
    "dem": "Special Committee on Democratic and Electoral Reform",
    "pac": "Select Standing Committee on Public Accounts",
    "health": "Select Standing Committee on Health",
    "rpa": "Special Committee on Reforming the Police Act",
    "rpea": "Special Committee to Review Provisions of the Election Act",
}

# Default seed path. Relative to the repo root (scanner's /app working dir
# in compose is /app, so the seed path resolves via the host mount). Click
# command exposes --seed-file for override.
DEFAULT_SEED_PATH = Path("/app/scripts/seeds/bc-committee-meetings.json")

# Committee filename → code reverse map: the seed file groups URLs by
# `committees.{code}`, but a URL like .../43rd1st/fgs/{file} also embeds
# the code in its path. We use that as the authoritative source on read
# so the seed's grouping is a hint, not a contract.
_URL_COMMITTEE_CODE_RE = re.compile(
    r"/hdms/file/Committees/(?P<parl>\d+[a-z]+)(?P<sess>\d+[a-z]+)/"
    r"(?P<code>[A-Za-z0-9_-]+)/(?P<filename>[^/]+)$"
)


# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class CommitteeMeetingRef:
    """Duck-type of `SittingRef` — same field names so _upsert_speech can
    consume both interchangeably. Committee-specific fields are carried
    alongside for the raw payload + URL templates.
    """

    # SittingRef-compatible fields
    sitting_date: date
    half: str
    parliament: int
    session: int
    blues_filename: str            # filename only (no path) for diagnostics
    final_filename: Optional[str]  # if a Final version exists
    issue_number: Optional[int]
    debate_type: str = "Committee"
    published: bool = True

    # Committee-specific extras
    committee_code: str = ""
    committee_name: str = ""
    meeting_location: Optional[str] = None
    blues_url: Optional[str] = None       # full http URL of Blues variant
    final_url: Optional[str] = None       # full http URL of Final variant if present
    sitting_time: Optional[time] = None    # extracted from <meta han.startTime>

    @property
    def best_url(self) -> str:
        """Final if available, else Blues. Mirrors SittingRef.best_url."""
        return self.final_url or self.blues_url or ""

    @property
    def canonical_url(self) -> str:
        """Canonical URL keyed on (parl, sess, code, date, half). Stable
        across Blues→Final upgrades for the same meeting. Distinct from the
        floor Hansard canonical pattern (which uses /Debates/) so committee
        rows can never collide with floor rows."""
        return (
            f"https://hansard-bc.canonical/Committees/"
            f"{_parl_slug(self.parliament)}{_sess_slug(self.session)}/"
            f"{self.committee_code}/"
            f"{self.sitting_date.strftime('%Y%m%d')}{self.half}-Committee.html"
        )


@dataclass
class IngestCommitteeStats:
    meetings_scanned: int = 0
    speeches_seen: int = 0
    speeches_inserted: int = 0
    speeches_updated: int = 0
    speeches_resolved: int = 0
    speeches_presiding: int = 0
    speeches_role_only: int = 0
    speeches_ambiguous: int = 0
    speeches_unresolved: int = 0
    skipped_empty: int = 0
    fetch_failures: int = 0
    parse_errors: int = 0


# ── Seed loader ──────────────────────────────────────────────────────


def load_seed(path: Path) -> tuple[int, int, dict[str, list[str]]]:
    """Read scripts/seeds/bc-committee-meetings.json.

    Returns (parliament, session, committees_map) where committees_map is
    {code: [transcript_url, ...]}. Comment-only "_about" keys are ignored.
    Raises FileNotFoundError if the seed is missing — caller decides how
    loud to be.
    """
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    parliament = int(doc.get("parliament", 0))
    session = int(doc.get("session", 0))
    if not parliament or not session:
        raise ValueError(
            f"seed {path} missing parliament/session at top level"
        )

    committees_raw = doc.get("committees") or {}
    committees: dict[str, list[str]] = {}
    for code, block in committees_raw.items():
        if not isinstance(block, dict):
            continue
        urls = block.get("transcript_urls") or []
        if isinstance(urls, list):
            committees[code] = [str(u) for u in urls if isinstance(u, str)]
    return parliament, session, committees


def _meeting_ref_from_url(
    url: str, parliament: int, session: int,
) -> Optional[CommitteeMeetingRef]:
    """Build a CommitteeMeetingRef from a single transcript URL by parsing
    the filename. Returns None on parse failure (caller logs and skips)."""
    code_m = _URL_COMMITTEE_CODE_RE.search(url)
    if not code_m:
        log.warning("seed url %s: cannot extract committee code", url)
        return None
    code = code_m.group("code").lower()
    filename = code_m.group("filename")

    try:
        url_meta = parse_mod.parse_committee_url_meta("/" + filename)
    except ValueError as exc:
        log.warning("seed url %s: filename parse failed: %s", url, exc)
        return None

    name = STANDING_COMMITTEES.get(code, code.upper())
    # Best-effort blues/final URL: the seed lists ONE URL per meeting in
    # v1 (operator decides whether to track Blues or Final). The URL's
    # filename variant tells us which slot to fill.
    blues_url = url if url_meta.variant == "blues" else None
    final_url = url if url_meta.variant == "final" else None

    return CommitteeMeetingRef(
        sitting_date=url_meta.sitting_date,
        half=url_meta.half,
        parliament=parliament,
        session=session,
        blues_filename=filename if url_meta.variant == "blues" else "",
        final_filename=filename if url_meta.variant == "final" else None,
        issue_number=url_meta.issue,
        debate_type="Committee",
        published=(url_meta.variant == "final"),
        committee_code=code,
        committee_name=name,
        meeting_location=url_meta.location,
        blues_url=blues_url,
        final_url=final_url,
    )


def build_meeting_refs_from_seed(
    seed_path: Path,
    *,
    committees_filter: Optional[list[str]] = None,
    since: Optional[date] = None,
    until: Optional[date] = None,
) -> list[CommitteeMeetingRef]:
    """Load the seed file and materialize CommitteeMeetingRef instances,
    filtered by committee codes and date window. Oldest-first ordering so
    progress logs read naturally."""
    parliament, session, committees_raw = load_seed(seed_path)

    code_filter: Optional[set[str]] = None
    if committees_filter:
        code_filter = {c.lower() for c in committees_filter}

    refs: list[CommitteeMeetingRef] = []
    for code, urls in committees_raw.items():
        if code_filter is not None and code.lower() not in code_filter:
            continue
        for url in urls:
            ref = _meeting_ref_from_url(url, parliament, session)
            if ref is None:
                continue
            if since and ref.sitting_date < since:
                continue
            if until and ref.sitting_date > until:
                continue
            refs.append(ref)

    refs.sort(key=lambda r: (r.sitting_date, r.half, r.committee_code))
    return refs


# ── Orchestrator ────────────────────────────────────────────────────


async def ingest_committees(
    db: Database,
    *,
    parliament: int,
    session: int,
    since: Optional[date] = None,
    until: Optional[date] = None,
    limit_meetings: Optional[int] = None,
    limit_speeches: Optional[int] = None,
    committees: Optional[list[str]] = None,
    seed_path: Optional[Path] = None,
) -> IngestCommitteeStats:
    """Fetch + parse + upsert BC standing-committee transcripts.

    Args:
        parliament / session: target session. Used for ensure_session row;
            actual meeting refs come from the seed file's parliament/session
            block (overwritten with the args if different — operator's
            choice).
        since / until: optional inclusive date window on meeting_date.
        limit_meetings: cap on meetings processed (newest-N when limiting).
        limit_speeches: cap on total inserted+updated speeches.
        committees: comma-separated committee-code filter (default = all
            in the seed file).
        seed_path: override scripts/seeds/bc-committee-meetings.json.
    """
    stats = IngestCommitteeStats()
    seed_path = seed_path or DEFAULT_SEED_PATH

    refs = build_meeting_refs_from_seed(
        seed_path,
        committees_filter=committees,
        since=since,
        until=until,
    )
    if not refs:
        log.warning(
            "bc_committees: seed produced 0 meetings (path=%s parliament=%d "
            "session=%d committees=%s since=%s until=%s)",
            seed_path, parliament, session, committees, since, until,
        )
        return stats

    # If the operator passed different parliament/session than the seed
    # carries, log it loudly — the canonical URL embeds the value, so a
    # mismatch silently writes rows under the wrong session.
    seed_parl = refs[0].parliament
    seed_sess = refs[0].session
    if (seed_parl, seed_sess) != (parliament, session):
        log.warning(
            "bc_committees: seed parliament/session (%d/%d) != args "
            "(%d/%d); ingesting under SEED values",
            seed_parl, seed_sess, parliament, session,
        )
        parliament, session = seed_parl, seed_sess

    session_id = await ensure_session(
        db, parliament=parliament, session=session,
    )
    lookup = await load_bc_speaker_lookup(db)

    if limit_meetings:
        refs = refs[-limit_meetings:]  # newest N

    log.info(
        "bc_committees: processing %d meetings (parliament=%d session=%d, "
        "committees=%s, seed=%s)",
        len(refs), parliament, session,
        committees or "ALL",
        seed_path,
    )

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, headers=HEADERS, follow_redirects=True,
    ) as client:
        for ref in refs:
            if (limit_speeches
                    and (stats.speeches_inserted + stats.speeches_updated)
                    >= limit_speeches):
                break
            stats.meetings_scanned += 1
            url = ref.best_url
            log.info(
                "meeting %s %s %s %s → %s",
                ref.committee_code.upper(), ref.sitting_date,
                ref.half, ref.meeting_location or "?", url,
            )
            try:
                r = await _get_with_retry(client, url)
                r.raise_for_status()
                page_html = r.text
            except Exception as exc:
                log.warning("meeting %s: fetch failed: %s", url, exc)
                stats.fetch_failures += 1
                continue

            try:
                result = parse_mod.extract_speeches(page_html, url)
            except Exception as exc:
                log.warning("meeting %s: parse failed: %s", url, exc)
                stats.parse_errors += 1
                continue

            # Optional: pull title-page metadata to fill in any missing
            # location / committee_name fields. The URL-derived values
            # win when present, but committee_meta backfills missing ones.
            meta = parse_mod.extract_committee_meta(page_html)
            if not ref.meeting_location and meta.location:
                ref.meeting_location = meta.location
            if meta.committee_name and not ref.committee_name.endswith(
                meta.committee_name
            ):
                # Title says "Finance and Government Services" while the
                # catalog has "Select Standing Committee on Finance and
                # Government Services" — keep the catalog form (more
                # canonical for membership lookups).
                pass

            # Fallback: if the parser didn't surface a sitting-Speaker
            # element (committee transcripts often don't carry one), use
            # the parliament-level default. Committee chairs are NOT
            # Speakers, but the lookup gracefully drops the hint if there
            # are no "The Speaker" attributions.
            if not result.sitting_speaker_name:
                result.sitting_speaker_name = BC_PARLIAMENT_SPEAKER.get(
                    ref.parliament
                )

            if len(result.speeches) < 3:
                log.warning(
                    "meeting %s: only %d speeches parsed — skipping",
                    url, len(result.speeches),
                )
                stats.parse_errors += 1
                continue

            log.info(
                "  parsed %d speeches (variant=%s, sections=%d, location=%s)",
                len(result.speeches), result.url_meta.variant,
                len(result.section_hits), ref.meeting_location,
            )

            for ps in result.speeches:
                if (limit_speeches
                        and (stats.speeches_inserted + stats.speeches_updated)
                        >= limit_speeches):
                    break
                stats.speeches_seen += 1

                # Override the parser's speech_type='speech' / 'floor' /
                # etc. — committee transcripts always land as 'committee'
                # regardless of the section heading inside them.
                ps.speech_type = "committee"

                politician, status = lookup.resolve(
                    ps.speaker_name_raw,
                    sitting_speaker_name=result.sitting_speaker_name,
                )
                if status == "resolved":
                    stats.speeches_resolved += 1
                    confidence = 1.0
                elif status == "presiding":
                    stats.speeches_presiding += 1
                    confidence = 0.9
                elif status == "role":
                    stats.speeches_role_only += 1
                    confidence = 0.5
                elif status == "ambiguous":
                    stats.speeches_ambiguous += 1
                    confidence = 0.0
                else:
                    stats.speeches_unresolved += 1
                    confidence = 0.0

                outcome = await _upsert_speech(
                    db,
                    session_id=session_id,
                    ref=ref,  # type: ignore[arg-type] — duck-typed
                    parsed=ps,
                    politician=politician,
                    confidence=confidence,
                    page_html=page_html,
                    real_url=url,
                    sitting_speaker_name=result.sitting_speaker_name,
                    committee_acronym=ref.committee_code.upper(),
                    committee_name=ref.committee_name,
                    meeting_location=ref.meeting_location,
                    committee_blues_url=ref.blues_url,
                    committee_final_url=ref.final_url,
                )
                if outcome == "inserted":
                    stats.speeches_inserted += 1
                elif outcome == "updated":
                    stats.speeches_updated += 1
                elif outcome == "skipped":
                    stats.skipped_empty += 1

            await asyncio.sleep(REQUEST_DELAY_SECONDS)

    log.info(
        "bc_committees done: %d meetings, %d speeches "
        "(inserted=%d updated=%d skipped_empty=%d fetch_failures=%d "
        "parse_errors=%d) "
        "resolved=%d presiding=%d role_only=%d ambiguous=%d unresolved=%d",
        stats.meetings_scanned,
        stats.speeches_seen,
        stats.speeches_inserted,
        stats.speeches_updated,
        stats.skipped_empty,
        stats.fetch_failures,
        stats.parse_errors,
        stats.speeches_resolved,
        stats.speeches_presiding,
        stats.speeches_role_only,
        stats.speeches_ambiguous,
        stats.speeches_unresolved,
    )
    return stats
