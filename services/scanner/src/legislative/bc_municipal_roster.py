"""British Columbia municipal roster, from CivicInfo BC's localelections.ca.

★ WHY BC IS NOT SHAPED LIKE ONTARIO, AND WHY A WARD-ANCHORED INGESTER IS USELESS
HERE. Under the Local Government Act, at-large is BC's STATUTORY DEFAULT — wards
require an LGIC-approved bylaw and essentially nobody has one. We hold ZERO BC
ward polygons, and all BC members attach to a single `boundary_kind='municipality'`
polygon per council. So there is no ward to anchor on, no ward-vs-seat diff to
compute, and the Ontario `compare-on-municipal-wards` model does not transfer.
The transferable precedent is QUÉBEC's municipality-tier attach
(`qc_municipal_roster.py:270`, `:395-413`), not Ontario's.

★ ONE ENDPOINT FOR THE WHOLE PROVINCE. CivicInfo BC is the not-for-profit that
runs BC's local-election database, board-governed by BC local governments, with
data entered by the municipal Chief Election Officers themselves. There is no
provincial administrator of local elections, so this is as close to an authority
as BC has. Its report builder returns every elected official in the province in
one server-rendered HTML table.

⛔ FETCH POSTURE — AN OPERATOR DECISION, NOT A DEFAULT. Recorded here because the
next person will otherwise "helpfully" broaden it:

    localelections.ca/robots.txt   User-agent: *  Crawl-delay: 5
                                   Disallow: /config/ /wp-admin/ /wordpress/ /blog/
                                   (nothing on /report/)
    civicinfo.bc.ca/robots.txt     Content-Signal: ai-train=no, use=reference
                                   User-agent: ClaudeBot -> Disallow: /

Same organisation, two very different postures. The decision was: fetch
`localelections.ca` ONLY, honour its crawl-delay, identify with a descriptive
CPD user-agent carrying a contact URL, and NEVER fetch civicinfo.bc.ca.
⚠ Use the APEX host. `www.localelections.ca` plus a generic tool user-agent
returns 403; `localelections.ca` with the UA below returns 200.

⛔ THE AMO TRAP APPLIES IN FULL. The current-cycle URL serves a CANDIDATE list
until the count completes, with `Elected` and `Number of Votes` present as
columns but EMPTY. The same URL flips to results progressively on election night.
A wholesale ingest mid-count captures a partial council. `assert_results_shape()`
refuses on that basis; the verdict is the authorisation, exactly as in Ontario.
"""
from __future__ import annotations

import asyncio
import html as _html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import httpx

from ..db import Database

SOURCE_PREFIX = "civicinfo-bc"

# ⚠ Apex, not www — see the module docstring.
HOST = "localelections.ca"
USER_AGENT = (
    "CanadianPoliticalData/1.0 "
    "(+https://canadianpoliticaldata.org; admin@thebunkerops.ca)"
)
# robots.txt: `Crawl-delay: 5`. Honoured between every request, not just bursts.
CRAWL_DELAY_SECONDS = 5.0

# BC general local elections: third Saturday of October, every four years.
# 2018-10-20 and 2022-10-15 are both that Saturday, which is what makes 2026
# arithmetic rather than inference. ⚠ Still not read off a statute.
ELECTION_DATES: dict[int, date] = {
    2018: date(2018, 10, 20),
    2022: date(2022, 10, 15),
    2026: date(2026, 10, 17),
}

# `Elected Type` in the report -> our `politicians.elected_office`.
OFFICE_MAP = {
    "MAYOR": "Mayor",
    "COUNCILLOR": "Councillor",
    "COMMISSIONER": "Commissioner",
}

# ⛔ Park boards are NOT optional. Vancouver's council polygon carries 10
# Councillors + 7 Park Board COMMISSIONERS + the Mayor. Fetching only
# mayors+councillors makes those 7 look like held rows the authority does not
# know about — which reads exactly like seven retirements. Two GETs, always.
REPORT_OFFICES = ("mayors=on&councillors=on", "parkboards=on")


@dataclass(frozen=True)
class Council:
    """One BC council we hold, keyed the way the publisher names it."""
    csd_code: str            # census-subdivisions/<code>, our constituency_id
    expected_name: str       # what our boundary row is called
    expected_area_km2: float # ⛔ the ONLY thing that separates the two Langleys


# ⛔ KEYED ON (Local Government, Jurisdiction Type) — NOT ON NAME.
#
# BC has two municipalities called "Langley": the City (10.2 km²) and the
# Township (314.7 km²). They are separate councils with separate members, and
# OUR OWN boundary table calls BOTH of them "Langley" — so the name genuinely
# cannot disambiguate them and neither can our data. The publisher's
# `Jurisdiction Type` column is what resolves it, which is why it is half the key.
#
# ⚠ And because our side cannot tell them apart either, `verify_mapping()` checks
# AREA, not name. A transposition of these two would otherwise pass every check:
# both codes exist, both are live BC municipality polygons, both are named
# "Langley", and 7-vs-9 members is plausible either way round. Area is the only
# signal that separates them, so area is what is asserted.
COUNCILS: dict[tuple[str, str], Council] = {
    ("Abbotsford", "City"):      Council("census-subdivisions/5909052", "Abbotsford", 385.5),
    ("Burnaby", "City"):         Council("census-subdivisions/5915025", "Burnaby", 92.0),
    ("Coquitlam", "City"):       Council("census-subdivisions/5915034", "Coquitlam", 129.8),
    ("Kelowna", "City"):         Council("census-subdivisions/5935010", "Kelowna", 260.9),
    ("Langley", "City"):         Council("census-subdivisions/5915002", "Langley", 10.2),
    ("Langley", "Township"):     Council("census-subdivisions/5915001", "Langley", 314.7),
    ("New Westminster", "City"): Council("census-subdivisions/5915029", "New Westminster", 18.2),
    ("Richmond", "City"):        Council("census-subdivisions/5915015", "Richmond", 151.7),
    ("Saanich", "District"):     Council("census-subdivisions/5917021", "Saanich", 107.0),
    ("Surrey", "City"):          Council("census-subdivisions/5915004", "Surrey", 324.1),
    ("Vancouver", "City"):       Council("census-subdivisions/5915022", "Vancouver", 116.3),
    # ★ TWO ELECTED BODIES, ONE POLYGON. Vancouver's Park Board is elected
    # city-wide and its 7 commissioners are real municipal officials in our data,
    # attached to the same Vancouver polygon as the council. The publisher files
    # them under Jurisdiction Type "Park Board", NOT "City", so they need their
    # own key — without it the compare reports them as 7 held rows the authority
    # does not know about, which reads exactly like 7 retirements.
    # ⚠ The parkboards report is province-wide: Cultus Lake also has one. The
    # Local Government half of the key is what excludes it.
    ("Vancouver", "Park Board"): Council("census-subdivisions/5915022", "Vancouver", 116.3),
    ("Victoria", "City"):        Council("census-subdivisions/5917034", "Victoria", 19.5),
}

# 1% of the recorded area. Tight enough to catch a transposition (the Langleys
# differ by 30x), loose enough to survive a boundary reload's rounding.
AREA_TOLERANCE = 0.01

# ⛔ HOW LONG AN ELECTION RESULT STAYS AUTHORITATIVE FOR A WHOLESALE WRITE.
#
# A result is definitive the week after the count and decays from there, because
# councillors resign, die and are replaced by by-elections, and the result file
# never learns. Measured on the 2022 BC cycle on 2026-09-02 — 1,417 days after
# polling day — 111 of 113 members still matched, and BOTH remainders were cases
# where OUR data was MORE CURRENT than the authority:
#
#   Langley (Township)  authority: Misty Van Popta   held: Blair Whitmarsh
#   Richmond (City)     authority: Chak Au           held: (nobody)
#
# A wholesale apply of that cycle would have re-installed Chak Au and reverted
# Whitmarsh to Van Popta — silently, with a green verdict, because a `gap` and a
# `diverge` look identical whether the cause is a hole in our data or turnover
# the publisher never recorded. This tool cannot tell those apart, so past a
# fresh window it refuses to guess and requires a named council instead.
#
# ★ This is the Ontario lesson in a second province: "frozen is not the same as
# wrong", and a blanket ingest of a stale cycle reverts the parts that are right.
APPLY_FRESH_WINDOW_DAYS = 90


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def norm_name(s: str) -> str:
    """Loose key for comparing a person across two publishers.

    ⚠ Deliberately lossy, and used for REPORTING a diff — never for deciding to
    overwrite a row. It does not collapse Rob/Robert or Chris/Christopher, and
    two such pairs are known to exist in the BC set.
    """
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def loose_same_person(a: str, b: str) -> bool:
    """Would a careful human call these the same person?

    ⚠ REPORTING ONLY. This never authorises a write — it exists so the diff
    shows real gaps instead of name-form noise. Measured against the 2022 BC
    cycle, four of the five apparent mismatches were this:

        Richard T. Lee            vs Richard Lee              (middle initial)
        Robert Rindt              vs Rob Rindt                (short form)
        Christopher Mark Coleman  vs Chris Coleman            (both)
        Angela Kate Haer          vs Angela Haer              (middle name)

    and exactly one was a genuine difference (Misty Van Popta vs Blair
    Whitmarsh — real post-election turnover). Reducing to (first token, last
    token) with a prefix test on the given name separates those cleanly.

    ⛔ Deliberately NOT symmetric-fuzzy: it requires the SURNAME token to match
    exactly. A rule loose enough to pair two different surnames is a rule that
    will eventually merge two councillors.
    """
    ta, tb = norm_name(a).split(), norm_name(b).split()
    if not ta or not tb:
        return False
    if ta[-1] != tb[-1]:
        return False
    fa, fb = ta[0], tb[0]
    if fa == fb:
        return True
    short, long_ = (fa, fb) if len(fa) <= len(fb) else (fb, fa)
    return len(short) >= 3 and long_.startswith(short)


_SMALL_PARTICLES = {"de", "van", "von", "der", "den", "du", "la", "le", "di", "da"}


def fix_caps(s: str) -> str:
    """Re-case a name the publisher submitted in ALL CAPS.

    ⛔ ONLY fires when the string carries no lowercase at all. Per-municipality
    casing is inconsistent — Kelowna submits `TERESA MAY`, New Westminster
    submits all-caps surnames only (`Daniel FONTAINE`), Burnaby and Victoria
    submit mixed case. Re-casing a name that is already correct is how
    `MacDougall` becomes `Macdougall`, so a string containing any lowercase is
    returned untouched.

    ⚠ Even when it does fire this is a GUESS, and it is only ever used for a NEW
    row. On a re-key the existing database name wins, because a name a human has
    already seen is better evidence than a mechanical re-casing.
    """
    s = (s or "").strip()
    if not s or any(c.islower() for c in s):
        return s

    def one(tok: str) -> str:
        if not tok:
            return tok
        low = tok.lower()
        if low in _SMALL_PARTICLES:
            return low
        # Mc/Mac and O' keep an internal capital; hyphens re-case each side.
        if "-" in tok:
            return "-".join(one(p) for p in tok.split("-"))
        if low.startswith("mc") and len(low) > 2:
            return "Mc" + low[2:].capitalize()
        if low.startswith("mac") and len(low) > 3:
            return "Mac" + low[3:].capitalize()
        if low.startswith("o'") and len(low) > 2:
            return "O'" + low[2:].capitalize()
        return low.capitalize()

    return " ".join(one(t) for t in s.split())


# ── Fetch ────────────────────────────────────────────────────────────────────

def report_url(year: Optional[int], offices: str) -> str:
    """The province-wide report. `year=None` is the current cycle."""
    parts = [
        offices,
        # Every Experience bucket, or the report silently omits whole classes of
        # member — an incumbent-only fetch loses every newly elected councillor.
        "incumbent=on", "servedDiff=on", "servedPrior=on",
        "prevExp=on", "new=on", "unknown=on",
        "rtype=results",
    ]
    if year is not None:
        parts.append(f"year={year}")
    return f"https://{HOST}/report/index.php?" + "&".join(parts)


async def fetch_report(client: httpx.AsyncClient, year: Optional[int],
                       offices: str) -> str:
    r = await client.get(report_url(year, offices))
    r.raise_for_status()
    return r.text


_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _cells(row_html: str) -> list[str]:
    return [_html.unescape(_TAG.sub("", c)).strip() for c in _TD.findall(row_html)]


def parse_report(page: str) -> tuple[list[str], list[dict[str, str]]]:
    """Server-rendered HTML table -> header + rows.

    ⛔ ROW WIDTH IS RAGGED. Both 22- and 25-cell rows appear in the same table,
    and the archived cycles are 17 wide because the contact columns
    (Address/City/Postal Code/Phone/Cell/Contact Consent) are dropped from
    prior years, presumably under a retention policy. So the column COUNT is
    not a constant, and positional indexing against a remembered layout is how
    you silently read `Last Name` out of the `Gender` column.

    Rows whose cell count does not equal the header's are REJECTED and counted,
    never truncated or padded.
    """
    header: Optional[list[str]] = None
    rows: list[dict[str, str]] = []
    ragged = 0
    for raw in _TR.findall(page):
        c = _cells(raw)
        if header is None:
            if c and any("Local Government" in x for x in c):
                header = c
            continue
        if len(c) != len(header):
            if c:
                ragged += 1
            continue
        rows.append(dict(zip(header, c)))
    if header is None:
        raise RuntimeError(
            "localelections.ca: no table header containing 'Local Government'. "
            "The report layout changed, or the fetch was challenged — refusing "
            "to parse."
        )
    if ragged:
        rows.append({"__ragged__": str(ragged)})
    return header, rows


@dataclass
class Member:
    council_key: tuple[str, str]
    first_name: str
    last_name: str
    office: str
    votes: Optional[int]
    acclaimed: bool
    organization: str
    raw_name: str

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


def extract_members(rows: list[dict[str, str]]) -> tuple[list[Member], int]:
    """Rows -> the members of the councils we actually hold."""
    out: list[Member] = []
    ragged = 0
    for r in rows:
        if "__ragged__" in r:
            ragged = int(r["__ragged__"])
            continue
        key = (r.get("Local Government", "").strip(),
               r.get("Jurisdiction Type", "").strip())
        if key not in COUNCILS:
            continue
        office = OFFICE_MAP.get(r.get("Elected Type", "").strip().upper())
        if office is None:
            continue
        first_raw = r.get("First Name", "").strip()
        last_raw = r.get("Last Name", "").strip()
        if not first_raw or not last_raw:
            continue
        votes_s = re.sub(r"[^0-9]", "", r.get("Number of Votes", "") or "")
        out.append(Member(
            council_key=key,
            first_name=fix_caps(first_raw),
            last_name=fix_caps(last_raw),
            office=office,
            votes=int(votes_s) if votes_s else None,
            acclaimed=(r.get("Acclamation", "").strip().upper() in ("YES", "Y", "TRUE")),
            organization=r.get("Elector Organization", "").strip(),
            raw_name=f"{first_raw} {last_raw}".strip(),
        ))
    return out, ragged


# ── Guards ───────────────────────────────────────────────────────────────────

def assert_results_shape(rows: list[dict[str, str]], year: Optional[int]) -> list[str]:
    """⛔ Refuse a CANDIDATE list wearing a results URL.

    This is the Ontario/AMO trap in a second publisher. `rtype=results` returns
    `Elected` and `Number of Votes` as COLUMNS for the live cycle long before
    they hold anything — nominations for 2026 do not even close until
    2026-09-11 — and the same URL fills in progressively on election night
    ("results will be updated every 5 minutes"). So a run that happens to land
    mid-count reads a partial council as the whole council, and a wholesale
    apply would retire everyone not yet reported.

    The completed 2022 cycle returns 1,025 rows, every one `Elected=YES`. A
    populated `Elected` column is therefore the signal that counting is done.
    """
    problems: list[str] = []
    real = [r for r in rows if "__ragged__" not in r]
    if not real:
        return ["localelections.ca returned no parsable rows"]
    if "Elected" not in real[0]:
        return ["report has no `Elected` column — rtype=results was not honoured"]

    elected = sum(1 for r in real if r.get("Elected", "").strip().upper() == "YES")
    if elected == 0:
        problems.append(
            f"NO row in the {year or 'current'} report is marked Elected=YES "
            f"({len(real)} rows). This is a CANDIDATE list, not a result — "
            f"nominations close 2026-09-11 and results fill in on election "
            f"night. REFUSING: a partial council read as a whole one retires "
            f"everyone who has not reported yet."
        )
    elif elected < len(real):
        problems.append(
            f"only {elected} of {len(real)} rows are Elected=YES — counting "
            f"appears to be IN PROGRESS. REFUSING for the same reason."
        )
    return problems


def superseded_by(year: int, today: Optional[date] = None) -> Optional[int]:
    """The later cycle whose election has already happened, if any.

    ⛔ Same guard as Ontario's. Ingesting 2022 the morning after the 2026
    election would reinstate the defeated council over the winners, and it
    would look like a perfectly ordinary run. Derived from ELECTION_DATES so
    it starts refusing on its own, with no edit.
    """
    today = today or date.today()
    later = [y for y, d in ELECTION_DATES.items() if y > year and d <= today]
    return max(later) if later else None


async def verify_mapping(db: Database) -> list[str]:
    """Assert every hardcoded CSD code still names the council we think.

    ⛔ THE ONTARIO LESSON, APPLIED BEFORE IT COSTS ANYTHING. Eight of fourteen
    hardcoded AMO ids in `on_municipal_roster`'s first draft were wrong and
    three named a REAL BUT DIFFERENT municipality — none of which would have
    errored; each would have quietly ingested another council's roster.

    ⚠ AREA, NOT NAME, IS THE CHECK THAT MATTERS. Our boundary table calls both
    Langley (City) and Langley (Township) "Langley", so a name assertion passes
    even if the two codes are transposed — and 7-vs-9 members is plausible
    either way round. They differ 30x in area, so area is what separates them.
    """
    problems: list[str] = []
    for (lg, jtype), c in sorted(COUNCILS.items()):
        row = await db.fetchrow(
            """
            SELECT name, area_sqkm, boundary_kind, province_territory, level
              FROM constituency_boundaries
             WHERE constituency_id = $1
               AND effective_from <= CURRENT_DATE
               AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
            """,
            c.csd_code,
        )
        label = f"{lg} ({jtype})"
        if row is None:
            problems.append(f"{label}: {c.csd_code} is not a live boundary row")
            continue
        if row["province_territory"] != "BC" or row["level"] != "municipal":
            problems.append(
                f"{label}: {c.csd_code} is "
                f"{row['level']}/{row['province_territory']}, expected municipal/BC"
            )
        if row["boundary_kind"] != "municipality":
            problems.append(
                f"{label}: {c.csd_code} is boundary_kind='{row['boundary_kind']}', "
                f"expected 'municipality' — BC members attach to the whole "
                f"council polygon, never a district"
            )
        if (row["name"] or "").strip() != c.expected_name:
            problems.append(
                f"{label}: {c.csd_code} is named '{row['name']}', "
                f"expected '{c.expected_name}'"
            )
        area = row["area_sqkm"]
        if area is None:
            problems.append(f"{label}: {c.csd_code} has no area_sqkm to verify against")
        elif abs(area - c.expected_area_km2) / c.expected_area_km2 > AREA_TOLERANCE:
            problems.append(
                f"{label}: {c.csd_code} is {area:.1f} km², expected "
                f"~{c.expected_area_km2:.1f} km² — the code table is stale or "
                f"TWO CODES ARE TRANSPOSED (this is the check that separates "
                f"Langley City from Langley Township); REFUSING"
            )
    return problems


# ── Compare ──────────────────────────────────────────────────────────────────

@dataclass
class CouncilDiff:
    label: str
    csd_code: str
    authority: int
    held: int
    matched: int
    loose_matched: int = 0
    only_authority: list[str] = field(default_factory=list)
    only_held: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if not self.only_authority and not self.only_held:
            return "agree"
        if self.only_authority and not self.only_held:
            return "gap"          # we hold nobody for a seat the authority filled
        if self.only_held and not self.only_authority:
            return "extra"        # we hold somebody the authority does not
        return "diverge"


@dataclass
class CompareStats:
    year: int
    councils: int = 0
    authority_rows: int = 0
    held_rows: int = 0
    matched: int = 0
    ragged_rows: int = 0
    diffs: list[CouncilDiff] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


async def _held_by_council(db: Database) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in await db.fetch(
        """
        SELECT id, name, elected_office, constituency_id, source_id
          FROM politicians
         WHERE is_active AND level = 'municipal' AND province_territory = 'BC'
           AND constituency_id = ANY($1::text[])
        """,
        [c.csd_code for c in COUNCILS.values()],
    ):
        out.setdefault(r["constituency_id"], []).append(dict(r))
    return out


async def compare_bc_municipal_roster(
    db: Database, year: Optional[int] = None,
) -> CompareStats:
    """Read-only diff of localelections.ca against what we hold.

    ★ Compare-first, exactly as Ontario. Nothing here writes, and the per-council
    verdict is what authorises a later write — a council that does not come back
    `gap` or `diverge` is not writable, so a surprise in the source becomes a
    refusal instead of an edit.
    """
    # ⛔ The default is the most recent COMPLETED election, fetched EXPLICITLY
    # by year — never the bare current-cycle URL. Omitting `year` from the
    # request returns whatever cycle is live, which today is a candidate list
    # nominations have not closed on; labelling that as the last completed
    # election would be the worst of both. To inspect the live cycle, ask for
    # it by year and let assert_results_shape() refuse it on its merits.
    resolved_year = year if year is not None else max(
        (y for y, d in ELECTION_DATES.items() if d <= date.today()), default=2022
    )
    st = CompareStats(year=resolved_year)

    st.problems.extend(await verify_mapping(db))
    if st.problems:
        # ⛔ Abort the WHOLE run, not the bad rows. A stale code table means we
        # do not know which council we are reading.
        return st

    sup = superseded_by(resolved_year)
    if sup is not None:
        st.problems.append(
            f"cycle {resolved_year} is superseded by {sup} "
            f"(election {ELECTION_DATES[sup]}) — REFUSING"
        )
        return st

    rows: list[dict[str, str]] = []
    async with httpx.AsyncClient(
        timeout=60.0, follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for i, offices in enumerate(REPORT_OFFICES):
            if i:
                # robots.txt Crawl-delay: 5 — between every request.
                await asyncio.sleep(CRAWL_DELAY_SECONDS)
            page = await fetch_report(client, resolved_year, offices)
            _, part = parse_report(page)
            rows.extend(part)

    st.problems.extend(assert_results_shape(rows, resolved_year))
    if st.problems:
        return st

    members, st.ragged_rows = extract_members(rows)
    by_council: dict[tuple[str, str], list[Member]] = {}
    for m in members:
        by_council.setdefault(m.council_key, []).append(m)

    held = await _held_by_council(db)

    # ⚠ Several publisher keys can share one polygon (Vancouver council + park
    # board). Compare per POLYGON, or each body is diffed against the other's
    # members too and both look half-wrong.
    by_csd: dict[str, list[Member]] = {}
    labels: dict[str, list[str]] = {}
    for key, council in sorted(COUNCILS.items()):
        by_csd.setdefault(council.csd_code, []).extend(by_council.get(key, []))
        labels.setdefault(council.csd_code, []).append(f"{key[0]} ({key[1]})")

    seen_csd: set[str] = set()
    for key, council in sorted(COUNCILS.items()):
        if council.csd_code in seen_csd:
            continue
        seen_csd.add(council.csd_code)
        auth = by_csd.get(council.csd_code, [])
        ours = held.get(council.csd_code, [])
        auth_by = {norm_name(m.name): m for m in auth}
        held_by = {norm_name(h["name"]): h for h in ours}
        common = set(auth_by) & set(held_by)
        rest_a = set(auth_by) - common
        rest_h = set(held_by) - common
        # Second pass: pair off name-form artefacts so they stop reading as
        # gaps. Greedy and one-to-one — a held row can absorb at most one
        # authority row, so this can never manufacture matches.
        loose = 0
        for ka in sorted(rest_a):
            hit = next((kh for kh in sorted(rest_h)
                        if loose_same_person(auth_by[ka].name, held_by[kh]["name"])), None)
            if hit is not None:
                rest_a.discard(ka)
                rest_h.discard(hit)
                loose += 1
        d = CouncilDiff(
            label=" + ".join(labels[council.csd_code]),
            csd_code=council.csd_code,
            authority=len(auth), held=len(ours),
            matched=len(common) + loose, loose_matched=loose,
            only_authority=sorted(auth_by[k].name for k in rest_a),
            only_held=sorted(held_by[k]["name"] for k in rest_h),
        )
        st.diffs.append(d)
        st.councils += 1
        st.authority_rows += d.authority
        st.held_rows += d.held
        st.matched += d.matched

    return st


# ── Apply ────────────────────────────────────────────────────────────────────

@dataclass
class ApplyStats:
    year: int
    councils_written: int = 0
    installed: int = 0
    rekeyed: int = 0
    updated: int = 0
    retired: int = 0
    skipped_councils: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


async def _install(db: Database, m: Member, council: Council,
                   st: ApplyStats, dry_run: bool) -> None:
    """Insert or re-key one member. ⛔ Never replaces a person who is already here."""
    sid = f"{SOURCE_PREFIX}:{slugify(m.council_key[0])}-{slugify(m.council_key[1])}-council:{slugify(m.name)}"
    existing = await db.fetchrow("SELECT id, name FROM politicians WHERE source_id = $1", sid)

    if existing is None:
        # ★ RE-KEY A SITTING MEMBER RATHER THAN REPLACE THEM. The BC rows carry
        # socials, offices and websites accumulated over two years. Deactivating
        # someone and inserting a fresh row strands every one of those on an
        # inactive row — the defect migration 0069 exists to undo. A match here
        # moves the source_id and the person keeps their id and everything hung
        # off it, and simultaneously leaves the Open North retirement sweep.
        existing = await db.fetchrow(
            """
            SELECT id, name FROM politicians
             WHERE is_active AND level = 'municipal' AND province_territory = 'BC'
               AND constituency_id = $1
               AND regexp_replace(lower(unaccent(name)), '[^a-z0-9]+', '', 'g')
                 = regexp_replace(lower(unaccent($2)), '[^a-z0-9]+', '', 'g')
             LIMIT 1
            """,
            council.csd_code, m.name,
        )
        if existing is not None:
            if not dry_run:
                await db.execute(
                    "UPDATE politicians SET source_id = $2, updated_at = now() "
                    "WHERE id = $1::uuid", existing["id"], sid,
                )
            st.rekeyed += 1

    if existing is not None:
        # ⚠ The DB name wins over the publisher's. fix_caps() is a guess about a
        # name a human may already have corrected; re-casing `MacDougall` to
        # `Macdougall` on every run would be a slow, invisible regression.
        if not dry_run:
            await db.execute(
                """
                UPDATE politicians
                   SET elected_office = $2, constituency_id = $3,
                       constituency_name = $4, is_active = true, updated_at = now()
                 WHERE id = $1::uuid
                """,
                existing["id"], m.office, council.csd_code, council.expected_name,
            )
        st.updated += 1
        return

    # ⛔ REFUSE RATHER THAN RISK A DUPLICATE PERSON.
    #
    # The re-key search above is scoped to rows that are ACTIVE and ATTACHED to
    # this council's polygon. Someone who was retired, or whose constituency_id
    # a cutover left NULL, is invisible to it — and inserting then produces a
    # SECOND row for a person we already have. This project has an audit and a
    # merge script for exactly that damage; not creating it is cheaper.
    #
    # A same-named BC municipal row outside the search's scope is therefore a
    # STOP, not an insert. Reactivating a retired member and installing a
    # namesake are different decisions and nothing here can tell them apart.
    clash = await db.fetchrow(
        """
        SELECT id, name, is_active, constituency_id, source_id
          FROM politicians
         WHERE level = 'municipal' AND province_territory = 'BC'
           AND regexp_replace(lower(unaccent(name)), '[^a-z0-9]+', '', 'g')
             = regexp_replace(lower(unaccent($1)), '[^a-z0-9]+', '', 'g')
         LIMIT 1
        """,
        m.name,
    )
    if clash is not None:
        st.problems.append(
            f"{m.name} ({m.council_key[0]}): a BC municipal row already exists "
            f"for this name (id={clash['id']}, is_active={clash['is_active']}, "
            f"constituency_id={clash['constituency_id']}) but it is not an "
            f"active member of this council, so the re-key did not find it. "
            f"REFUSING to insert — that would create a duplicate person. "
            f"Reactivate or re-attach the existing row by hand."
        )
        return

    if not dry_run:
        row = await db.fetchrow(
            """
            INSERT INTO politicians (
                name, first_name, last_name, level, province_territory,
                constituency_id, constituency_name, elected_office,
                source_id, is_active, extras)
            VALUES ($1,$2,$3,'municipal','BC',$4,$5,$6,$7,true,$8::jsonb)
            RETURNING id
            """,
            m.name, m.first_name, m.last_name, council.csd_code,
            council.expected_name, m.office, sid,
            _extras_json(m, st.year),
        )
        await db.execute(
            """
            INSERT INTO politician_terms (politician_id, office, level,
                province_territory, constituency_id, started_at, source)
            VALUES ($1::uuid, $2, 'municipal', 'BC', $3, $4, $5)
            """,
            row["id"], m.office, council.csd_code,
            ELECTION_DATES[st.year], f"{SOURCE_PREFIX}:{slugify(m.council_key[0])}",
        )
    st.installed += 1


def _extras_json(m: Member, year: int) -> str:
    import json
    return json.dumps({"civicinfo_bc": {
        "elected_year": year,
        "votes": m.votes,
        "acclaimed": m.acclaimed,
        "elector_organization": m.organization or None,
        "publisher_name": m.raw_name,   # ⚠ before fix_caps, so the guess is auditable
        "source": "localelections.ca /report/index.php rtype=results",
    }})


async def apply_bc_municipal_roster(
    db: Database, year: Optional[int] = None, council: Optional[str] = None,
    dry_run: bool = True,
) -> ApplyStats:
    """Write the BC roster. ⛔ The compare verdict is the authorisation.

    Only councils the comparison reports as `gap` or `diverge` are written.
    `agree` needs no write; `extra` — we hold someone the authority does not —
    is REFUSED, because the two explanations are a retirement and a publisher
    omission, and this cannot tell them apart. That is the same call Québec
    makes when a held council is missing from the source file: a council whose
    absence is unexplained aborts rather than being wiped.
    """
    cmp_st = await compare_bc_municipal_roster(db, year=year)
    st = ApplyStats(year=cmp_st.year, problems=list(cmp_st.problems))
    if st.problems:
        return st

    # ⛔ Stale-cycle guard. See APPLY_FRESH_WINDOW_DAYS.
    age = (date.today() - ELECTION_DATES[st.year]).days
    if age > APPLY_FRESH_WINDOW_DAYS and not council:
        st.problems.append(
            f"the {st.year} election was {age} days ago "
            f"({ELECTION_DATES[st.year]}), past the {APPLY_FRESH_WINDOW_DAYS}-day "
            f"window in which a result is safe to write wholesale. Members have "
            f"since resigned and been replaced, and the result file never learns "
            f"— so a `gap` may be OUR hole or THEIR staleness, and this cannot "
            f"tell which. REFUSING a blanket write. Name a single council with "
            f"--council once you have confirmed it, or run this within 90 days "
            f"of the next election (BC votes {ELECTION_DATES.get(2026)})."
        )
        return st

    writable: set[str] = set()
    for d in cmp_st.diffs:
        if council and slugify(council) not in slugify(d.label):
            continue
        if d.verdict == "agree":
            continue
        if d.verdict == "extra":
            st.skipped_councils.append(
                f"{d.label}: verdict=extra — we hold {d.only_held} whom the "
                f"authority does not list. That is EITHER a retirement OR a "
                f"publisher omission and this cannot tell which. Refusing; "
                f"confirm against the council's own site."
            )
            continue
        writable.add(d.csd_code)
        st.councils_written += 1

    if not writable:
        return st

    # ⓘ Re-fetched for the write pass rather than threaded out of the
    # comparison, so compare() stays genuinely read-only and callable on its
    # own. Two more GETs, crawl-delayed like the first pair.

    rows: list[dict[str, str]] = []
    async with httpx.AsyncClient(
        timeout=60.0, follow_redirects=True, headers={"User-Agent": USER_AGENT},
    ) as client:
        for i, offices in enumerate(REPORT_OFFICES):
            if i:
                await asyncio.sleep(CRAWL_DELAY_SECONDS)
            _, part = parse_report(await fetch_report(client, st.year, offices))
            rows.extend(part)
    members, _ = extract_members(rows)

    for m in members:
        c = COUNCILS[m.council_key]
        if c.csd_code not in writable:
            continue
        await _install(db, m, c, st, dry_run)

    return st
