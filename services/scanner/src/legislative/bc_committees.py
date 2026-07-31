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

## Discovery: pcms REST API (seed file retained as fallback)

Since 2026-07-30 discovery is automatic: `discover_meeting_refs` walks
`api.lims.leg.bc.ca/pcms/committees/meetings?filter=previous` (the REST
surface behind the dyn.leg.bc.ca committee SPA, mapped in
docs/research/british-columbia.md § Committee Activity) and yields the
same transcript URLs the seed file used to carry — every meeting back to
1996-07-16. The 2026-05-19 "no structured listing endpoint" conclusion
was true for the surfaces probed then (HDMS listings, LIMS GraphQL,
Drupal JSON); the pcms namespace was found later by mining the SPA
bundle. The legacy operator-curated seed at
scripts/seeds/bc-committee-meetings.json still loads via `--use-seed`
for offline re-ingest or as a manual fallback. The ingester is
idempotent on canonical_url either way.

## Speaker resolution: committee-restricted with a visiting-MLA rescue

Since 2026-07-30 `ingest-bc-committee-membership` syncs current-parliament
membership from the pcms API into `politician_committees` (exact FK via
politicians.lims_member_id), so `load_bc_committee_speaker_lookup`
restricts resolution to actual committee members — the AB-style
witness-rejection pattern. Three tiers:
  1. Committee member (restricted lookup)          → confidence 1.0
  2. Visiting MLA — bill sponsor / substitute —
     chamber-wide EXACT full-name match only       → confidence 0.9
  3. Neither → unattributed (witnesses stay NULL — correct)
Tier 2 exists because visitors aren't members (observed: Sheldon Clare
presenting Bill M237 to IVA); exact-full-name keeps the surname-collision
hole closed. Chamber-wide fallback remains only for committees with zero
membership rows (historical parliaments until the phase-3 backfill lands
dated membership).
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
    _strip_honorifics,
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
#
# The catalogue is split into two buckets: STANDING_COMMITTEES is the set
# the freshness canary watches every cycle (active or potentially-active
# committees of the current Parliament); HISTORICAL_COMMITTEES holds codes
# whose mandate has concluded (special committees that reported and were
# discharged). Display-name lookup falls back from STANDING to HISTORICAL
# so re-ingesting an old transcript still attributes correctly.
STANDING_COMMITTEES: dict[str, str] = {
    "cay": "Select Standing Committee on Children and Youth",
    "fgs": "Select Standing Committee on Finance and Government Services",
    "dem": "Special Committee on Democratic and Electoral Reform",
    "pac": "Select Standing Committee on Public Accounts",
    "health": "Select Standing Committee on Health",
    # Discovered 2026-07-27 via the pcms REST surface on api.lims.leg.bc.ca
    # (see seed _about) — committees active in the 43rd Parliament that the
    # 2026-05-19 site-search probe missed. Names verified from transcript
    # title pages. LAMC (Legislative Assembly Management Committee) is
    # deliberately excluded: administrative housekeeping, and its HDMS path
    # (/Committees/43rd-LAMC) doesn't follow the {parl}{sess}/{code} grammar.
    "pbpmb": "Select Standing Committee on Private Bills and Private Members' Bills",
    "iva": "Special Committee to Review Provisions of the Insurance (Vehicle) Act",
    "pc": "Special Committee on Police Complaints",
    "hrcr": "Special Committee to Review Provisions of the Human Rights Code",
    "lta": "Special Committee to Review the Lobbyists Transparency Act",
    "pida": "Special Committee to Review the Public Interest Disclosure Act",
}

# Concluded-mandate committees. Not watched by the freshness canary — they
# will not meet again under these codes. Kept here so display-name lookup
# stays correct if a historical transcript is ingested (and so a future
# operator probing for a code finds the prior name without git-spelunking).
HISTORICAL_COMMITTEES: dict[str, str] = {
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
    speeches_visiting_mla: int = 0  # rescued by chamber-wide exact-full-name fallback
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
                   AND replace(replace(replace(replace(replace(
                       lower(regexp_replace(pt.constituency_id, '^.*/', '')),
                       '–','-'), '—','-'), '‐','-'), '−','-'), ' ', '-')
                       = replace($3, ' ', '-')
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
        log.warning("transcript url %s: cannot extract committee code", url)
        return None
    code = code_m.group("code").lower()
    filename = code_m.group("filename")

    # The URL path embeds parliament + session ("43rd2nd") — treat it as
    # authoritative, same doctrine as the committee code above. This lets a
    # single seed file carry meetings from multiple sessions; the top-level
    # parliament/session args are only a fallback for malformed paths.
    parl_digits = re.match(r"\d+", code_m.group("parl"))
    sess_digits = re.match(r"\d+", code_m.group("sess"))
    if parl_digits and sess_digits:
        parliament = int(parl_digits.group())
        session = int(sess_digits.group())

    try:
        url_meta = parse_mod.parse_committee_url_meta("/" + filename)
    except ValueError as exc:
        log.warning("transcript url %s: filename parse failed: %s", url, exc)
        return None

    name = STANDING_COMMITTEES.get(
        code, HISTORICAL_COMMITTEES.get(code, code.upper()),
    )
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


# ── pcms API membership ingest ───────────────────────────────────────
# GET /pcms/committees/membership returns every current-parliament
# committee grouped standing/special/statutory, each with chair/deputy
# (or a pre-election convener) + rank-and-file members. The load-bearing
# detail: memberByMemberId.id IS the LIMS member id — the same
# identifier space as politicians.lims_member_id — so resolution is an
# exact FK join with a name-based fallback only for politicians whose
# lims_member_id is missing locally. Historical parliaments are also
# reachable (/pcms/committees/{parl}/membership and
# /{abbrev}/{parl}/members?session= — session param REQUIRED, omitting
# it returns an empty 200); dated historical rows land with the
# phase-3 backfill, which needs a date-aware restricted lookup anyway.

PCMS_MEMBERSHIP_URL = "https://api.lims.leg.bc.ca/pcms/committees/membership"
PCMS_SOURCE = "pcms-api"


@dataclass
class MembershipIngestStats:
    committees_seen: int = 0
    members_seen: int = 0
    resolved_by_lims_id: int = 0
    resolved_by_name: int = 0
    unresolved: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_closed: int = 0


def _iter_membership_slots(entry: dict) -> list[tuple[dict, str]]:
    """Yield (member_node, role) pairs for one committee entry.

    Role slots are mutually exclusive upstream: chair+deputy OR a single
    convener (placeholder before a chair is elected); all optional.
    committeeMembers EXCLUDES whoever fills a role slot.
    """
    out: list[tuple[dict, str]] = []
    if entry.get("committeeChair"):
        out.append((entry["committeeChair"], "Chair"))
    if entry.get("committeeDeputyChair"):
        out.append((entry["committeeDeputyChair"], "Deputy Chair"))
    if entry.get("committeeConvener"):
        out.append((entry["committeeConvener"], "Convener"))
    members = (
        (entry.get("committeeMembers") or {})
        .get("allMemberParliaments", {})
        .get("nodes")
        or []
    )
    for node in members:
        out.append((node, "Member"))
    return out


async def _resolve_by_lims_or_name(
    db: Database, node: dict, stats: MembershipIngestStats,
) -> Optional[str]:
    """member node → politician.id. LIMS-id exact join first; name-based
    fallback second. NEVER the image caption — those disagree with
    memberByMemberId on real rows (observed: 'Shah' vs caption 'Shaw')."""
    member = node.get("memberByMemberId") or {}
    lims_id = member.get("id")
    if isinstance(lims_id, int):
        row = await db.fetchrow(
            """
            SELECT id::text AS id FROM politicians
             WHERE level = 'provincial' AND province_territory = 'BC'
               AND lims_member_id = $1
            """,
            lims_id,
        )
        if row is not None:
            stats.resolved_by_lims_id += 1
            return row["id"]

    name = f"{member.get('firstName') or ''} {member.get('lastName') or ''}".strip()
    if name:
        pid = await resolve_member_to_politician(db, name, "")
        if pid is not None:
            stats.resolved_by_name += 1
            return pid

    log.warning(
        "bc committee membership: unresolved member lims_id=%s name=%r",
        lims_id, name,
    )
    stats.unresolved += 1
    return None


async def ingest_bc_committee_membership(
    db: Database,
    client: Optional[httpx.AsyncClient] = None,
) -> MembershipIngestStats:
    """Sync current-parliament BC committee membership from the pcms API
    into politician_committees.

    Open rows (ended_at IS NULL) are upserted per (politician,
    committee); pcms-sourced open rows whose politician dropped off the
    upstream roster are soft-closed (ended_at=now()). Rows from other
    sources (e.g. 'hansard-bc' substitute detection from transcript
    Membership blocks) are never closed here — substitutes attend
    without being formal members and live their own lifecycle.
    """
    stats = MembershipIngestStats()

    async def _run(c: httpx.AsyncClient) -> None:
        r = await _get_with_retry(c, PCMS_MEMBERSHIP_URL)
        r.raise_for_status()
        doc = r.json()

        cur = doc.get("currentParliament") or {}
        log.info(
            "bc committee membership: parliament %s%s session %s%s",
            cur.get("parliamentNumber"), cur.get("parliamentAnnotation") or "",
            cur.get("sessionNumber"), cur.get("sessionAnnotation") or "",
        )

        for group in ("standing", "special", "statutory"):
            for entry in doc.get(group) or []:
                committee = entry.get("committeeByCommitteeId") or {}
                committee_name = committee.get("name")
                if not committee_name:
                    continue
                stats.committees_seen += 1

                fresh_ids: list[str] = []
                for node, role in _iter_membership_slots(entry):
                    stats.members_seen += 1
                    pid = await _resolve_by_lims_or_name(db, node, stats)
                    if pid is None:
                        continue
                    fresh_ids.append(pid)
                    is_new = await upsert_committee(
                        db,
                        politician_id=pid,
                        committee_name=committee_name,
                        role=role,
                        level="provincial",
                        source=PCMS_SOURCE,
                    )
                    if is_new:
                        stats.rows_inserted += 1
                    else:
                        stats.rows_updated += 1

                # Soft-close pcms-sourced rows for members no longer on
                # the upstream roster (the roster-hygiene discipline —
                # open-ended rows otherwise accumulate forever).
                closed = await db.fetch(
                    """
                    UPDATE politician_committees pc
                       SET ended_at = now()
                      FROM politicians p
                     WHERE p.id = pc.politician_id
                       AND p.level = 'provincial'
                       AND p.province_territory = 'BC'
                       AND pc.committee_name = $1
                       AND pc.level = 'provincial'
                       AND pc.source = $2
                       AND pc.ended_at IS NULL
                       AND NOT (pc.politician_id = ANY($3::uuid[]))
                    RETURNING pc.politician_id
                    """,
                    committee_name, PCMS_SOURCE, fresh_ids,
                )
                stats.rows_closed += len(closed)

    if client is not None:
        await _run(client)
    else:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, headers=HEADERS, follow_redirects=True,
        ) as c:
            await _run(c)

    log.info(
        "bc committee membership: committees=%d members=%d "
        "lims_id=%d name=%d unresolved=%d "
        "inserted=%d updated=%d closed=%d",
        stats.committees_seen, stats.members_seen,
        stats.resolved_by_lims_id, stats.resolved_by_name, stats.unresolved,
        stats.rows_inserted, stats.rows_updated, stats.rows_closed,
    )
    return stats


# ── pcms API discovery ───────────────────────────────────────────────
# The dyn.leg.bc.ca committee SPA reads a REST surface on
# api.lims.leg.bc.ca (mapped 2026-07-30 — see docs/research/
# british-columbia.md § Committee Activity). The meetings feed replaces
# the operator-curated seed file: it lists every committee meeting back
# to 1996-07-16 (50/page, startTime DESC) with the meeting's transcripts
# in a sibling `hansardTranscripts[]` array. Transcript URL =
# HDMS_FILE_BASE + filePath + "/" + fileName — the same URL grammar the
# seed file carried, so discovered URLs flow through the existing
# _meeting_ref_from_url machinery unchanged.
#
# Pagination gotchas (all verified live):
#   - `enCursor` is base64 of ["start_time_desc", ["<ISO>", <meeting id>]]
#     — craftable, so a deep walk can resume from a date watermark.
#   - transcript `publishTime` is NULL for all pre-2010 files; the
#     meeting's `startTime` is the only safe date watermark.
#   - meetings with no transcripts exist (in-camera deliberations) and
#     are skipped silently.
#   - LAMC transcripts live under /Committees/43rd-LAMC — outside the
#     {parl}{sess}/{code} grammar — and fail _URL_COMMITTEE_CODE_RE,
#     which excludes them exactly as the seed convention did.

PCMS_MEETINGS_URL = "https://api.lims.leg.bc.ca/pcms/committees/meetings"
HDMS_FILE_BASE = "https://lims.leg.bc.ca/hdms/file"


@dataclass
class DiscoveryStats:
    pages_fetched: int = 0
    meetings_seen: int = 0
    transcripts_seen: int = 0
    refs_built: int = 0
    skipped_unparseable: int = 0
    oldest_meeting_seen: Optional[date] = None


def _parse_pcms_start_time(value: object) -> Optional[datetime]:
    """pcms timestamps are naive local ISO ('2026-07-29T10:00:00')."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def discover_meeting_refs(
    client: httpx.AsyncClient,
    *,
    since: Optional[date] = None,
    until: Optional[date] = None,
    committees_filter: Optional[list[str]] = None,
    max_pages: Optional[int] = None,
) -> tuple[list[CommitteeMeetingRef], DiscoveryStats]:
    """Walk the pcms meetings feed newest-first and build meeting refs.

    Stops when the page's oldest meeting predates `since` (the feed is
    startTime DESC, so every later page is older still) or when
    `max_pages` is exhausted. Blues + Final transcripts for the same
    (parl, sess, code, date, half) merge into ONE ref with both URL
    slots filled, so a Final upgrade lands as an update on the same
    canonical_url rather than a duplicate meeting.
    """
    stats = DiscoveryStats()
    code_filter: Optional[set[str]] = None
    if committees_filter:
        code_filter = {c.lower() for c in committees_filter}

    # (parliament, session, code, date, half) → merged ref
    merged: dict[tuple[int, int, str, date, str], CommitteeMeetingRef] = {}
    cursor: Optional[str] = None

    while True:
        if max_pages is not None and stats.pages_fetched >= max_pages:
            break
        url = f"{PCMS_MEETINGS_URL}?filter=previous"
        if cursor:
            url += f"&enCursor={cursor}"
        r = await _get_with_retry(client, url)
        r.raise_for_status()
        doc = r.json()
        stats.pages_fetched += 1

        meetings = doc.get("meetings") or []
        transcripts = doc.get("hansardTranscripts") or []
        page_info = doc.get("pageInfo") or {}
        stats.meetings_seen += len(meetings)
        stats.transcripts_seen += len(transcripts)

        # Meeting id → (startTime, official committee-period name). The
        # transcript→meeting join is page-local (verified: every
        # committeeMeetingId on a page resolves within that page).
        meeting_index: dict[int, tuple[Optional[datetime], Optional[str]]] = {}
        oldest_on_page: Optional[datetime] = None
        for m in meetings:
            started = _parse_pcms_start_time(m.get("startTime"))
            period = m.get("committeePeriodByCommitteePeriodId") or {}
            name = period.get("name") or None
            if isinstance(m.get("id"), int):
                meeting_index[m["id"]] = (started, name)
            if started and (oldest_on_page is None or started < oldest_on_page):
                oldest_on_page = started
        if oldest_on_page and (
            stats.oldest_meeting_seen is None
            or oldest_on_page.date() < stats.oldest_meeting_seen
        ):
            stats.oldest_meeting_seen = oldest_on_page.date()

        for t in transcripts:
            file_path = t.get("filePath") or ""
            file_name = t.get("fileName") or ""
            if not file_path or not file_name:
                stats.skipped_unparseable += 1
                continue
            # LAMC (Legislative Assembly Management Committee) is
            # deliberately out of scope — administrative housekeeping,
            # and its /Committees/{parl}-LAMC path is outside the
            # {parl}{sess}/{code} grammar. Skip quietly so every daily
            # run doesn't warn about an intentional exclusion.
            if "-LAMC" in file_path:
                stats.skipped_unparseable += 1
                continue
            attr = t.get("committeeTranscriptAttributeByFileId") or {}
            meeting_id = attr.get("committeeMeetingId")
            started, api_name = meeting_index.get(meeting_id, (None, None))

            url = f"{HDMS_FILE_BASE}{file_path}/{file_name}"
            ref = _meeting_ref_from_url(url, 0, 0)
            if ref is None:
                # LAMC + any future off-grammar paths land here.
                stats.skipped_unparseable += 1
                continue
            if code_filter is not None and ref.committee_code not in code_filter:
                continue
            if since and ref.sitting_date < since:
                continue
            if until and ref.sitting_date > until:
                continue
            # The committee-period name from the API is the official
            # full name ("Select Standing Committee on ...") — richer
            # than the STANDING_COMMITTEES fallback and correct for
            # historical codes the static catalog doesn't know.
            if api_name:
                ref.committee_name = api_name

            key = (
                ref.parliament, ref.session, ref.committee_code,
                ref.sitting_date, ref.half,
            )
            existing = merged.get(key)
            if existing is None:
                merged[key] = ref
                stats.refs_built += 1
            else:
                # Merge Blues/Final variants of the same meeting half.
                if ref.final_url and not existing.final_url:
                    existing.final_url = ref.final_url
                    existing.final_filename = ref.final_filename
                    existing.published = True
                if ref.blues_url and not existing.blues_url:
                    existing.blues_url = ref.blues_url
                    existing.blues_filename = ref.blues_filename
                if ref.issue_number and not existing.issue_number:
                    existing.issue_number = ref.issue_number

        has_next = bool(page_info.get("hasNextPage"))
        cursor = page_info.get("endCursor") or None
        if not has_next or not cursor:
            break
        # The feed is date-desc: once the whole page predates `since`,
        # every remaining page does too.
        if since and oldest_on_page and oldest_on_page.date() < since:
            break
        await asyncio.sleep(REQUEST_DELAY_SECONDS)

    refs = sorted(
        merged.values(),
        key=lambda r: (r.sitting_date, r.half, r.committee_code),
    )
    log.info(
        "pcms discovery: %d pages → %d meetings / %d transcripts → "
        "%d refs (skipped_unparseable=%d, oldest_seen=%s)",
        stats.pages_fetched, stats.meetings_seen, stats.transcripts_seen,
        stats.refs_built, stats.skipped_unparseable,
        stats.oldest_meeting_seen,
    )
    return refs, stats


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
    use_seed: bool = False,
    max_pages: Optional[int] = None,
) -> IngestCommitteeStats:
    """Fetch + parse + upsert BC standing-committee transcripts.

    Args:
        parliament / session: target session. Used for ensure_session row;
            actual meeting refs carry their own parliament/session derived
            from each transcript URL's {parl}{sess} path segment.
        since / until: optional inclusive date window on meeting_date.
            `since` also bounds pcms pagination — the walk stops at the
            first page fully older than it.
        limit_meetings: cap on meetings processed (newest-N when limiting).
        limit_speeches: cap on total inserted+updated speeches.
        committees: comma-separated committee-code filter.
        seed_path: seed JSON path (only read when use_seed=True).
        use_seed: read the legacy operator-curated seed file instead of
            discovering meetings from the pcms API. Kept for offline
            re-ingest and as a manual fallback if the API surface moves.
        max_pages: cap on pcms pages walked during discovery (50
            meetings/page date-desc; None = walk until `since` or floor).
    """
    stats = IngestCommitteeStats()
    seed_path = seed_path or DEFAULT_SEED_PATH

    if use_seed:
        refs = build_meeting_refs_from_seed(
            seed_path,
            committees_filter=committees,
            since=since,
            until=until,
        )
    else:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, headers=HEADERS, follow_redirects=True,
        ) as discovery_client:
            refs, _disc = await discover_meeting_refs(
                discovery_client,
                since=since,
                until=until,
                committees_filter=committees,
                max_pages=max_pages,
            )
    if not refs:
        log.warning(
            "bc_committees: %s produced 0 meetings (parliament=%d "
            "session=%d committees=%s since=%s until=%s max_pages=%s)",
            f"seed {seed_path}" if use_seed else "pcms discovery",
            parliament, session, committees, since, until, max_pages,
        )
        return stats

    # Refs carry their own parliament/session (derived from each URL's
    # {parl}{sess} path segment), so a single seed can span sessions.
    # ensure_session per distinct pair, cached.
    ref_sessions = sorted({(r.parliament, r.session) for r in refs})
    if len(ref_sessions) > 1:
        log.info(
            "bc_committees: seed spans %d sessions: %s",
            len(ref_sessions),
            ", ".join(f"{p}-{s}" for p, s in ref_sessions),
        )
    session_id_cache: dict[tuple[int, int], object] = {}
    for p, s in ref_sessions:
        session_id_cache[(p, s)] = await ensure_session(
            db, parliament=p, session=s,
        )
    # Per-committee cache for the restricted speaker lookup. Built lazily
    # per ref AFTER the meeting's Membership-block ingest so any
    # net-new rows are visible. Keyed by committee_name only — BC
    # memberships don't carry date semantics in v1 (we observe as of
    # "most-recent transcript ingested"). load_bc_committee_speaker_lookup
    # internally falls back to chamber-wide when 0 membership rows exist.
    restricted_cache: dict[str, tuple[SpeakerLookup, bool]] = {}
    # Chamber-wide lookup, loaded lazily the first time a restricted
    # committee needs the visiting-MLA exact-full-name fallback.
    chamber_lookup: Optional[SpeakerLookup] = None

    if limit_meetings:
        refs = refs[-limit_meetings:]  # newest N

    log.info(
        "bc_committees: processing %d meetings (parliament=%d session=%d, "
        "committees=%s, source=%s)",
        len(refs), parliament, session,
        committees or "ALL",
        f"seed:{seed_path}" if use_seed else "pcms-api",
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
            if is_restricted and chamber_lookup is None:
                chamber_lookup = await load_bc_speaker_lookup(db)

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
                if (
                    is_restricted
                    and chamber_lookup is not None
                    and status in ("unresolved", "ambiguous")
                ):
                    # Visiting MLAs — bill sponsors presenting to a
                    # committee, substitutes — aren't members and get
                    # rejected by the restricted lookup (observed live:
                    # Sheldon Clare presenting Bill M237 to IVA,
                    # 2026-07-20). Rescue via chamber-wide EXACT
                    # full-name match only: committee Blues announce
                    # visitors by full name, while the witness/MLA
                    # collisions the restriction exists to block are
                    # surname-level. A witness sharing an MLA's exact
                    # full name stays a residual (accepted) risk.
                    key = _norm(_strip_honorifics(ps.speaker_name_raw))
                    hits = chamber_lookup.by_full_name.get(key) or []
                    if len(hits) == 1:
                        politician = hits[0]
                        status = "visiting"

                if status == "visiting":
                    stats.speeches_visiting_mla += 1
                    confidence = 0.9
                elif status == "resolved":
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
                    session_id=session_id_cache[(ref.parliament, ref.session)],
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
        "visiting_mla=%d "
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
        stats.speeches_visiting_mla,
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
