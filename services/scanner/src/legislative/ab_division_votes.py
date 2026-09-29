"""AB recorded divisions → votes + per-member vote_positions.

Source: the Alberta Hansard text we ALREADY hold (`speeches` rows with
source_system='assembly.ab.ca'). No upstream fetch. AB Hansard prints
every recorded division as a member list:

    [Several members rose calling for a division. The division bell
    was rung at 2:45 p.m.]
    For the motion: Amery Johnson Armstrong-Homeniuk Jones …
    Against the motion: Al-Guneid Arcand-Paul Batten …
    Totals: For – 46 Against – 37

`ab_votes.py` (source_system='votes-ab') only sees the consensus-shape
`[Motion carried]` brackets and never lands positions; this module is
the division counterpart, the way `bc_vp_votes.py` sits beside
`bc_votes.py`. Distinct source_system keeps the two auditable.

## Why per SITTING, not per speech

The division table is a multi-column block in a two-column PDF, and
pdftotext's reading order (see `ab_hansard.py`) scatters it: a list can
start in one speech row and finish in the next, or land inside an
unrelated turn. Blocks are therefore located in the sitting's speeches
concatenated in `sequence` order.

## Why the Totals line is a hard gate

Reading order can also INTERLEAVE the two lists — a 2002-05-13 block
carries government members inside "For the motion" that belong to
"Against". Every token still resolves to a real MLA, so nothing about
the names betrays it. The printed `Totals:` line is the only check that
does: positions are written ONLY when the parsed For/Against counts
equal the printed totals. Anything else (mismatch, or an era/block with
no totals printed) gets the vote row — the division happened and the
printed tallies are facts — with `raw.parse_status` recording why its
positions were withheld.

## Names

Surnames only, two columns interleaved alphabetically, collisions
qualified after a comma (`Sigurdson, R.J.`, `Nixon, Jason`,
`Brar, Gurinder`), and surnames that contain spaces
(`Calahoo Stonehouse`, `de Jonge`, `van Dijken`). Whitespace is not a
name boundary, so tokenisation is a greedy longest-match against the
AB roster whose terms cover the sitting date.

Idempotency: votes upsert on (source_system, source_url) where
source_url = sitting PDF URL + '#division-{n}' (n = ordinal of the
"For the motion:" marker in the sitting); positions are
delete-then-insert per vote so a parser fix never leaves stale rows.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Optional

import orjson

from ..db import Database
from .bc_vp_votes import _INITIAL_TOKEN_RE, _norm_name

log = logging.getLogger(__name__)

SOURCE_SYSTEM = "votes-ab-division"
HANSARD_SOURCE_SYSTEM = "assembly.ab.ca"

_FOR = "For the motion:"
_AGAINST = "Against the motion:"
_TOTALS_RE = re.compile(r"Totals?:")
_TOTAL_SIDE_RE = re.compile(r"\b(?P<side>For|Against)\s*[–—-]\s*(?P<n>\d+)")
# Page furniture and clock stamps pdftotext leaves inside a list.
_NOISE_RE = re.compile(
    r"\b\d{1,2}:\d{2}\b"
    r"|Alberta Hansard"
    r"|\b(?:January|February|March|April|May|June|July|August|September"
    r"|October|November|December)\s+\d{1,2},\s+\d{4}\b"
    r"|\b\d+\b"
)
_WS_RE = re.compile(r"\s+")
_DIVISION_CALL_RE = re.compile(r"\[\s*Several members rose calling for a division", re.I)
_BRACKET_OUTCOME_RE = re.compile(
    r"\[\s*(?:The\s+)?(?:Motion|Amendment)[^\]]*?\b"
    r"(?P<outcome>carried|defeated|lost|agreed to|negatived)\b",
    re.I,
)
_BILL_REF_RE = re.compile(r"\bBill\s+(?P<n>\d+)\b")

MAX_SURNAME_TOKENS = 3
MAX_UNTOTALLED_AGAINST_CHARS = 3000
CONTEXT_CHARS = 1500


# ── Roster ──────────────────────────────────────────────────────────


# Surnames Hansard printed that the roster no longer carries, keyed to
# the stable `ab_assembly_mid`. One reasoned entry each — never a fuzzy
# rule (see constituency_name_alias for the same discipline).
SURNAME_ALIASES: dict[str, str] = {
    # Michaela Glasgo (Brooks-Medicine Hat, 30L) sat as "Glasgo" until
    # her 2021 marriage; the roster holds her as Michaela Frey.
    "glasgo": "0918",
}


class Roster:
    """Members of one AB Legislature, keyed by normalised surname (and the
    2-/3-token tails of the display name, which catch compound surnames
    the DB splits differently).

    Membership is the Assembly's own per-Legislature member list — the
    MLA terms `ab_mlas`/`ab_former_mlas` write with
    source='assembly.ab.ca:legl-{N}' — joined on the session's
    parliament_number. Exact, where the alternatives are not: AB term
    DATES are year-granular (two Smiths "sitting" through 2015), and the
    speech attribution is itself contaminated for some surnames (Danielle
    Smith is credited with speeches in the 24th/25th/29th Legislatures,
    Nate Horner with Doug Horner's), so "who spoke" cannot break ties.

    Legislature membership is still too coarse for one case: a member
    who arrives mid-Legislature by by-election. Hansard qualifies a
    surname only while two same-surname members SIT together, so a bare
    "Smith" in the 30th means Mark Smith before Danielle Smith's
    2022-11-08 by-election. `ab_member_info.constituency_history`
    carries that election date; a candidate who had not yet been elected
    on the sitting date is dropped.
    """

    def __init__(self) -> None:
        self.by_surname: dict[str, list[dict]] = {}

    @classmethod
    async def load(cls, db: Database, legislature: int) -> "Roster":
        rows = await db.fetch(
            """
            SELECT DISTINCT p.id::text AS id, p.name, p.first_name,
                   p.last_name, p.ab_assembly_mid,
                   p.extras->'ab_member_info'->'constituency_history'
                     AS constituency_history
              FROM politicians p
              JOIN politician_terms pt ON pt.politician_id = p.id
             WHERE p.level = 'provincial'
               AND p.province_territory = 'AB'
               AND pt.office = 'MLA'
               AND pt.source = $1
            """,
            f"assembly.ab.ca:legl-{legislature}",
        )
        r = cls()
        for row in rows:
            d = {k: row[k] for k in ("id", "name", "first_name", "last_name")}
            d["joined"] = _by_election_date(row["constituency_history"], legislature)
            keys: set[str] = set()
            last = _norm_name(row["last_name"] or "")
            if last:
                keys.add(last)
            toks = _norm_name(row["name"] or "").split(" ")
            for n in (2, 3):
                if len(toks) > n:
                    keys.add(" ".join(toks[-n:]))
            keys.update(k for k, mid in SURNAME_ALIASES.items()
                        if mid == row["ab_assembly_mid"])
            for k in keys:
                bucket = r.by_surname.setdefault(k, [])
                if d not in bucket:
                    bucket.append(d)
        return r

    def resolve(
        self, surname: str, qualifier: Optional[str], on_date: date,
    ) -> Optional[str]:
        candidates = self.by_surname.get(surname, [])
        q = _norm_name(qualifier or "").replace(".", " ").split()
        if q:
            initials = all(len(t) == 1 for t in q)
            narrowed = []
            for c in candidates:
                first = _norm_name(c["first_name"] or "").replace(".", " ").split()
                if initials:
                    # "L. Bruce Miller" prints as "Miller, B." — the
                    # initial may be any given name, not only the first.
                    ok = q[0] in {t[0] for t in first if t}
                else:
                    ok = " ".join(first).startswith(" ".join(q))
                if ok:
                    narrowed.append(c)
            candidates = narrowed
        if len(candidates) > 1:
            candidates = [c for c in candidates
                          if c["joined"] is None or c["joined"] <= on_date]
        return candidates[0]["id"] if len(candidates) == 1 else None


def _by_election_date(history, legislature: int) -> Optional[date]:
    """The by-election date that seated this member in `legislature`,
    or None for a general-election member (sits from the start)."""
    if isinstance(history, str):
        history = orjson.loads(history)
    for h in history or []:
        if str(h.get("legislature")) != str(legislature):
            continue
        if "by" not in (h.get("election_type") or "").lower():
            return None
        try:
            return datetime.strptime(h.get("election_date") or "", "%Y-%b-%d").date()
        except ValueError:
            return None
    return None


# ── Name-list tokenisation ──────────────────────────────────────────


@dataclass
class ParsedName:
    raw: str
    politician_id: Optional[str]


@dataclass
class ParsedList:
    names: list[ParsedName] = dc_field(default_factory=list)
    junk: list[str] = dc_field(default_factory=list)


def tokenize_names(
    region: str, roster: Roster, on_date: date, *, stop_at_junk: bool,
) -> ParsedList:
    """Greedy longest-match of roster surnames over a list region.

    A token no surname covers is either an MLA missing from the roster
    (Capitalised — kept as an unresolved name so the Totals gate still
    counts it) or leaked prose (lower-case — junk). With
    `stop_at_junk`, the first non-name ends the list: used when no
    Totals line bounds the region.
    """
    out = ParsedList()
    raw_toks = _WS_RE.sub(" ", _NOISE_RE.sub(" ", region)).strip().split(" ")
    raw_toks = [t for t in raw_toks if t]
    norm = [_norm_name(t.rstrip(",")) for t in raw_toks]
    i = 0
    while i < len(raw_toks):
        match_len = 0
        for n in range(MAX_SURNAME_TOKENS, 0, -1):
            if i + n > len(raw_toks):
                continue
            # A comma closes a surname; it cannot sit mid-key.
            if any(t.endswith(",") for t in raw_toks[i:i + n - 1]):
                continue
            key = " ".join(norm[i:i + n])
            if key in roster.by_surname:
                match_len = n
                break
        if not match_len:
            tok = raw_toks[i]
            if stop_at_junk:
                break
            if tok[:1].isupper() and tok.rstrip(",").replace("-", "").replace("’", "").replace("'", "").isalpha():
                out.names.append(ParsedName(raw=tok.rstrip(","), politician_id=None))
            else:
                out.junk.append(tok)
            i += 1
            continue
        surname_raw = " ".join(raw_toks[i:i + match_len]).rstrip(",")
        surname_key = " ".join(norm[i:i + match_len])
        qualifier = None
        j = i + match_len
        if raw_toks[j - 1].endswith(",") and j < len(raw_toks):
            # "Sigurdson, R.J." / "Wright, J." / "Nixon, Jason".
            q_toks = []
            while j < len(raw_toks) and _INITIAL_TOKEN_RE.match(_norm_name(raw_toks[j])):
                q_toks.append(raw_toks[j])
                j += 1
            if not q_toks and raw_toks[j][:1].isupper():
                q_toks = [raw_toks[j]]
                j += 1
            qualifier = " ".join(q_toks) or None
        raw_name = f"{surname_raw}, {qualifier}" if qualifier else surname_raw
        out.names.append(ParsedName(
            raw=raw_name, politician_id=roster.resolve(surname_key, qualifier, on_date),
        ))
        i = j
    return out


# ── Block location ──────────────────────────────────────────────────


@dataclass
class Division:
    ordinal: int
    speech_id: str
    for_list: ParsedList
    against_list: ParsedList
    total_for: Optional[int]
    total_against: Optional[int]
    parse_status: str          # verified | count_mismatch | no_totals | no_against
    result: Optional[str]
    motion_text: Optional[str]
    bill_number: Optional[str]

    @property
    def positions_trusted(self) -> bool:
        return self.parse_status == "verified"


def _speech_at(offsets: list[tuple[int, str]], pos: int) -> str:
    sid = offsets[0][1]
    for start, s in offsets:
        if start > pos:
            break
        sid = s
    return sid


def find_divisions(
    text: str, offsets: list[tuple[int, str]], roster: Roster, on_date: date,
) -> list[Division]:
    """Every "For the motion:" block in one sitting's concatenated text."""
    out: list[Division] = []
    starts = [m.start() for m in re.finditer(re.escape(_FOR), text)]
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(text)
        a = text.find(_AGAINST, i, end)
        tm = _TOTALS_RE.search(text, a if a >= 0 else i, end)
        total_for = total_against = None
        if tm:
            for sm in _TOTAL_SIDE_RE.finditer(text[tm.end(): tm.end() + 250]):
                if sm.group("side") == "For" and total_for is None:
                    total_for = int(sm.group("n"))
                elif sm.group("side") == "Against" and total_against is None:
                    total_against = int(sm.group("n"))

        if a < 0:
            # No Against header before the next division: the list was
            # scattered beyond recovery. Keep the vote, withhold names.
            for_region = text[i + len(_FOR): tm.start() if tm else min(end, i + MAX_UNTOTALLED_AGAINST_CHARS)]
            for_list = tokenize_names(for_region, roster, on_date, stop_at_junk=True)
            against_list = ParsedList()
            status = "no_against"
            block_end = tm.end() if tm else i + len(_FOR)
        else:
            for_list = tokenize_names(text[i + len(_FOR): a], roster, on_date, stop_at_junk=False)
            if tm and tm.start() > a:
                against_list = tokenize_names(text[a + len(_AGAINST): tm.start()], roster, on_date, stop_at_junk=False)
                block_end = tm.end()
            else:
                region = text[a + len(_AGAINST): min(end, a + MAX_UNTOTALLED_AGAINST_CHARS)]
                against_list = tokenize_names(region, roster, on_date, stop_at_junk=True)
                block_end = a + len(_AGAINST)
            if total_for is None or total_against is None:
                status = "no_totals"
            elif (len(for_list.names) == total_for
                  and len(against_list.names) == total_against
                  and not for_list.junk and not against_list.junk):
                status = "verified"
            else:
                status = "count_mismatch"

        # Outcome: printed totals are definitive; a tie (Speaker's
        # casting vote) or an untotalled block falls back to the
        # bracketed outcome that follows.
        result = None
        if total_for is not None and total_against is not None and total_for != total_against:
            result = "passed" if total_for > total_against else "defeated"
        else:
            om = _BRACKET_OUTCOME_RE.search(text, block_end, min(len(text), block_end + CONTEXT_CHARS))
            if om:
                result = "passed" if om.group("outcome").lower() in ("carried", "agreed to") else "defeated"

        pre = text[max(0, i - CONTEXT_CHARS): i]
        call = None
        for call in _DIVISION_CALL_RE.finditer(pre):
            pass
        motion_ctx = pre[: call.start()] if call else pre
        motion_text = motion_ctx.strip()[-500:] or None
        bill_number = None
        for bm in _BILL_REF_RE.finditer(motion_ctx):
            bill_number = bm.group("n")

        out.append(Division(
            ordinal=k + 1,
            speech_id=_speech_at(offsets, i),
            for_list=for_list, against_list=against_list,
            total_for=total_for, total_against=total_against,
            parse_status=status, result=result,
            motion_text=motion_text, bill_number=bill_number,
        ))
    return out


# ── Persistence ─────────────────────────────────────────────────────


@dataclass
class IngestStats:
    sittings: int = 0
    divisions: int = 0
    by_status: dict[str, int] = dc_field(default_factory=dict)
    votes_inserted: int = 0
    votes_updated: int = 0
    positions: int = 0
    positions_resolved: int = 0
    bills_linked: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


async def _sittings(
    db: Database, *, all_sittings: bool, since: Optional[date],
    limit_sittings: Optional[int],
) -> list[dict]:
    """Sittings carrying a division marker. Default (flag-less, the daily
    schedule): only sittings with no division rows yet, plus the trailing
    30 days so a re-published transcript is re-parsed — self-healing
    without re-walking 25 years every night. `all_sittings` re-walks
    everything (parser changes)."""
    rows = await db.fetch(
        """
        SELECT s.source_url, min(s.spoken_at) AS spoken_at
          FROM speeches s
         WHERE s.source_system = $1
           AND s.speech_type <> 'committee'
           AND s.text ~ 'For the motion:'
           AND ($2::date IS NULL OR s.spoken_at >= $2::date)
         GROUP BY s.source_url
        HAVING $3::bool
            OR min(s.spoken_at) >= now() - interval '30 days'
            OR NOT EXISTS (
                 SELECT 1 FROM votes v
                  WHERE v.source_system = $4
                    AND v.raw->>'sitting_url' = s.source_url
               )
         ORDER BY min(s.spoken_at) DESC
        """,
        HANSARD_SOURCE_SYSTEM, since, all_sittings, SOURCE_SYSTEM,
    )
    if limit_sittings:
        rows = rows[:limit_sittings]
    return [dict(r) for r in rows]


async def _bill_id_for(db: Database, session_id: str, bill_number: Optional[str]) -> Optional[str]:
    if not bill_number:
        return None
    return await db.fetchval(
        "SELECT id::text FROM bills WHERE session_id = $1::uuid AND bill_number = $2 LIMIT 1",
        session_id, bill_number,
    )


async def ingest_ab_division_votes(
    db: Database,
    *,
    all_sittings: bool = False,
    since: Optional[date] = None,
    limit_sittings: Optional[int] = None,
    dry_run: bool = False,
) -> IngestStats:
    """Locate, parse and land every AB recorded division. Idempotent."""
    stats = IngestStats()
    roster_cache: dict[int, Roster] = {}

    for sitting in await _sittings(
        db, all_sittings=all_sittings, since=since, limit_sittings=limit_sittings,
    ):
        speeches = await db.fetch(
            """
            SELECT s.id::text AS id, s.session_id::text AS session_id,
                   ls.parliament_number, s.sequence, s.spoken_at, s.text
              FROM speeches s
              JOIN legislative_sessions ls ON ls.id = s.session_id
             WHERE s.source_system = $1 AND s.source_url = $2
               AND s.speech_type <> 'committee'
             ORDER BY s.sequence
            """,
            HANSARD_SOURCE_SYSTEM, sitting["source_url"],
        )
        if not speeches:
            continue
        stats.sittings += 1
        parts: list[str] = []
        offsets: list[tuple[int, str]] = []
        pos = 0
        for s in speeches:
            t = _WS_RE.sub(" ", s["text"] or "").strip()
            offsets.append((pos, s["id"]))
            parts.append(t)
            pos += len(t) + 1
        text = " ".join(parts)

        sitting_date = speeches[0]["spoken_at"].date()
        session_id = speeches[0]["session_id"]
        legislature = speeches[0]["parliament_number"]
        roster = roster_cache.get(legislature)
        if roster is None:
            roster = await Roster.load(db, legislature)
            roster_cache[legislature] = roster

        for d in find_divisions(text, offsets, roster, sitting_date):
            stats.divisions += 1
            stats.by_status[d.parse_status] = stats.by_status.get(d.parse_status, 0) + 1
            if dry_run:
                log.debug(
                    "%s #%d %s for=%d/%s against=%d/%s junk=%s",
                    sitting_date, d.ordinal, d.parse_status,
                    len(d.for_list.names), d.total_for,
                    len(d.against_list.names), d.total_against,
                    d.for_list.junk + d.against_list.junk,
                )
                if d.positions_trusted:
                    for lst in (d.for_list, d.against_list):
                        stats.positions += len(lst.names)
                        stats.positions_resolved += sum(1 for n in lst.names if n.politician_id)
                continue

            bill_id = await _bill_id_for(db, session_id, d.bill_number)
            if bill_id:
                stats.bills_linked += 1
            raw = {
                "extractor": "ab_division_votes/v1",
                "sitting_url": sitting["source_url"],
                "division_ordinal": d.ordinal,
                "parse_status": d.parse_status,
                "for_names": [n.raw for n in d.for_list.names],
                "against_names": [n.raw for n in d.against_list.names],
                "junk_tokens": d.for_list.junk + d.against_list.junk,
                "bill_number": d.bill_number,
            }
            row = await db.fetchrow(
                """
                INSERT INTO votes (
                    session_id, level, province_territory,
                    bill_id, speech_id, vote_type, occurred_at, result,
                    ayes, nays, abstentions, motion_text,
                    source_system, source_url, raw
                ) VALUES (
                    $1::uuid, 'provincial', 'AB',
                    $2, $3::uuid, 'division', $4, $5,
                    $6, $7, NULL, $8,
                    $9, $10, $11::jsonb
                )
                ON CONFLICT (source_system, source_url)
                DO UPDATE SET
                    bill_id = EXCLUDED.bill_id,
                    speech_id = EXCLUDED.speech_id,
                    occurred_at = EXCLUDED.occurred_at,
                    result = EXCLUDED.result,
                    ayes = EXCLUDED.ayes,
                    nays = EXCLUDED.nays,
                    motion_text = EXCLUDED.motion_text,
                    raw = EXCLUDED.raw,
                    updated_at = now()
                RETURNING id::text AS id, (xmax = 0) AS inserted
                """,
                session_id, bill_id, d.speech_id, speeches[0]["spoken_at"], d.result,
                d.total_for, d.total_against, d.motion_text,
                SOURCE_SYSTEM, f"{sitting['source_url']}#division-{d.ordinal}",
                orjson.dumps(raw).decode(),
            )
            vote_id = row["id"]
            if row["inserted"]:
                stats.votes_inserted += 1
            else:
                stats.votes_updated += 1

            await db.execute("DELETE FROM vote_positions WHERE vote_id = $1::uuid", vote_id)
            if not d.positions_trusted:
                continue
            for lst, position in ((d.for_list, "yea"), (d.against_list, "nay")):
                for n in lst.names:
                    await db.execute(
                        """
                        INSERT INTO vote_positions (
                            vote_id, politician_id, politician_name_raw, position
                        ) VALUES ($1::uuid, $2, $3, $4)
                        ON CONFLICT (vote_id, politician_name_raw)
                        DO UPDATE SET politician_id = EXCLUDED.politician_id,
                                      position = EXCLUDED.position
                        """,
                        vote_id, n.politician_id, n.raw, position,
                    )
                    stats.positions += 1
                    if n.politician_id:
                        stats.positions_resolved += 1

    log.info("ingest_ab_division_votes: %s", stats.as_dict())
    return stats
