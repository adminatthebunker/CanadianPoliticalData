"""Prince Edward Island municipal rosters — Charlottetown, Summerside, Stratford.

PE's whole municipal exposure is three councils and 27 seats. There is no
province-wide source: Elections PEI is behind a Radware bot-manager CAPTCHA,
there is no PEI CKAN, and FPEIM's province-wide directory lists councillors as a
flat comma-separated string with NO ward attribution — excellent as a
cross-check, useless as the key our rows are built on. So this is three parsers.

★ ANCHORED ON THE WARD NUMBER WHEREVER THE NUMBER EXISTS, AND THE REASON IS
CHARLOTTETOWN. Our Charlottetown polygons carry `name = 'Ward N'` and a SLUG
that is a ward NAME — and two of those names are a generation out of date:

    ward   city (2026)      our slug
    4      Spring Park      st-avards      ← a name the city no longer uses
    5      Ellen's Creek    spring-park    ← the city's name for ward FOUR

⛔ So a name join does not merely fail here, it CROSS-WIRES: the city's "Spring
Park" (ward 4) matches our `spring-park` polygon, which is ward 5. A prior
research pass reported exactly that as "two councillors on the wrong ward". It
was wrong — checked against the city's own page on 2026-09-02, ward 4 is
Mitchell G. Tweel and ward 5 is Kevin Ramsay, which is precisely what we hold.
The ROSTER was right; the ward NAMES are what is stale. Anchoring on the number
is what makes that distinction visible instead of costing two wrong re-keys.

⚠ Summerside and Stratford polygons have no number at all — only names — so
those two map by slugified name, and `verify_mapping()` refuses unless the
mapping is complete and one-to-one.

⚠ MULTI-SEAT WARDS. Stratford elects TWO councillors per ward across three
wards. Comparison is therefore over the SET of holders per ward, never a single
holder, which also covers the one-seat councils without a special case.

⛔ FETCH POSTURE — townofstratford.ca IS AN OPERATOR DECISION, NOT A DEFAULT.
Its robots.txt carries a Cloudflare-managed block listing `User-agent: ClaudeBot
-> Disallow: /`, plus `Content-Signal: search=yes, ai-train=no, use=reference`
for everyone, framed as an express reservation of rights under Article 4 of EU
Directive 2019/790. Unlike the CivicInfo BC case, that is on THE HOST WE FETCH,
not a parent domain. The operator's decision on 2026-09-02 was to fetch it as a
CPD-identified civic ingester, on the reading that the `*` rule is `Allow: /`
with `use=reference` and the Disallow list is a managed AI-crawler roster rather
than a restriction on this use. ⚠ Anyone revisiting this should revisit that
decision, not assume it. Charlottetown and Summerside carry no such directive.
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

SOURCE_PREFIX = "pei-municipal"
USER_AGENT = (
    "CanadianPoliticalData/1.0 "
    "(+https://canadianpoliticaldata.org; admin@thebunkerops.ca)"
)
CRAWL_DELAY_SECONDS = 3.0

# ★ 2026-11-02 is NOT a statutory-cycle inference. The City of Summerside states
# it outright on its own council page, explaining that the mayoralty stays vacant
# until then: "the office of the Mayor will be determined at the next municipal
# general election on November 2, 2026". Confirmed from a government source
# 2026-09-02; it had been an inference until that moment.
ELECTION_DATES: dict[int, date] = {
    2018: date(2018, 11, 5),
    2022: date(2022, 11, 7),
    2026: date(2026, 11, 2),
}


@dataclass(frozen=True)
class Council:
    slug: str
    source_set: str
    municipality_cid: str      # the mayor's polygon
    expected_wards: int
    seats_per_ward: int        # ⚠ Stratford elects TWO per ward
    url: str
    numbered_polygons: bool    # do OUR polygons carry "Ward N" in `name`?


COUNCILS: dict[str, Council] = {
    "charlottetown": Council(
        slug="charlottetown", source_set="charlottetown-wards",
        municipality_cid="census-subdivisions/1102075",
        expected_wards=10, seats_per_ward=1,
        url="https://www.charlottetown.ca/mayor___council/city_council/meet_my_councillor",
        numbered_polygons=True,
    ),
    "summerside": Council(
        slug="summerside", source_set="summerside-wards",
        municipality_cid="census-subdivisions/1103025",
        expected_wards=8, seats_per_ward=1,
        url="https://www.summerside.ca/city_governance/senior_leadership_mayor_council",
        numbered_polygons=False,
    ),
    "stratford": Council(
        slug="stratford", source_set="stratford-wards",
        municipality_cid="census-subdivisions/1102080",
        expected_wards=3, seats_per_ward=2,
        url="https://townofstratford.ca/government-services/contact-town-of-stratford/mayor-council/",
        numbered_polygons=False,
    ),
}

OFFICES = ("Mayor", "Deputy Mayor", "Councillor")


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    # ⚠ Dash and apostrophe normalisation is load-bearing, not cosmetic. One
    # Summerside page writes the SAME ward three ways — "Center East -Downtown",
    # "Green Shore - Three Oaks", "Greenshore -Three Oaks" — and Stratford
    # writes "Kelly’s Cove" with U+2019, not an ASCII apostrophe. Our slugs are
    # `center-east-downtown` and `kellys-cove`. This is cross-cutting decision
    # C5 in the boundary corpus, still open, handled locally here.
    s = s.replace("’", "'").replace("‘", "'")
    for dash in ("—", "–", "−"):
        s = s.replace(dash, "-")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def strip_middle_initial(s: str) -> str:
    """`Mitchell G. Tweel` -> `mitchell tweel`, for comparison only.

    ⚠ Reporting only, never identity. Our row says "Mitchell G. Tweel" and the
    city says "Mitchell Tweel"; without this the seat reads `stale` forever and
    an apply would retire him and reinstall him under a new id every run.
    """
    toks = [t for t in norm_name(s).split() if len(t) > 1]
    return " ".join(toks)


@dataclass
class Member:
    council: str
    person: str
    office: str
    ward_no: Optional[int]
    ward_name: str

    @property
    def is_citywide(self) -> bool:
        return self.ward_no is None


# ── Parsers ──────────────────────────────────────────────────────────────────

def _lines(page: str) -> list[str]:
    """Tags -> newlines, so a person and their ward stay adjacent.

    ⓘ All three sites put the office+name in one element and the ward in the
    next, so line adjacency is the structure; a flattened single-string parse
    loses it and starts matching a name to the following person's ward.
    """
    txt = _html.unescape(re.sub(r"<[^>]+>", "\n", page))
    txt = re.sub(r"[ \t]+", " ", txt)
    return [l.strip() for l in txt.split("\n") if l.strip()]


_OFFICE_RE = re.compile(
    r"^(Deputy Mayor / Councillor|Deputy Mayor|Mayor|Councillor)\s+"
    r"([A-Z][A-Za-z'’\.\-]+(?:\s+[A-Z][A-Za-z'’\.\-]+){0,3})\s*$"
)
# ", Ward 3, Tea Hill" (Stratford) and "Ward 4: Clifton - Market" (Summerside).
_WARD_RE = re.compile(r"^[,\s]*Ward\s*(\d{1,2})\s*[:,]\s*(.+?)\s*$")
_WARD_BARE_RE = re.compile(r"^[,\s]*Ward\s*(\d{1,2})\b")


def parse_adjacent(page: str, council: str) -> list[Member]:
    """Summerside + Stratford: `<Office> <Name>` then `Ward N: <Name>` after it."""
    ls = _lines(page)
    out: list[Member] = []
    seen: set[tuple[str, str]] = set()
    for i, line in enumerate(ls):
        m = _OFFICE_RE.match(line)
        if not m:
            continue
        office_raw, person = m.group(1), m.group(2).strip()
        # "Deputy Mayor / Councillor" is one person holding a ward seat plus a
        # title; the ward seat is the one our rows model.
        office = "Councillor" if "Councillor" in office_raw else office_raw
        key = (office, norm_name(person))
        if key in seen:
            continue
        ward_no, ward_name = None, ""
        for nxt in ls[i + 1:i + 3]:
            w = _WARD_RE.match(nxt)
            if w:
                ward_no, ward_name = int(w.group(1)), w.group(2).strip()
                break
            if _WARD_BARE_RE.match(nxt):
                ward_no = int(_WARD_BARE_RE.match(nxt).group(1))
                break
        if office == "Mayor" and ward_no is not None:
            ward_no = None      # a mayor is city-wide even if listed near a ward
        seen.add(key)
        out.append(Member(council=council, person=person, office=office,
                          ward_no=ward_no, ward_name=ward_name))
    return out


# ⚠ The `(?:\([^)]*\))?` is not decoration. Two of Charlottetown's ten
# councillors publish PRONOUNS between their name and their ward —
# "Alanna Jankov (she/her) - Ward 1", "John McAleer (he/him) - Ward 7" — and
# without it the parser silently dropped exactly those two and reported them as
# orphaned seats. A parser that reads 8 of 10 and says nothing is worse than one
# that fails, because the two it loses look like real defects in our data.
_CT_RE = re.compile(
    r"(Councillor|Deputy Mayor|Mayor)\s+"
    r"([A-Z][A-Za-z'’\.\-]+(?:\s+[A-Z][A-Za-z'’\.\-]+){0,3}?)"
    r"\s*(?:\([^)]*\))?"
    r"\s*[-–—,]?\s*Ward\s+(\d{1,2})"
)


def parse_charlottetown(page: str) -> list[Member]:
    """Charlottetown states the ward NUMBER inline and never the ward name."""
    txt = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", page)))
    out: list[Member] = []
    seen: set[tuple[int, str]] = set()
    for m in _CT_RE.finditer(txt):
        office, person, ward = m.group(1), m.group(2).strip(), int(m.group(3))
        if (ward, norm_name(person)) in seen:
            continue
        seen.add((ward, norm_name(person)))
        out.append(Member(council="charlottetown", person=person,
                          office="Councillor" if office != "Mayor" else "Mayor",
                          ward_no=ward, ward_name=""))
    mm = re.search(r"\bMayor\s+([A-Z][A-Za-z'’\.\-]+(?:\s+[A-Z][A-Za-z'’\.\-]+){0,2})", txt)
    if mm and not any(x.office == "Mayor" for x in out):
        out.append(Member(council="charlottetown", person=mm.group(1).strip(),
                          office="Mayor", ward_no=None, ward_name=""))
    return out


PARSERS = {
    "charlottetown": parse_charlottetown,
    "summerside": lambda p: parse_adjacent(p, "summerside"),
    "stratford": lambda p: parse_adjacent(p, "stratford"),
}


async def fetch(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url)
    r.raise_for_status()
    return r.text


# ── Mapping ──────────────────────────────────────────────────────────────────

async def verify_mapping(db: Database, c: Council) -> tuple[dict, list[str]]:
    """ward key -> constituency_id, checked against the DB every run.

    For Charlottetown the key is the ward NUMBER, parsed out of our polygon's
    own `name` ("Ward 4"). For the other two it is the slugified ward NAME,
    because those polygons carry no number.
    """
    problems: list[str] = []
    mapping: dict = {}
    rows = await db.fetch(
        """
        SELECT constituency_id, name FROM constituency_boundaries
         WHERE source_set = $1 AND boundary_kind = 'district'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
        """,
        c.source_set,
    )
    if len(rows) != c.expected_wards:
        problems.append(
            f"{c.slug}: expected {c.expected_wards} live wards in "
            f"{c.source_set}, found {len(rows)}"
        )
    for r in rows:
        if c.numbered_polygons:
            m = re.match(r"^Ward\s+(\d{1,2})$", (r["name"] or "").strip())
            if not m:
                problems.append(
                    f"{c.slug}: {r['constituency_id']} is named "
                    f"{r['name']!r}, not 'Ward N' — the numeric anchor is "
                    f"unavailable and a NAME join here cross-wires wards 4/5"
                )
                continue
            key = int(m.group(1))
        else:
            key = slugify(r["name"] or "")
            if not key:
                problems.append(f"{c.slug}: {r['constituency_id']} has no usable name")
                continue
        if key in mapping:
            problems.append(f"{c.slug}: ward key {key!r} claimed by two polygons")
            continue
        mapping[key] = r["constituency_id"]

    if c.numbered_polygons:
        missing = [n for n in range(1, c.expected_wards + 1) if n not in mapping]
        if missing:
            problems.append(f"{c.slug}: ward numbers absent from geometry: {missing}")

    muni = await db.fetchrow(
        """
        SELECT boundary_kind FROM constituency_boundaries
         WHERE constituency_id = $1
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
        """,
        c.municipality_cid,
    )
    if muni is None:
        problems.append(
            f"{c.slug}: {c.municipality_cid} is not live — the mayor has nowhere to attach"
        )
    elif muni["boundary_kind"] != "municipality":
        problems.append(
            f"{c.slug}: {c.municipality_cid} is '{muni['boundary_kind']}', expected 'municipality'"
        )
    return mapping, problems


# ── Compare ──────────────────────────────────────────────────────────────────

@dataclass
class SeatDiff:
    council: str
    ward_label: str
    constituency_id: str
    authority: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    verdict: str = "agree"


@dataclass
class CompareStats:
    diffs: list[SeatDiff] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)

    def count(self, v: str) -> int:
        return sum(1 for d in self.diffs if d.verdict == v)


def _classify(auth: list[str], held: list[str]) -> str:
    """⚠ Set comparison, because Stratford elects TWO councillors per ward.

    Middle initials are stripped for the comparison only — our row says
    "Mitchell G. Tweel" and Charlottetown says "Mitchell Tweel", and without
    this that seat reads `stale` forever and an apply retires and reinstalls him
    on every run.
    """
    a = {strip_middle_initial(x) for x in auth}
    h = {strip_middle_initial(x) for x in held}
    if a == h:
        return "agree"
    if a and not h:
        return "gap"
    if h and not a:
        return "orphan"
    if a - h and not (h - a):
        return "gap"        # authority names someone extra; we are short
    if h - a and not (a - h):
        return "vacancy"    # we hold someone the authority dropped
    return "stale"


async def compare_pe_municipal_roster(
    db: Database, council: Optional[str] = None,
) -> CompareStats:
    """Read-only, ward-anchored diff across the three PEI councils."""
    st = CompareStats()
    targets = [c for k, c in COUNCILS.items()
               if council is None or slugify(council) == k]
    if not targets:
        st.problems.append(f"unknown council {council!r}")
        return st

    async with httpx.AsyncClient(
        timeout=60.0, follow_redirects=True, headers={"User-Agent": USER_AGENT},
    ) as client:
        for i, c in enumerate(targets):
            if i:
                await asyncio.sleep(CRAWL_DELAY_SECONDS)
            mapping, problems = await verify_mapping(db, c)
            st.problems.extend(problems)
            if problems:
                continue

            members = PARSERS[c.slug](await fetch(client, c.url))
            if not members:
                st.problems.append(f"{c.slug}: parsed no members — layout changed?")
                continue

            by_key: dict[object, list[str]] = {}
            for m in members:
                if m.is_citywide:
                    by_key.setdefault("__mayor__", []).append(m.person)
                    continue
                key = m.ward_no if c.numbered_polygons else slugify(m.ward_name)
                if key not in mapping:
                    st.unmapped.append(
                        f"{c.slug}: authority ward {m.ward_no} "
                        f"({m.ward_name!r}) matches no polygon — {m.person}"
                    )
                    continue
                by_key.setdefault(key, []).append(m.person)

            held: dict[str, list[str]] = {}
            for r in await db.fetch(
                """
                SELECT name, constituency_id FROM politicians
                 WHERE is_active AND level='municipal' AND province_territory='PE'
                   AND constituency_id = ANY($1::text[])
                """,
                list(mapping.values()) + [c.municipality_cid],
            ):
                held.setdefault(r["constituency_id"], []).append(r["name"])

            for key in sorted(mapping, key=str):
                cid = mapping[key]
                a, h = sorted(by_key.get(key, [])), sorted(held.get(cid, []))
                st.diffs.append(SeatDiff(
                    council=c.slug,
                    ward_label=(f"ward {key}" if c.numbered_polygons else str(key)),
                    constituency_id=cid, authority=a, held=h,
                    verdict=_classify(a, h),
                ))
            a, h = sorted(by_key.get("__mayor__", [])), sorted(held.get(c.municipality_cid, []))
            st.diffs.append(SeatDiff(
                council=c.slug, ward_label="mayor",
                constituency_id=c.municipality_cid, authority=a, held=h,
                verdict=_classify(a, h),
            ))
    return st


# ── Apply ────────────────────────────────────────────────────────────────────

@dataclass
class ApplyStats:
    installed: int = 0
    rekeyed: int = 0
    updated: int = 0
    skipped: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


async def apply_pe_municipal_roster(
    db: Database, council: Optional[str] = None, dry_run: bool = True,
) -> ApplyStats:
    """Write the PEI rosters. ⛔ The per-ward verdict is the authorisation.

    Only `stale` and `gap` are written — the cases where the city names a holder
    we do not have. `agree` needs no write.

    ⛔ `orphan` and `vacancy` are REFUSED, and deliberately so even though both
    currently-known instances are real (Summerside's mayor resigned 2026-09-01;
    Stratford's Tea Hill lost one of two seats). Removing a sitting official is
    the least reversible thing this code could do, and "the page did not mention
    them" is indistinguishable from a template change, a lazy-loaded block, or a
    parser regression. ★ That is not hypothetical here: this parser silently
    dropped two of Charlottetown's ten councillors on its first run — they
    publish pronouns between their name and their ward — and reported them as
    orphans. An auto-retire path would have deactivated two sitting councillors
    over a missing `(she/her)`.

    Verified departures are written as migrations, with the publisher's own
    words recorded — see 0128.
    """
    cmp_st = await compare_pe_municipal_roster(db, council=council)
    st = ApplyStats(problems=list(cmp_st.problems))
    if st.problems:
        return st

    for d in cmp_st.diffs:
        if d.verdict == "agree":
            continue
        if d.verdict in ("orphan", "vacancy"):
            st.skipped.append(
                f"{d.council}/{d.ward_label}: verdict={d.verdict} — we hold "
                f"{d.held} and the city lists {d.authority or 'nobody'}. "
                f"Refusing to remove a sitting official on the absence of a "
                f"name from a page; confirm and write a migration."
            )
            continue
        for person in d.authority:
            if any(strip_middle_initial(person) == strip_middle_initial(h)
                   for h in d.held):
                continue
            await _install(db, person, d, st, dry_run)
    return st


async def _install(db: Database, person: str, d: SeatDiff,
                   st: ApplyStats, dry_run: bool) -> None:
    sid = f"{SOURCE_PREFIX}:{d.council}-council:{slugify(person)}"
    existing = await db.fetchrow("SELECT id FROM politicians WHERE source_id = $1", sid)

    if existing is None:
        # Re-key rather than replace — keeps id, socials, offices, websites.
        existing = await db.fetchrow(
            """
            SELECT id FROM politicians
             WHERE is_active AND level='municipal' AND province_territory='PE'
               AND regexp_replace(lower(unaccent(name)), '[^a-z0-9]+', '', 'g')
                 = regexp_replace(lower(unaccent($1)), '[^a-z0-9]+', '', 'g')
             LIMIT 1
            """,
            person,
        )
        if existing is not None:
            if not dry_run:
                await db.execute(
                    "UPDATE politicians SET source_id=$2, updated_at=now() "
                    "WHERE id=$1::uuid", existing["id"], sid)
            st.rekeyed += 1

    if existing is not None:
        if not dry_run:
            await db.execute(
                "UPDATE politicians SET constituency_id=$2, is_active=true, "
                "updated_at=now() WHERE id=$1::uuid",
                existing["id"], d.constituency_id)
        st.updated += 1
        return

    clash = await db.fetchrow(
        """
        SELECT id, is_active FROM politicians
         WHERE level='municipal' AND province_territory='PE'
           AND regexp_replace(lower(unaccent(name)), '[^a-z0-9]+', '', 'g')
             = regexp_replace(lower(unaccent($1)), '[^a-z0-9]+', '', 'g')
         LIMIT 1
        """,
        person,
    )
    if clash is not None:
        st.problems.append(
            f"{person} ({d.council}): a PE municipal row already exists "
            f"(id={clash['id']}, is_active={clash['is_active']}) that the "
            f"re-key did not find. REFUSING to insert a duplicate person."
        )
        return

    parts = person.split()
    first, last = (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (person, "")
    office = "Mayor" if d.ward_label == "mayor" else "Councillor"
    if not dry_run:
        import json
        row = await db.fetchrow(
            """
            INSERT INTO politicians (name, first_name, last_name, level,
                province_territory, constituency_id, elected_office,
                source_id, is_active, extras)
            VALUES ($1,$2,$3,'municipal','PE',$4,$5,$6,true,$7::jsonb)
            RETURNING id
            """,
            person, first, last, d.constituency_id, office, sid,
            json.dumps({"pei_municipal": {
                "council": d.council, "ward": d.ward_label,
                "source": COUNCILS[d.council].url}}),
        )
        await db.execute(
            """
            INSERT INTO politician_terms (politician_id, office, level,
                province_territory, constituency_id, started_at, source)
            VALUES ($1::uuid,$2,'municipal','PE',$3,$4,$5)
            """,
            row["id"], office, d.constituency_id,
            ELECTION_DATES[2022], f"{SOURCE_PREFIX}:{d.council}-council",
        )
    st.installed += 1
