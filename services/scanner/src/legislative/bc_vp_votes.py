"""BC Votes & Proceedings → recorded divisions with per-member positions.

Source (mapped 2026-07-31, see docs/research/british-columbia.md):
  - `lims.leg.bc.ca/pdms/votes-and-proceedings/{parl}{sess}` → JSON
    listing of every V&P issue for the session (fileName / filePath /
    date). The `votesAttributesByFileId.voteNumbers` field is the V&P
    ISSUE number, not division numbers — there is no per-sitting
    "has divisions" flag, so every document is fetched and parsed.
  - Documents at `lims.leg.bc.ca/pdms/file{filePath}/{fileName}` carry
    recorded divisions as a table: `Yeas --/— N` and `Nays --/— N`
    header cells with <BR>-separated member surnames. Two markup eras
    (36th-era bare <TABLE><TH> + <I>-wrapped names; modern
    <table class="division"> + <td class="head">) share this skeleton,
    so ONE parser handles both. Verdict + motion text live in the
    paragraphs immediately before the table ("Motion agreed to /
    defeated on the following division:").

Floor: P35 (1992) — same digital floor as BC bills; pre-P35 sessions
return empty listings.

This REPLACES nothing: the Hansard-regex extractor (`bc_votes.py`,
source_system='votes-bc') stays for consensus-shape votes; this module
lands the recorded divisions the regex path could never resolve to
positions. Distinct source_system keeps the two auditable.

Name resolution: V&P prints surnames only, with first-initial prefixes
for collisions ("R. Singh" vs "A. Singh", "J. D. Wilson"). Resolution
is a date-windowed roster lookup (politician_terms overlapping the
sitting date) keyed by normalized surname, narrowed by initials on
collision, unresolved left NULL with the raw name kept.

Idempotency: votes upsert on (source_system, source_url) where
source_url = document URL + '#division-{n}'; positions upsert on
(vote_id, politician_name_raw).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Optional

import httpx
import orjson

from ..db import Database

log = logging.getLogger(__name__)

SOURCE_SYSTEM = "votes-bc-vp"
PDMS_VP_URL = "https://lims.leg.bc.ca/pdms/votes-and-proceedings/{token}"
PDMS_FILE_URL = "https://lims.leg.bc.ca/pdms/file{path}/{fname}"
FLOOR_PARLIAMENT = 35

REQUEST_TIMEOUT = 60
REQUEST_DELAY_SECONDS = 1.2
HEADERS = {
    "User-Agent": "SovereignWatch/1.0 (civic-transparency; +admin@thebunkerops.ca)",
    "Accept": "application/json, text/html",
    "Origin": "https://dyn.leg.bc.ca",
}


def _ordinal(n: int) -> str:
    if 4 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _parl_sess_token(parliament: int, session: int) -> str:
    return f"{_ordinal(parliament)}{_ordinal(session)}"


# ── Division parsing ─────────────────────────────────────────────────

_TABLE_RE = re.compile(r"<table[^>]*>(?P<body>.*?)</table>", re.S | re.I)
_YEAS_RE = re.compile(r"Yeas\s*(?:--|—|–|-)\s*(?P<n>\d+)", re.I)
_NAYS_RE = re.compile(r"Nays\s*(?:--|—|–|-)\s*(?P<n>\d+)", re.I)
# Names separate on <br> — but 1996-era cells have no trailing <br>
# before </td>, so cell/row boundaries must split too or the last name
# of one cell fuses with the first of the next ("Stephens de Jong").
_BR_SPLIT_RE = re.compile(r"<br\s*/?>|</t[dhr]>|<t[dh][^>]*>|<tr[^>]*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_VERDICT_RE = re.compile(
    r"(?P<verdict>agreed to|carried|passed|adopted|defeated|negatived|lost)"
    r"[^.<]{0,120}?on\s+the\s+following\s+(?:deferred\s+)?division",
    re.I,
)
_BILL_NO_RE = re.compile(r"Bill\s*\(?\s*No\.?\s*(?P<n>\d+)\s*\)?", re.I)
_PARA_SPLIT_RE = re.compile(r"<p[^>]*>|<P[^>]*>", re.I)

_PASS_VERDICTS = {"agreed to", "carried", "passed", "adopted"}


def _strip(html_fragment: str) -> str:
    t = _TAG_RE.sub(" ", html_fragment)
    t = t.replace("&nbsp;", " ").replace("\xa0", " ")
    t = t.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
    return _WS_RE.sub(" ", t).strip()


def _names_from_cells(fragment: str) -> list[str]:
    """Member names from a Yeas/Nays half of a division table.

    Cells are <BR>-separated; strip tags per line. Header echoes and
    count tokens are filtered out.
    """
    names: list[str] = []
    for chunk in _BR_SPLIT_RE.split(fragment):
        s = _strip(chunk)
        if not s:
            continue
        if _YEAS_RE.search(s) or _NAYS_RE.search(s):
            # Header text sharing the chunk — drop the header part only.
            s = _YEAS_RE.sub("", s)
            s = _NAYS_RE.sub("", s)
            s = s.strip()
            if not s:
                continue
        if re.fullmatch(r"[\d\s—–-]+", s):
            continue
        # Section markers / headers leaking through table structure:
        # "(IN COMMITTEE -- SECTION A)" etc.; stray entity fragments.
        if "(" in s or "--" in s or len(s) > 40:
            continue
        if "&" in s or "nbsp" in s.lower():
            continue
        names.append(s)
    return names


class ParsedDivision:
    __slots__ = ("seq", "yea_count", "nay_count", "yeas", "nays",
                 "result", "motion_text", "bill_number")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def parse_divisions(html: str) -> list[ParsedDivision]:
    """Extract every recorded division from one V&P document."""
    out: list[ParsedDivision] = []
    for m in _TABLE_RE.finditer(html):
        body = m.group("body")
        ym = _YEAS_RE.search(body)
        nm = _NAYS_RE.search(body)
        if not ym:
            continue
        yea_count = int(ym.group("n"))
        nay_count = int(nm.group("n")) if nm else 0
        # Header order varies: defeated amendments list the majority
        # (Nays) section FIRST. Split order-aware — names between the
        # first and second header belong to the first header's side.
        if nm and nm.start() < ym.start():
            nay_half = body[nm.end():ym.start()]
            yea_half = body[ym.end():]
        elif nm:
            yea_half = body[ym.end():nm.start()]
            nay_half = body[nm.end():]
        else:
            yea_half = body[ym.end():]
            nay_half = ""
        yeas = _names_from_cells(yea_half)
        nays = _names_from_cells(nay_half)

        # Verdict + motion context from the text before the table.
        pre = html[max(0, m.start() - 2500): m.start()]
        result = None
        motion_text = None
        vm = None
        for vm in _VERDICT_RE.finditer(_strip(pre)):
            pass  # keep the LAST verdict phrase before the table
        if vm:
            result = "Passed" if vm.group("verdict").lower() in _PASS_VERDICTS else "Failed"
        else:
            # "the Committee divided as follows:" carries no verdict
            # word — the outcome is the tally itself (ties fail).
            result = "Passed" if yea_count > nay_count else "Failed"
        paras = [_strip(p) for p in _PARA_SPLIT_RE.split(pre)]
        paras = [p for p in paras if p]
        if paras:
            motion_text = " ".join(paras[-2:])[-600:]
        bill_number = None
        if motion_text:
            bm = None
            for bm in _BILL_NO_RE.finditer(motion_text):
                pass  # last bill mention is closest to the division
            if bm:
                bill_number = bm.group("n")

        out.append(ParsedDivision(
            seq=len(out) + 1,
            yea_count=yea_count, nay_count=nay_count,
            yeas=yeas, nays=nays,
            result=result, motion_text=motion_text,
            bill_number=bill_number,
        ))
    return out


# ── Name resolution (date-windowed roster) ──────────────────────────

def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("\xa0", " ")   # NBSP survives inside cell names
    s = s.replace("’", "'").replace("`", "'")
    s = s.lower()
    # "B.Jones" / "K.Jones" print with no space after the initial —
    # insert one so the initial-token splitter can see it.
    s = re.sub(r"\.(?=[a-z])", ". ", s)
    # Hyphen ↔ space drift: V&P prints "Halsey Brandt" where the roster
    # stores "Halsey-Brandt". Fold both to spaces.
    s = s.replace("-", " ")
    return _WS_RE.sub(" ", s).strip()


# One to three initials in one token: "r", "r.", "g.f.", "j.d".
# Multi-letter sequences REQUIRE dots — a bare 2-letter token is a
# surname particle ("de Jong", "Ma"), never initials.
_INITIAL_TOKEN_RE = re.compile(r"^(?:[a-z]\.){0,2}[a-z]\.?$")


class Roster:
    """Surname (+initial) indexes over MLAs whose terms cover a date."""

    def __init__(self) -> None:
        self.by_surname: dict[str, list[dict]] = {}

    @classmethod
    async def load(cls, db: Database, on_date: date) -> "Roster":
        rows = await db.fetch(
            """
            SELECT DISTINCT p.id::text AS id, p.name,
                   p.first_name, p.last_name
              FROM politicians p
              JOIN politician_terms pt ON pt.politician_id = p.id
             WHERE p.level = 'provincial'
               AND p.province_territory = 'BC'
               AND pt.started_at <= $1
               AND (pt.ended_at IS NULL OR pt.ended_at >= $1)
            """,
            datetime.combine(on_date, datetime.min.time(), tzinfo=timezone.utc)
            .replace(hour=12),
        )
        r = cls()
        for row in rows:
            d = dict(row)
            keys: set[str] = set()
            last = _norm_name(row["last_name"] or "")
            if last:
                keys.add(last)
            # V&P prints compound surnames the DB may split differently:
            # "Chandra Herbert" is stored first_name="Spencer Chandra" /
            # last_name="Herbert". Index the trailing 2- and 3-token
            # tails of the full display name as extra keys.
            full = _norm_name(row["name"] or "")
            toks = full.split(" ")
            if len(toks) >= 2:
                keys.add(" ".join(toks[-2:]))
            if len(toks) >= 3:
                keys.add(" ".join(toks[-3:]))
            for k in keys:
                r.by_surname.setdefault(k, []).append(d)
        return r

    def resolve(self, name_raw: str) -> Optional[str]:
        """V&P name ('de Jong', 'R. Singh', 'J. D. Wilson') → politician id."""
        s = _norm_name(name_raw)
        if not s:
            return None
        tokens = s.split(" ")
        initials: list[str] = []
        while tokens and _INITIAL_TOKEN_RE.match(tokens[0]) and len(tokens) > 1:
            initials.extend(
                c for c in tokens[0] if c.isalpha()
            )
            tokens = tokens[1:]
        surname = " ".join(tokens)
        candidates = self.by_surname.get(surname, [])
        if not candidates:
            return None
        if len(candidates) == 1 and not initials:
            return candidates[0]["id"]
        if initials:
            narrowed = [
                c for c in candidates
                if _norm_name(c["first_name"] or "").startswith(initials[0])
            ]
            if len(narrowed) == 1:
                return narrowed[0]["id"]
            return None
        # >1 candidate, no initials → ambiguous; safer unresolved.
        if len(candidates) == 1:
            return candidates[0]["id"]
        return None


# ── Persistence ─────────────────────────────────────────────────────

class VpStats:
    def __init__(self) -> None:
        self.sessions = 0
        self.docs_fetched = 0
        self.docs_with_divisions = 0
        self.votes_inserted = 0
        self.votes_updated = 0
        self.positions = 0
        self.positions_resolved = 0
        self.bills_linked = 0
        self.fetch_failures = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


async def _local_sessions(
    db: Database, parliaments: Optional[list[int]],
) -> list[dict]:
    rows = await db.fetch(
        """
        SELECT id::text AS id, parliament_number, session_number, start_date
          FROM legislative_sessions
         WHERE level = 'provincial' AND province_territory = 'BC'
           AND parliament_number >= $1
         ORDER BY parliament_number, session_number
        """,
        FLOOR_PARLIAMENT,
    )
    if parliaments:
        rows = [r for r in rows if r["parliament_number"] in parliaments]
    return [dict(r) for r in rows]


async def _bill_id_for(
    db: Database, session_id: str, bill_number: Optional[str],
) -> Optional[str]:
    if not bill_number:
        return None
    return await db.fetchval(
        """
        SELECT id::text FROM bills
         WHERE session_id = $1::uuid AND bill_number = $2
         LIMIT 1
        """,
        session_id, bill_number,
    )


async def ingest_bc_vp_votes(
    db: Database,
    *,
    parliaments: Optional[list[int]] = None,
    since: Optional[date] = None,
    limit_docs: Optional[int] = None,
) -> VpStats:
    """Walk V&P listings per session, parse divisions, land votes +
    vote_positions. Idempotent; safe to re-run any slice."""
    import asyncio

    stats = VpStats()
    sessions = await _local_sessions(db, parliaments)
    roster_cache: dict[str, Roster] = {}

    async with httpx.AsyncClient(
        headers=HEADERS, follow_redirects=True, timeout=REQUEST_TIMEOUT,
    ) as client:
        for s in sessions:
            token = _parl_sess_token(
                s["parliament_number"], s["session_number"],
            )
            try:
                r = await client.get(PDMS_VP_URL.format(token=token))
                r.raise_for_status()
                nodes = (
                    (r.json().get("allParliamentaryFileAttributes") or {})
                    .get("nodes") or []
                )
            except Exception as exc:
                log.warning("vp listing %s failed: %s", token, exc)
                stats.fetch_failures += 1
                continue
            if not nodes:
                continue
            stats.sessions += 1

            for node in nodes:
                if limit_docs and stats.docs_fetched >= limit_docs:
                    break
                fname = node.get("fileName") or ""
                fpath = node.get("filePath") or ""
                raw_date = (node.get("date") or "")[:10]
                try:
                    sitting_date = date.fromisoformat(raw_date)
                except ValueError:
                    sitting_date = None
                if since and sitting_date and sitting_date < since:
                    continue
                url = PDMS_FILE_URL.format(path=fpath, fname=fname)
                try:
                    dr = await client.get(url)
                    dr.raise_for_status()
                    html = dr.text
                except Exception as exc:
                    log.warning("vp doc %s failed: %s", url, exc)
                    stats.fetch_failures += 1
                    continue
                stats.docs_fetched += 1

                divisions = parse_divisions(html)
                if not divisions:
                    await asyncio.sleep(REQUEST_DELAY_SECONDS)
                    continue
                stats.docs_with_divisions += 1

                # Roster cached per SITTING DATE — not per parliament.
                # (A per-parliament cache keyed off the first-encountered
                # sitting was loaded at whatever date the unsorted V&P
                # listing happened to yield first; when that date fell
                # before the LIMS term-start convention date, the cached
                # roster silently excluded most of the parliament for
                # every later sitting. Observed live 2026-07-31: 912
                # unresolved P36 positions for members with valid terms.)
                roster = None
                if sitting_date:
                    rkey = sitting_date.isoformat()
                    roster = roster_cache.get(rkey)
                    if roster is None:
                        roster = await Roster.load(db, sitting_date)
                        roster_cache[rkey] = roster

                occurred_at = (
                    datetime.combine(
                        sitting_date, datetime.min.time(),
                        tzinfo=timezone.utc,
                    ) if sitting_date else None
                )

                for d in divisions:
                    bill_id = await _bill_id_for(db, s["id"], d.bill_number)
                    if bill_id:
                        stats.bills_linked += 1
                    source_url = f"{url}#division-{d.seq}"
                    row = await db.fetchrow(
                        """
                        INSERT INTO votes (
                            session_id, level, province_territory,
                            bill_id, vote_type, occurred_at, result,
                            ayes, nays, abstentions, motion_text,
                            source_system, source_url, raw
                        ) VALUES (
                            $1::uuid, 'provincial', 'BC',
                            $2, 'division', $3, $4,
                            $5, $6, NULL, $7,
                            $8, $9, $10::jsonb
                        )
                        ON CONFLICT (source_system, source_url)
                        DO UPDATE SET
                            bill_id = EXCLUDED.bill_id,
                            occurred_at = EXCLUDED.occurred_at,
                            result = EXCLUDED.result,
                            ayes = EXCLUDED.ayes,
                            nays = EXCLUDED.nays,
                            motion_text = EXCLUDED.motion_text,
                            raw = EXCLUDED.raw,
                            updated_at = now()
                        RETURNING id::text AS id, (xmax = 0) AS inserted
                        """,
                        s["id"], bill_id, occurred_at, d.result,
                        d.yea_count, d.nay_count, d.motion_text,
                        SOURCE_SYSTEM, source_url,
                        orjson.dumps({
                            "document": url,
                            "division_seq": d.seq,
                            "parliament": s["parliament_number"],
                            "session": s["session_number"],
                            "sitting_date": raw_date,
                            "yea_names": d.yeas,
                            "nay_names": d.nays,
                            "bill_number": d.bill_number,
                        }).decode(),
                    )
                    vote_id = row["id"]
                    if row["inserted"]:
                        stats.votes_inserted += 1
                    else:
                        stats.votes_updated += 1

                    # Delete-then-insert: parser fixes must not leave
                    # stale rows from a prior parse (e.g. fused names).
                    await db.execute(
                        "DELETE FROM vote_positions WHERE vote_id = $1::uuid",
                        vote_id,
                    )
                    for names, position in ((d.yeas, "yea"), (d.nays, "nay")):
                        for name_raw in names:
                            pid = roster.resolve(name_raw) if roster else None
                            await db.execute(
                                """
                                INSERT INTO vote_positions (
                                    vote_id, politician_id,
                                    politician_name_raw, position
                                ) VALUES ($1::uuid, $2, $3, $4)
                                ON CONFLICT (vote_id, politician_name_raw)
                                DO UPDATE SET
                                    politician_id = EXCLUDED.politician_id,
                                    position = EXCLUDED.position
                                """,
                                vote_id, pid, name_raw, position,
                            )
                            stats.positions += 1
                            if pid:
                                stats.positions_resolved += 1

                await asyncio.sleep(REQUEST_DELAY_SECONDS)

    log.info("ingest_bc_vp_votes: %s", stats.as_dict())
    return stats