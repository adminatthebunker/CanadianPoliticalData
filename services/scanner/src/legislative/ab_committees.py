"""Alberta standing-committee transcripts → `speeches` table.

Provincial-committee analog of `federal_hansard.ingest_committees`. Mirrors
the chamber-Hansard pipeline (`ab_hansard.ingest`) almost entirely:

  Listing :  www.assembly.ab.ca/assembly-business/transcripts/
               transcripts-by-type?comm={ACRONYM}&legl={L}&session={S}
  PDF URL :  docs.assembly.ab.ca/LADDAR_files\\docs\\committees\\{acronym}\\
               legislature_{L}\\session_{S}\\{YYYYMMDD}_{HHMM}_01_{acronym}.pdf

The filename suffix is the committee acronym (lowercase) instead of `han`,
and the docs subtree is `committees/<acronym>/` instead of `hansards/han/`.
Everything else — PDF format, speaker-line shape, two-column reading order
— is identical to chamber Hansard, so we reuse the parser, the upserter,
and the speaker lookup from `ab_hansard`.

`_pick_speech_type` (in ab_hansard) inspects the URL and routes committee
PDFs to `speech_type='committee'`, so the same `_upsert_speech` handles
both pipelines. Witnesses (non-MLA committee speakers — deputy ministers,
industry reps, etc.) land as `politician_id=NULL` rows with their raw
honorific+surname preserved — same shape as unresolved floor speakers.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional

import httpx

from ..db import Database
from .ab_hansard import (
    HEADERS,
    PDF_FETCH_DELAY_SECONDS,
    REQUEST_TIMEOUT,
    SOURCE_SYSTEM,
    SittingRef,
    SpeakerLookup,
    _get_with_retry,
    _norm,
    _strip_honorifics,
    _upsert_speech,
    ensure_session,
    extract_speeches_from_text,
    fetch_pdf_and_extract,
    load_speaker_lookup,
)

log = logging.getLogger(__name__)

# ── Committee catalogue ──────────────────────────────────────────────
# Probe-confirmed against assembly.ab.ca on 2026-05-19. Acronym → full
# name. Full names must match `politician_committees.committee_name` for
# membership-based speaker lookup to work — they're sourced from the
# same /committee-membership page that `committees.py:ingest_ab_committees`
# scrapes, so they're already aligned.
STANDING_COMMITTEES: dict[str, str] = {
    "HS": "Standing Committee on the Alberta Heritage Savings Trust Fund",
    "EF": "Standing Committee on Alberta's Economic Future",
    "CI": "Standing Committee on Citizen Initiative Proposal Review",
    "CEB": "Special Standing Committee on Electoral Boundaries",
    "FC": "Standing Committee on Families and Communities",
    "LO": "Standing Committee on Legislative Offices",
    "MS": "Special Standing Committee on Members' Services",
    "PB": "Standing Committee on Private Bills and Private Members' Public Bills",
    "PE": "Standing Committee on Privileges and Elections, Standing Orders and Printing",
    "PA": "Standing Committee on Public Accounts",
    "RS": "Standing Committee on Resource Stewardship",
}

LISTING_URL = (
    "https://www.assembly.ab.ca/assembly-business/transcripts/"
    "transcripts-by-type?comm={committee}&legl={legislature}&session={session}"
)

# The PDF href pattern mirrors chamber Hansard except for the `committees/
# <acronym>/` subtree and the `_<acronym>.pdf` suffix. Acronym is matched
# case-insensitively because the listing-page URLs use lowercase even when
# the visible acronym is uppercase ("HS" → href `.../committees/hs/...`).
_LISTING_URL_RE = re.compile(
    r'href="(https://docs\.assembly\.ab\.ca/[^"]+'
    r'\\docs\\committees\\(?P<acronym>[a-z0-9]+)\\'
    r'legislature_(?P<leg>\d+)\\session_(?P<sess>\d+)\\'
    r'(?P<date>\d{8})_(?P<hhmm>\d{4})_01_(?P=acronym)\.pdf)"',
    re.IGNORECASE,
)


@dataclass
class CommitteeMeetingRef:
    """Duck-type of `SittingRef` for committee meetings — same field names
    so it can pass through `_upsert_speech` unchanged."""

    url: str
    sitting_date: date
    sitting_time: time
    legislature: int
    session: int
    committee_acronym: str
    committee_name: str

    @property
    def time_of_day(self) -> str:
        h = self.sitting_time.hour
        if h < 12:
            return "morning"
        if h < 17:
            return "afternoon"
        return "evening"


# ── Cover-page roster parser ─────────────────────────────────────────
# Each committee PDF opens with a cover page that lists the meeting's
# attending roster. Format probed 2026-05-19 across HS/PA/LO/MS:
#
#   Yao, Tany, Fort McMurray-Wood Buffalo (UC), Chair
#   Johnson, Jennifer, Lacombe-Ponoka (UC), Deputy Chair
#   Cyr, Scott J., Bonnyville-Cold Lake-St. Paul (UC)*
#   McIver, Hon. Ric, Calgary-Hays (UC), Chair
#   Petrovic, Chelsae, Livingstone-Macleod (UC)**
#   * substitution for Scott Cyr
#
# Substitute MLAs (marked with one-or-more asterisks) aren't in
# `politician_committees` for this committee but ARE real AB MLAs who
# should be attributed when they speak. The committee-restricted speaker
# lookup misses them by design; this roster parser closes that gap on a
# per-meeting basis.
@dataclass
class AttendeeRef:
    last_name: str
    first_name: str       # may carry leading "Hon." or trailing initial like "Scott J."
    constituency: str
    party: str            # e.g. "UC", "NDP"
    is_substitute: bool
    role: Optional[str]   # "Chair" / "Deputy Chair" / None


_ROSTER_LINE_RE = re.compile(
    # Last name: handles plain ("Yao"), compound capitalized ("Calahoo Stonehouse"),
    # lowercase-prefix ("van Dijken", "de Jonge"), hyphenated ("Arcand-Paul"),
    # and apostrophes ("D'Arcy").
    r"^(?P<last>(?:[a-z]+\s+)?[A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'\-]+)?),\s+"
    r"(?P<first>(?:Hon\.\s+)?[A-Z][\w.\s'\-À-ÿ]*?),\s+"
    r"(?P<constituency>[A-Z][A-Za-zÀ-ÿ'.\s\-]+?)"
    r"\s+\((?P<party>[A-Z]+)\)"
    # Everything after the party-paren is captured as a single tail and
    # parsed in Python — the substitute marker (*+) can appear directly
    # after the paren OR after a comma-role-separator, and roles include
    # plain Chair / Deputy Chair / Acting variants.
    r"(?P<tail>[^A-Za-z]*?(?:Chair|Deputy Chair|Acting Chair|Acting Deputy Chair)?)\s*$"
)
_ROLE_RE = re.compile(r"\b(Acting Deputy Chair|Acting Chair|Deputy Chair|Chair)\b")


def parse_meeting_roster(text: str, *, max_lines_to_scan: int = 120) -> list[AttendeeRef]:
    """Walk the first portion of a committee transcript and extract the
    attending-MLA roster (members + substitutes) from the cover page.

    Stops at the first non-matching line *after* at least one roster
    line has been seen — natural terminator handles the various
    "Officials" / "Support Staff" / "Legislative Officers" headers
    that close out the roster section without us having to enumerate
    them.

    Returns an empty list if no roster lines match (e.g. a PDF with
    unusual cover-page formatting); caller should treat as a normal
    soft-miss, not an error.
    """
    out: list[AttendeeRef] = []
    saw_match = False
    for i, raw_line in enumerate(text.splitlines()):
        if i >= max_lines_to_scan:
            break
        line = raw_line.strip()
        if not line:
            continue
        m = _ROSTER_LINE_RE.match(line)
        if m:
            saw_match = True
            tail = m.group("tail") or ""
            role_m = _ROLE_RE.search(tail)
            out.append(
                AttendeeRef(
                    last_name=m.group("last").strip(),
                    first_name=m.group("first").strip(),
                    constituency=m.group("constituency").strip(),
                    party=m.group("party"),
                    is_substitute="*" in tail,
                    role=role_m.group(1) if role_m else None,
                )
            )
            continue
        if saw_match:
            # First non-matching line after the roster started: done.
            # The roster is contiguous; anything past it is staff /
            # officials / footnotes — not voting MLAs.
            break
    return out


async def resolve_attendees_to_politicians(
    db: Database, attendees: list[AttendeeRef],
) -> list[dict]:
    """For each attendee, FK-match against `politicians` and return
    resolved rows (politician dict). Drops attendees that can't be
    uniquely resolved — better than guessing.

    Match strategy:
      1. Exact last_name + first-token-of-first-name match (handles
         "Scott J." → "Scott Cyr" via first-token "Scott").
      2. If multiple, narrow by constituency (case-insensitive substring).
      3. If still multiple, drop (ambiguous).
    """
    if not attendees:
        return []

    resolved: list[dict] = []
    for att in attendees:
        # Strip "Hon. " prefix if present; we never store it in first_name.
        first_clean = re.sub(r"^Hon\.\s+", "", att.first_name).strip()
        first_token = first_clean.split()[0] if first_clean else ""
        if not first_token or not att.last_name:
            continue

        rows = await db.fetch(
            """
            SELECT id::text AS id, name, first_name, last_name, ab_assembly_mid
              FROM politicians
             WHERE level = 'provincial'
               AND province_territory = 'AB'
               AND ab_assembly_mid IS NOT NULL
               AND lower(last_name) = lower($1)
               AND (
                     lower(first_name) = lower($2)
                  OR lower(first_name) LIKE lower($2) || ' %'
                  OR lower(first_name) LIKE lower($2) || '.%'
               )
            """,
            att.last_name, first_token,
        )

        if len(rows) > 1 and att.constituency:
            # Disambiguate by constituency. The MLA's constituency lives
            # on politician_terms; we accept either column's match.
            narrowed = await db.fetch(
                """
                SELECT DISTINCT p.id::text AS id, p.name, p.first_name,
                       p.last_name, p.ab_assembly_mid
                  FROM politicians p
                  LEFT JOIN politician_terms pt ON pt.politician_id = p.id
                 WHERE p.level = 'provincial'
                   AND p.province_territory = 'AB'
                   AND p.ab_assembly_mid IS NOT NULL
                   AND lower(p.last_name) = lower($1)
                   AND (
                         lower(p.first_name) = lower($2)
                      OR lower(p.first_name) LIKE lower($2) || ' %'
                      OR lower(p.first_name) LIKE lower($2) || '.%'
                   )
                   AND replace(lower(regexp_replace(pt.constituency_id, '^.*/', '')), ' ', '-')
                       = replace(lower($3), ' ', '-')
                """,
                att.last_name, first_token, att.constituency,
            )
            if narrowed:
                rows = narrowed

        if len(rows) == 1:
            resolved.append(dict(rows[0]))
        # else: 0 hits (new MLA not in DB) or still-ambiguous → drop.

    return resolved


def augment_lookup_with_attendees(
    lookup: SpeakerLookup, attendees: list[dict],
) -> int:
    """Merge resolved attendees into an existing SpeakerLookup's three
    indexes, skipping IDs already present. Returns the count of net-new
    attendees added.

    Mirrors the index-building logic in `ab_hansard.load_speaker_lookup`
    so attendees match speaker lines via the same surname / first+last /
    full-name keys the chamber lookup uses.
    """
    existing_ids: set[str] = set()
    for idx in (lookup.by_full_name, lookup.by_first_last, lookup.by_surname):
        for lst in idx.values():
            for p in lst:
                existing_ids.add(p["id"])

    added = 0
    for p in attendees:
        if p["id"] in existing_ids:
            continue
        existing_ids.add(p["id"])
        added += 1

        full_name = _norm(_strip_honorifics(p["name"] or ""))
        if full_name:
            lookup.by_full_name.setdefault(full_name, []).append(p)

        first = _norm(p["first_name"] or "")
        last = _norm(p["last_name"] or "")
        if first and last:
            first_tok = first.split()[0]
            last_tok = last.split()[-1]
            lookup.by_first_last.setdefault(
                f"{first_tok} {last_tok}", []
            ).append(p)

        if last:
            last_tok = last.split()[-1]
            lookup.by_surname.setdefault(last_tok, []).append(p)
            if " " in last:
                lookup.by_surname.setdefault(last, []).append(p)

    return added


# ── Listing page ─────────────────────────────────────────────────────


async def fetch_committee_meetings_for_acronym(
    client: httpx.AsyncClient,
    *,
    committee_acronym: str,
    legislature: int,
    session: int,
) -> list[CommitteeMeetingRef]:
    """Scrape the per-committee listing HTML and return one
    `CommitteeMeetingRef` per meeting PDF discovered. Newer meetings
    appear first on the page — preserve order."""
    url = LISTING_URL.format(
        committee=committee_acronym.lower(),
        legislature=legislature,
        session=session,
    )
    r = await _get_with_retry(client, url)
    r.raise_for_status()
    committee_name = STANDING_COMMITTEES.get(
        committee_acronym.upper(), committee_acronym.upper()
    )
    seen: set[str] = set()
    out: list[CommitteeMeetingRef] = []
    for m in _LISTING_URL_RE.finditer(r.text):
        href = m.group(1)
        if href in seen:
            continue
        seen.add(href)
        d = datetime.strptime(m.group("date"), "%Y%m%d").date()
        hhmm = m.group("hhmm")
        try:
            t = time(int(hhmm[:2]), int(hhmm[2:]))
        except ValueError:
            # Upstream filenames occasionally carry a non-clock hhmm token
            # (seen on RS L30-S1: crashed the whole listing). The time is
            # ordering metadata only — midnight-default beats losing the
            # committee-session.
            log.warning(
                "ab_committees: invalid hhmm %r in %s — defaulting 00:00",
                hhmm, href,
            )
            t = time(0, 0)
        out.append(
            CommitteeMeetingRef(
                url=href,
                sitting_date=d,
                sitting_time=t,
                legislature=int(m.group("leg")),
                session=int(m.group("sess")),
                committee_acronym=committee_acronym.upper(),
                committee_name=committee_name,
            )
        )
    log.info(
        "ab_committees listing: %d meetings for comm=%s leg=%d session=%d",
        len(out), committee_acronym.upper(), legislature, session,
    )
    return out


async def fetch_committee_meetings(
    client: httpx.AsyncClient,
    *,
    legislature: int,
    session: int,
    committees: Optional[list[str]] = None,
    since: Optional[date] = None,
    until: Optional[date] = None,
) -> list[CommitteeMeetingRef]:
    """Walk every standing-committee listing for (legislature, session)
    and return the union of meetings discovered. `committees` filters to
    a subset of acronyms; default is all 11 standing committees."""
    acronyms = (
        [c.upper() for c in committees]
        if committees
        else list(STANDING_COMMITTEES.keys())
    )
    out: list[CommitteeMeetingRef] = []
    for acronym in acronyms:
        try:
            meetings = await fetch_committee_meetings_for_acronym(
                client,
                committee_acronym=acronym,
                legislature=legislature,
                session=session,
            )
        except Exception as exc:
            log.warning(
                "ab_committees listing failed for comm=%s leg=%d sess=%d: %s",
                acronym, legislature, session, exc,
            )
            continue
        out.extend(meetings)

    # Filter by date window — done in one place so per-acronym fetches don't
    # need to know the bounds.
    if since:
        out = [m for m in out if m.sitting_date >= since]
    if until:
        out = [m for m in out if m.sitting_date <= until]

    # Oldest-first so sequence numbering in progress logs reads naturally.
    out.sort(key=lambda m: (m.sitting_date, m.sitting_time, m.committee_acronym))
    return out


# ── Committee-restricted speaker lookup ─────────────────────────────


async def load_committee_speaker_lookup(
    db: Database, *, committee_name: str, meeting_date: date,
) -> tuple[SpeakerLookup, bool]:
    """Load the speaker lookup restricted to MLAs who are members of
    `committee_name` (still-open membership, or ended on/after the meeting
    date). Returns `(lookup, is_restricted)` — `is_restricted=False` when
    the committee has no membership rows at all (handles select-special
    committees not yet ingested into politician_committees), so the caller
    can decide whether falling back to chamber-wide is safe.

    Date semantics note: `politician_committees.started_at` is set to
    `now()` at ingest time (it's an observation timestamp, not a term
    boundary), so we *don't* filter on it — that would exclude every
    member for meetings predating the last roster refresh. Only
    `ended_at` carries real semantics; we keep memberships whose end
    is NULL or on/after the meeting date.

    Mirrors `ab_hansard.load_speaker_lookup`'s three-index structure
    (by_full_name / by_first_last / by_surname). The narrower candidate
    pool is a free attribution boost: a 12-member committee disambiguates
    most surname collisions that the 87-MLA chamber pool would leave
    ambiguous, and — critically — keeps witnesses out, preventing the
    common surname-collision false-positive (e.g. AIMCo CIO "Mr. Lord"
    binding to an unrelated MLA named Lord).
    """
    rows = await db.fetch(
        """
        SELECT p.id::text       AS id,
               p.name, p.first_name, p.last_name,
               p.ab_assembly_mid
          FROM politicians p
          JOIN politician_committees pc ON pc.politician_id = p.id
         WHERE p.level = 'provincial'
           AND p.province_territory = 'AB'
           AND p.ab_assembly_mid IS NOT NULL
           AND pc.committee_name = $1
           AND (pc.ended_at IS NULL OR pc.ended_at >= $2)
        """,
        committee_name,
        datetime.combine(meeting_date, time(0, 0)),
    )
    if not rows:
        return (await load_speaker_lookup(db)), False

    lookup = SpeakerLookup()
    for r in rows:
        full_name = _norm(_strip_honorifics(r["name"] or ""))
        if full_name:
            lookup.by_full_name.setdefault(full_name, []).append(dict(r))

        first = _norm(r["first_name"] or "")
        last = _norm(r["last_name"] or "")
        if first and last:
            first_tok = first.split()[0]
            last_tok = last.split()[-1]
            lookup.by_first_last.setdefault(
                f"{first_tok} {last_tok}", []
            ).append(dict(r))

        if last:
            last_tok = last.split()[-1]
            lookup.by_surname.setdefault(last_tok, []).append(dict(r))
            if " " in last:
                lookup.by_surname.setdefault(last, []).append(dict(r))

    for idx in (lookup.by_full_name, lookup.by_first_last, lookup.by_surname):
        for k, lst in idx.items():
            seen = set()
            deduped = []
            for p in lst:
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                deduped.append(p)
            idx[k] = deduped

    return lookup, True


# ── Orchestrator ────────────────────────────────────────────────────


@dataclass
class IngestCommitteeStats:
    meetings_scanned: int = 0
    speeches_seen: int = 0
    speeches_inserted: int = 0
    speeches_updated: int = 0
    speeches_resolved: int = 0
    speeches_role_only: int = 0
    speeches_ambiguous: int = 0
    speeches_unresolved: int = 0
    skipped_empty: int = 0
    fetch_failures: int = 0
    attendees_parsed: int = 0      # roster lines extracted from cover pages
    attendees_resolved: int = 0    # successfully FK-matched against politicians
    attendees_augmented: int = 0   # net-new entries added to committee lookup (substitutes)


async def ingest_committees(
    db: Database,
    *,
    legislature: int,
    session: int,
    since: Optional[date] = None,
    until: Optional[date] = None,
    limit_meetings: Optional[int] = None,
    limit_speeches: Optional[int] = None,
    committees: Optional[list[str]] = None,
) -> IngestCommitteeStats:
    """Fetch + parse + upsert AB standing-committee transcripts for one
    legislature+session.

    Mirrors `ab_hansard.ingest()` but walks the per-committee listing URLs
    instead of the chamber listing. Speaker resolution prefers the
    committee-restricted lookup (members of the meeting's committee on
    the meeting date) and falls back to the chamber-wide lookup when the
    committee membership is empty.

    Args:
        legislature: AB Legislature number (e.g., 31).
        session: Session within legislature (e.g., 2).
        since / until: optional date bounds (inclusive) on meeting date.
        limit_meetings: cap on meeting PDFs to fetch this run.
        limit_speeches: cap on TOTAL speeches inserted/updated.
        committees: optional acronym filter (e.g. ['HS', 'EF']);
            default = all 11 standing committees.
    """
    stats = IngestCommitteeStats()
    session_id = await ensure_session(db, legislature=legislature, session=session)
    chamber_lookup = await load_speaker_lookup(db)

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, headers=HEADERS, follow_redirects=True
    ) as client:
        meetings = await fetch_committee_meetings(
            client,
            legislature=legislature,
            session=session,
            committees=committees,
            since=since,
            until=until,
        )

        if limit_meetings:
            meetings = meetings[-limit_meetings:]  # newest N when limiting

        log.info(
            "ab_committees: processing %d meetings (leg=%d session=%d, committees=%s)",
            len(meetings), legislature, session,
            committees or "ALL",
        )

        # Cache committee-restricted lookups by (committee_name, meeting_date)
        # — most committees meet on dozens of dates per session, and the
        # date-windowed membership query is cheap but not free. Each entry
        # is `(lookup, is_restricted)`; is_restricted=False means the
        # cached lookup is actually the chamber-wide one (committee had
        # no membership rows).
        lookup_cache: dict[tuple[str, date], tuple[SpeakerLookup, bool]] = {}

        for meeting in meetings:
            if (limit_speeches
                    and stats.speeches_inserted + stats.speeches_updated >= limit_speeches):
                break
            stats.meetings_scanned += 1
            log.info(
                "meeting %s %s %s → %s",
                meeting.committee_acronym, meeting.sitting_date,
                meeting.time_of_day, meeting.url,
            )
            try:
                text = await fetch_pdf_and_extract(client, meeting.url)
            except Exception as exc:
                log.warning("meeting %s: fetch/parse failed: %s", meeting.url, exc)
                stats.fetch_failures += 1
                continue

            parsed = extract_speeches_from_text(text)
            log.info("  parsed %d speeches", len(parsed))

            cache_key = (meeting.committee_name, meeting.sitting_date)
            cached = lookup_cache.get(cache_key)
            if cached is None:
                cached = await load_committee_speaker_lookup(
                    db,
                    committee_name=meeting.committee_name,
                    meeting_date=meeting.sitting_date,
                )
                lookup_cache[cache_key] = cached
            lookup, is_restricted = cached

            # Per-meeting roster augmentation: parse the PDF cover page for
            # attending MLAs (regular members + substitutes marked *), FK-
            # match against politicians, merge any non-already-present
            # entries into the lookup. This is what catches substitute
            # MLAs that `politician_committees` doesn't know about — e.g.
            # Cyr / Petrovic / Schulz subbing in at HS 2026-04-13.
            if is_restricted:
                attendees = parse_meeting_roster(text)
                stats.attendees_parsed += len(attendees)
                if attendees:
                    resolved = await resolve_attendees_to_politicians(db, attendees)
                    stats.attendees_resolved += len(resolved)
                    added = augment_lookup_with_attendees(lookup, resolved)
                    stats.attendees_augmented += added
                    if added:
                        log.info(
                            "  roster augment: parsed=%d resolved=%d added=%d (substitutes)",
                            len(attendees), len(resolved), added,
                        )

            for ps in parsed:
                if (limit_speeches
                        and stats.speeches_inserted + stats.speeches_updated >= limit_speeches):
                    break
                stats.speeches_seen += 1

                politician: Optional[dict] = None
                if ps.surname:
                    politician, status = lookup.resolve(ps.surname)
                    if status == "unresolved" and not is_restricted:
                        # Lookup was already chamber-wide; nothing left to
                        # try. (If is_restricted=True, an unresolved miss
                        # almost always means a witness — falling back to
                        # chamber-wide would over-match the witness onto an
                        # unrelated MLA who happens to share the surname.)
                        pass
                    if status == "resolved":
                        stats.speeches_resolved += 1
                    elif status == "ambiguous":
                        stats.speeches_ambiguous += 1
                    else:
                        stats.speeches_unresolved += 1
                else:
                    stats.speeches_role_only += 1

                # CommitteeMeetingRef is a duck-type of SittingRef — same
                # field names, so _upsert_speech reads it transparently.
                outcome = await _upsert_speech(
                    db,
                    session_id=session_id,
                    sitting=meeting,  # type: ignore[arg-type]
                    parsed=ps,
                    politician=politician,
                    raw_text=text,
                    committee_acronym=meeting.committee_acronym,
                    committee_name=meeting.committee_name,
                )
                if outcome == "inserted":
                    stats.speeches_inserted += 1
                elif outcome == "updated":
                    stats.speeches_updated += 1
                elif outcome == "skipped":
                    stats.skipped_empty += 1

            await asyncio.sleep(PDF_FETCH_DELAY_SECONDS)

    log.info(
        "ab_committees done: %d meetings, %d speeches "
        "(inserted=%d updated=%d skipped_empty=%d fetch_failures=%d) "
        "resolved=%d role_only=%d ambiguous=%d unresolved=%d "
        "roster_attendees=%d roster_resolved=%d roster_augmented=%d",
        stats.meetings_scanned,
        stats.speeches_seen,
        stats.speeches_inserted,
        stats.speeches_updated,
        stats.skipped_empty,
        stats.fetch_failures,
        stats.speeches_resolved,
        stats.speeches_role_only,
        stats.speeches_ambiguous,
        stats.speeches_unresolved,
        stats.attendees_parsed,
        stats.attendees_resolved,
        stats.attendees_augmented,
    )
    return stats
