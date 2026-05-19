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
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

import httpx

from ..committees import upsert_committee
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
    SpeakerLookup,
    _get_with_retry,
    _norm,
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
    # Membership block (when present in the title page) → politician_committees:
    members_parsed: int = 0      # MembershipEntry rows extracted from <h1>Membership</h1>
    members_resolved: int = 0    # successfully FK-matched against politicians
    members_inserted: int = 0    # net-new politician_committees rows
    members_updated: int = 0     # existing open row, role/source updated


# Constituency normalization — collapses en-dash / em-dash / hyphen
# variants so "North Vancouver–Seymour" (en-dash, U+2013) and
# "North Vancouver-Seymour" (ASCII hyphen) match each other. Politicians
# table values vary across the en-dash/hyphen boundary by source — LIMS
# uses en-dashes, opennorth uses hyphens.
_CONST_DASH_RE = re.compile(r"[‐-―−]")  # all dash variants


def _norm_constituency(s: str) -> str:
    if not s:
        return ""
    return _CONST_DASH_RE.sub("-", s).strip().lower()


async def resolve_member_to_politician(
    db: Database, name: str, constituency: str,
) -> Optional[str]:
    """Match a MembershipEntry name + constituency to a politician.id.

    Strategy:
      1. Last-name + first-name-token match on active BC politicians.
      2. If multiple, narrow by constituency (via politician_terms,
         dash-normalized).
      3. If still ambiguous → return None (better than guessing).

    Returns politician.id (uuid str) or None.
    """
    # The MembershipEntry name shape can be:
    #   "Rohini Arora"
    #   "Hon. David Eby"
    #   "Amshen / Joan Phillip"  (Indigenous + English name, slash-sep)
    # For Amshen / Joan Phillip the chamber-Hansard parser already
    # canonicalises one form. Try the slash-second half first since
    # politicians table typically carries the English-form name.
    candidates = [name]
    if "/" in name:
        candidates.extend(p.strip() for p in name.split("/") if p.strip())

    constituency_norm = _norm_constituency(constituency)

    for candidate in candidates:
        # Strip "Hon. " prefix; we don't store it in first_name.
        clean = re.sub(r"^Hon\.?\s+", "", candidate).strip()
        parts = clean.split()
        if len(parts) < 2:
            continue
        first_token = parts[0]
        last_name = parts[-1]

        rows = await db.fetch(
            """
            SELECT p.id::text AS id, p.name, p.first_name, p.last_name
              FROM politicians p
             WHERE p.level = 'provincial'
               AND p.province_territory = 'BC'
               AND p.is_active = true
               AND lower(p.last_name) = lower($1)
               AND (
                     lower(p.first_name) = lower($2)
                  OR lower(p.first_name) LIKE lower($2) || ' %'
                  OR lower(p.first_name) LIKE lower($2) || '.%'
               )
            """,
            last_name, first_token,
        )

        if len(rows) == 1:
            return rows[0]["id"]

        if len(rows) > 1 and constituency_norm:
            # Disambiguate via politician_terms.constituency.
            narrowed = await db.fetch(
                """
                SELECT DISTINCT p.id::text AS id
                  FROM politicians p
                  LEFT JOIN politician_terms pt ON pt.politician_id = p.id
                 WHERE p.level = 'provincial'
                   AND p.province_territory = 'BC'
                   AND p.is_active = true
                   AND lower(p.last_name) = lower($1)
                   AND (
                         lower(p.first_name) = lower($2)
                      OR lower(p.first_name) LIKE lower($2) || ' %'
                      OR lower(p.first_name) LIKE lower($2) || '.%'
                   )
                   AND replace(replace(replace(replace(lower(pt.constituency),
                       '–','-'), '—','-'), '‐','-'), '−','-')
                       = $3
                """,
                last_name, first_token, constituency_norm,
            )
            if len(narrowed) == 1:
                return narrowed[0]["id"]

    return None


async def load_bc_committee_speaker_lookup(
    db: Database, *, committee_name: str,
) -> tuple[SpeakerLookup, bool]:
    """BC analog of ab_committees.load_committee_speaker_lookup.

    Builds a SpeakerLookup restricted to MLAs who are open members of
    `committee_name`. Returns (lookup, is_restricted). is_restricted=False
    when the committee has no membership rows — caller falls back to the
    chamber-wide lookup. Witness-rejection is the v1 prize: a non-MLA
    presenter named "Cory Heavener" no longer surname-matches an MLA
    named "Heavener" (none exists, but for the general case this prevents
    AIMCo-CIO-style collisions like "Mr. Lord" → MLA Lord that AB faced).

    Implementation mirrors `bc_hansard.load_bc_speaker_lookup`'s three-
    index structure (by_full_name / by_initial_last / by_surname) so the
    BC SpeakerLookup.resolve() works unchanged.
    """
    rows = await db.fetch(
        """
        SELECT p.id::text       AS id,
               p.name, p.first_name, p.last_name,
               p.lims_member_id
          FROM politicians p
          JOIN politician_committees pc ON pc.politician_id = p.id
         WHERE p.level = 'provincial'
           AND p.province_territory = 'BC'
           AND pc.committee_name = $1
           AND pc.ended_at IS NULL
        """,
        committee_name,
    )
    if not rows:
        return (await load_bc_speaker_lookup(db)), False

    lookup = SpeakerLookup()
    for r in rows:
        full = _norm(r["name"] or "")
        if full:
            lookup.by_full_name.setdefault(full, []).append(dict(r))
        fl = _norm(f"{r['first_name'] or ''} {r['last_name'] or ''}")
        if fl and fl != full:
            lookup.by_full_name.setdefault(fl, []).append(dict(r))
        last = _norm(r["last_name"] or "")
        first = _norm(r["first_name"] or "")
        if last:
            for tok in {last, last.split()[-1]}:
                lookup.by_surname.setdefault(tok, []).append(dict(r))
            if first:
                initial = first[0]
                lookup.by_initial_last.setdefault(
                    f"{initial} {last.split()[-1]}", []
                ).append(dict(r))

    # Dedupe (same lims_member_id collapses accent variants).
    for idx in (lookup.by_full_name, lookup.by_initial_last, lookup.by_surname):
        for k, lst in idx.items():
            seen_ids: set[str] = set()
            seen_lims: set[int] = set()
            dedup: list[dict] = []
            for p in lst:
                lims_id = p.get("lims_member_id")
                if p["id"] in seen_ids:
                    continue
                if lims_id is not None and lims_id in seen_lims:
                    continue
                seen_ids.add(p["id"])
                if lims_id is not None:
                    seen_lims.add(lims_id)
                dedup.append(p)
            idx[k] = dedup

    return lookup, True


async def ingest_membership_from_transcript(
    db: Database,
    *,
    html_text: str,
    committee_name: str,
    stats: IngestCommitteeStats,
) -> None:
    """Parse the title-page Membership block (when present) and upsert
    politician_committees rows. Updates stats in-place. Idempotent via
    upsert_committee."""
    entries = parse_mod.extract_committee_membership(html_text)
    if not entries:
        return

    stats.members_parsed += len(entries)
    for entry in entries:
        pid = await resolve_member_to_politician(
            db, entry.name, entry.constituency,
        )
        if pid is None:
            continue
        stats.members_resolved += 1
        is_new = await upsert_committee(
            db,
            politician_id=pid,
            committee_name=committee_name,
            role=entry.role,
            level="provincial",
            source=SOURCE_SYSTEM,  # 'hansard-bc'
        )
        if is_new:
            stats.members_inserted += 1
        else:
            stats.members_updated += 1


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
    # Per-committee cache for the restricted speaker lookup. Built lazily
    # per ref AFTER the meeting's Membership-block ingest so any
    # net-new rows are visible. Keyed by committee_name only — BC
    # memberships don't carry date semantics in v1 (we observe as of
    # "most-recent transcript ingested"). load_bc_committee_speaker_lookup
    # internally falls back to chamber-wide when 0 membership rows exist.
    restricted_cache: dict[str, tuple[SpeakerLookup, bool]] = {}

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

            # Parse the title-page Membership block (when present) and
            # upsert politician_committees rows. Idempotent — re-running
            # over already-seen members updates role/source on the open
            # row but doesn't duplicate. DEM-style committees without a
            # Membership block produce zero entries and are a soft-miss.
            await ingest_membership_from_transcript(
                db,
                html_text=page_html,
                committee_name=ref.committee_name,
                stats=stats,
            )

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

            # Build/fetch the committee-restricted lookup AFTER membership
            # ingest (so net-new rows from this transcript's Membership
            # block are visible). Falls back to the chamber-wide lookup
            # when the committee has 0 membership rows (is_restricted=False).
            cached = restricted_cache.get(ref.committee_name)
            if cached is None:
                cached = await load_bc_committee_speaker_lookup(
                    db, committee_name=ref.committee_name,
                )
                restricted_cache[ref.committee_name] = cached
            lookup, is_restricted = cached

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
        "resolved=%d presiding=%d role_only=%d ambiguous=%d unresolved=%d "
        "members_parsed=%d members_resolved=%d members_inserted=%d members_updated=%d",
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
        stats.members_parsed,
        stats.members_resolved,
        stats.members_inserted,
        stats.members_updated,
    )
    return stats


# ── Freshness / dead-canary check ─────────────────────────────────
# BC committees have no auto-discovery API; the seed file at
# scripts/seeds/bc-committee-meetings.json is hand-curated. If the
# operator forgets to add new meetings, daily-cron silently no-ops over
# the same N URLs forever. This check makes the staleness loud:
# per-committee, compute "days since most recent meeting in our DB" and
# emit a warning + email when any active committee crosses a threshold.
#
# Cadence guidance (probed 2026-05-19 from leg.bc.ca content):
#   - FGS does an annual ~3-week Budget Consultation tour (May-June);
#     dormant the rest of the year.
#   - CAY meets ~monthly on inquiry topics.
#   - DEM is an active special committee meeting weekly during inquiry.
# A single threshold can't capture cadence variation cleanly, so this
# check is a CANARY not a SLA — when the threshold trips, the operator
# decides whether it's a real gap or just recess.


@dataclass
class CommitteeFreshness:
    committee_code: str
    committee_name: str
    last_meeting_date: Optional[date]
    meetings_in_db: int
    days_stale: Optional[int]   # None when meetings_in_db == 0


async def check_committee_freshness(
    db: Database, *, today: Optional[date] = None,
) -> list[CommitteeFreshness]:
    """Return one CommitteeFreshness per code in STANDING_COMMITTEES.

    Codes with 0 meetings in our DB get last_meeting_date=None,
    days_stale=None — caller decides whether to flag those as alerts
    (probably yes, with a "never ingested" annotation).
    """
    today = today or date.today()

    # Single grouped query — much cheaper than N round-trips.
    rows = await db.fetch(
        """
        SELECT
          raw->'bc_committee'->>'committee_acronym' AS code_upper,
          MAX(spoken_at)::date AS last_meeting,
          COUNT(DISTINCT source_url) AS meetings
        FROM speeches
        WHERE source_url LIKE 'https://hansard-bc.canonical/Committees/%'
          AND raw->'bc_committee' ? 'committee_acronym'
        GROUP BY 1
        """
    )
    seen: dict[str, dict] = {
        (r["code_upper"] or "").lower(): {
            "last_meeting": r["last_meeting"],
            "meetings": int(r["meetings"]),
        }
        for r in rows
    }

    out: list[CommitteeFreshness] = []
    for code, name in STANDING_COMMITTEES.items():
        hit = seen.get(code)
        if hit is None:
            out.append(
                CommitteeFreshness(
                    committee_code=code,
                    committee_name=name,
                    last_meeting_date=None,
                    meetings_in_db=0,
                    days_stale=None,
                )
            )
            continue
        last = hit["last_meeting"]
        stale = (today - last).days if last else None
        out.append(
            CommitteeFreshness(
                committee_code=code,
                committee_name=name,
                last_meeting_date=last,
                meetings_in_db=hit["meetings"],
                days_stale=stale,
            )
        )

    # Sort by staleness descending (most stale / never-ingested first), so
    # the alert summary leads with the most actionable rows.
    def _sort_key(c: CommitteeFreshness) -> tuple[int, int, str]:
        # never-ingested → bucket 2 (most alarming), then stale-N → bucket
        # 1 with N as tiebreak, then fresh → bucket 0 with -N
        if c.days_stale is None:
            return (2, 0, c.committee_code)
        return (1, -c.days_stale, c.committee_code)
    out.sort(key=_sort_key)
    return out


def stale_committees(
    rows: list[CommitteeFreshness], threshold_days: int,
) -> list[CommitteeFreshness]:
    """Filter to rows that should trigger an alert.

    Distinguishes "stale" (actionable: we've seen this committee
    meeting, but the most recent meeting in our DB is > threshold days
    old — operator should check leg.bc.ca for new ones) from "dormant"
    (informational: never-ingested; could be a historical-only code
    like `health`/`pac` that the operator chose not to seed). Only
    stale rows are returned — dormant ones still appear in the report
    table but don't drive the email alert.
    """
    return [
        r for r in rows
        if r.meetings_in_db > 0
        and r.days_stale is not None
        and r.days_stale > threshold_days
    ]


def format_freshness_report(
    rows: list[CommitteeFreshness], threshold_days: int,
) -> tuple[str, str]:
    """Return (text, html) summaries. Both versions include the full per-
    committee table so the operator can spot-check fresh committees too,
    not only stale ones."""
    today = date.today().isoformat()
    stale = stale_committees(rows, threshold_days)
    dormant = [r for r in rows if r.meetings_in_db == 0]

    lines = [
        f"BC committee freshness report — {today}",
        f"Stale threshold: > {threshold_days} days since most-recent meeting",
        f"Stale (actionable): {len(stale)}    "
        f"Dormant (never ingested): {len(dormant)}    "
        f"Fresh: {len(rows) - len(stale) - len(dormant)}",
        "",
        f"{'Code':6s} {'Last meeting':14s} {'Days stale':>10s} {'Meetings':>9s}  Name",
        "-" * 90,
    ]
    for r in rows:
        last = r.last_meeting_date.isoformat() if r.last_meeting_date else "(never)"
        if r.days_stale is None:
            stale_repr = "dormant"
        else:
            is_stale_row = r.meetings_in_db > 0 and r.days_stale > threshold_days
            stale_repr = f"{r.days_stale:d}{'*' if is_stale_row else ''}"
        lines.append(
            f"{r.committee_code:6s} {last:14s} {stale_repr:>10s} {r.meetings_in_db:>9d}  {r.committee_name}"
        )
    if stale:
        lines.append("")
        lines.append("Action: check leg.bc.ca/parliamentary-business/committees for new meetings,")
        lines.append("then append URLs to scripts/seeds/bc-committee-meetings.json and re-run")
        lines.append("ingest-bc-committees.")
    text = "\n".join(lines)

    # HTML: same table, monospace.
    html_rows: list[str] = []
    for r in rows:
        last = r.last_meeting_date.isoformat() if r.last_meeting_date else "(never)"
        if r.days_stale is None:
            bg = "#f0f0f0"   # dormant — grey, informational
            stale_repr = "dormant"
        elif r.days_stale > threshold_days:
            bg = "#ffe9e9"   # stale — red, actionable
            stale_repr = str(r.days_stale)
        else:
            bg = ""           # fresh — default
            stale_repr = str(r.days_stale)
        html_rows.append(
            f'<tr style="background:{bg}">'
            f'<td><code>{r.committee_code}</code></td>'
            f'<td>{last}</td>'
            f'<td style="text-align:right">{stale_repr}</td>'
            f'<td style="text-align:right">{r.meetings_in_db}</td>'
            f'<td>{r.committee_name}</td>'
            f'</tr>'
        )
    html = (
        f'<h2>BC committee freshness — {today}</h2>'
        f'<p>Stale threshold: &gt; {threshold_days} days since most-recent meeting. '
        f'<b>Stale (actionable): {len(stale)}</b> &middot; '
        f'Dormant (never ingested): {len(dormant)} &middot; '
        f'Fresh: {len(rows) - len(stale) - len(dormant)}</p>'
        f'<table cellpadding="6" cellspacing="0" border="1" '
        f'style="border-collapse:collapse;font-family:monospace">'
        f'<tr><th>Code</th><th>Last meeting</th><th>Days stale</th>'
        f'<th>Meetings</th><th>Name</th></tr>'
        + "".join(html_rows)
        + '</table>'
        + (
            '<p><b>Action:</b> check '
            '<a href="https://www.leg.bc.ca/parliamentary-business/committees">'
            'leg.bc.ca/parliamentary-business/committees</a> for new meetings, '
            'then append URLs to <code>scripts/seeds/bc-committee-meetings.json</code> '
            'and re-run <code>ingest-bc-committees</code>.</p>'
            if stale else ''
        )
    )
    return text, html


# ── SMTP helper (inlined; mirrors alerts_worker pattern) ──────────


def _smtp_is_configured() -> bool:
    return bool(
        os.environ.get("SMTP_USERNAME")
        and os.environ.get("SMTP_PASSWORD")
        and os.environ.get("SMTP_FROM")
    )


def _send_freshness_email(
    to: str, subject: str, text: str, html: str,
) -> None:
    """Blocking SMTP send. Mirrors alerts_worker.send_smtp shape so any
    fix to the SMTP plumbing there can be backported here verbatim."""
    import smtplib
    import ssl
    from email.message import EmailMessage

    host = os.environ.get("SMTP_HOST", "smtp.protonmail.ch")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    from_addr = os.environ["SMTP_FROM"]

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.ehlo()
        s.starttls(context=ctx)
        s.ehlo()
        s.login(username, password)
        s.send_message(msg)


async def check_freshness_and_alert(
    db: Database,
    *,
    threshold_days: int = 21,
    alert_to: Optional[str] = None,
    always_email: bool = False,
) -> tuple[list[CommitteeFreshness], bool]:
    """Run the freshness check and send an alert email when warranted.

    Returns (rows, emailed). Idempotent — safe to run every cron tick.
    """
    rows = await check_committee_freshness(db)
    stale = stale_committees(rows, threshold_days)

    text, html = format_freshness_report(rows, threshold_days)
    # Always print to stdout so the admin Jobs page captures the report.
    print(text)

    should_email = always_email or bool(stale)
    if not should_email:
        return rows, False

    if not _smtp_is_configured():
        log.warning(
            "bc_committees freshness: %d stale committees but SMTP not "
            "configured (SMTP_USERNAME/PASSWORD/FROM unset) — skipping email",
            len(stale),
        )
        return rows, False

    to_addr = (
        alert_to
        or os.environ.get("CPD_OPS_EMAIL")
        or "admin@thebunkerops.ca"
    )
    subject = (
        f"[CPD] BC committees freshness — {len(stale)} stale"
        if stale
        else "[CPD] BC committees freshness — OK"
    )
    try:
        _send_freshness_email(to_addr, subject, text, html)
        log.info(
            "bc_committees freshness: emailed %d-stale report to %s",
            len(stale), to_addr,
        )
        return rows, True
    except Exception as exc:
        log.error("bc_committees freshness: SMTP send failed: %s", exc)
        return rows, False
