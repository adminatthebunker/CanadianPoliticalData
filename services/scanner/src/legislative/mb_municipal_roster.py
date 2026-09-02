"""Manitoba municipal roster — City of Winnipeg, from its own open-data portal.

MB's entire municipal exposure is one council: Winnipeg, 16 seats. There is no
province-wide source and none is needed.

★ THE SOURCE IS A ROSTER DATASET, NOT A BOUNDARY FILE. `data.winnipeg.ca`
publishes ward geometry (`t4cg-yaxs`) that carries a `councillor` field, and the
obvious move is to read the roster out of the geometry. Don't:

  - `t4cg-yaxs` has no MAYOR. A ward file structurally cannot carry a city-wide
    seat, and the mayor is 1 of our 16 MB rows.
  - it carries no term or currency flag, so "is this person still in office" has
    to be inferred from the file's own age.
  - ⚠ and its declared licence is the string "Open Government Licence - Prince
    Edward Island", which is simply wrong metadata on a Winnipeg dataset.
    Re-confirmed still wrong 2026-09-02.

`r4tk-7dip` ("Council Data") has none of those problems: it carries the mayor as
`ward_id=0`, an explicit `current_council` boolean, and a correctly declared
**Canada Open Government Licence**. It also RETAINS PRIOR CYCLES (2014/2018/2022,
16 rows each), so detecting who left is a diff inside one file rather than a
sweep-and-deactivate against a vanished mirror.

★ AND THE JOIN IS NUMERIC. Our `winnipeg-wards` polygons carry
`authority_district_id` = the ward number, a dense 1..15, and Socrata's `ward_id`
is the same number. So this never matches a person to a district by NAME —
which is both the standing guardrail and, here, a concrete trap:

⛔ `web_name` LOOKS like a safe key and is not. It is kebab-case, it matches our
`winnipeg-wards/<slug>` form, and it agrees with `slugify(name_english)` on 15 of
16 rows. It diverges on exactly one: ward 7 is `Charleswood - Tuxedo - Westwood`
but its `web_name` is the truncated `charleswood-tuxedo`, which matches NO
polygon. One silently orphaned councillor is exactly the kind of defect a
15-of-16 agreement rate hides.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import httpx

from ..db import Database

# Matches the prefix already on the one non-mirror MB row, so this ingester and
# whoever added Emma Durand-Wood by hand agree on identity.
SOURCE_PREFIX = "city-of-winnipeg"
COUNCIL_SLUG = "winnipeg-city-council"

HOST = "data.winnipeg.ca"
DATASET = "r4tk-7dip"
USER_AGENT = (
    "CanadianPoliticalData/1.0 "
    "(+https://canadianpoliticaldata.org; admin@thebunkerops.ca)"
)
# robots.txt: `User-agent: * / Crawl-delay: 1`, Disallow only on faceted /browse?
# URLs. /resource/ and /api/views/ are open. Licence on this dataset is declared
# "Canada Open Government Licence".
CRAWL_DELAY_SECONDS = 1.0

WARD_SET = "winnipeg-wards"
# The mayor is elected city-wide, so he attaches to the municipality polygon —
# the same tiering Québec uses (qc_municipal_roster.py:395-413), not a ward.
MUNICIPALITY_CID = "census-subdivisions/4611040"
EXPECTED_WARDS = 15

# Manitoba general municipal elections: FOURTH WEDNESDAY of October, every four
# years. ⓘ 2018-10-24 is not an inference — it is the `effective_from` our own
# winnipeg-wards generation carries under ruling A10.4, which dates a map to the
# election it first governed. The rest follow from the same rule.
ELECTION_DATES: dict[int, date] = {
    2014: date(2014, 10, 22),
    2018: date(2018, 10, 24),
    2022: date(2022, 10, 26),
    2026: date(2026, 10, 28),
}

OFFICE_MAP = {"mayor": "Mayor", "councillor": "Councillor"}


def superseded_by(year: int, today: Optional[date] = None) -> Optional[int]:
    """The later cycle whose election has already happened, if any.

    ⛔ WITHOUT THIS, `--year 2018` WRITES THE 2018 COUNCIL OVER THE 2022 ONE.
    Caught in testing: the 2018 dry run reported installed=4 rekeyed=1 updated=1
    retired=5 — five sitting councillors retired and their predecessors
    reinstated, on a clean run with no error. The dataset retains prior cycles,
    which is exactly what makes it good for retirement detection AND what makes
    an unguarded --year dangerous.

    ⓘ Note this guard is only reachable via an explicit `--year`. The default
    path asks Socrata for `current_council=true` and never names a cycle, which
    is the trustworthy way to use this source.
    """
    today = today or date.today()
    later = [y for y, d in ELECTION_DATES.items() if y > year and d <= today]
    return max(later) if later else None


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def split_name(person: str) -> tuple[str, str]:
    """`person` is a single display string; split conservatively.

    ⚠ First token is the given name, everything else is the surname — so
    `Markus Chambers` splits cleanly and a hypothetical `Emma Durand-Wood`
    keeps its hyphenated surname whole. This is only used for NEW rows; an
    existing row's names are never overwritten from here.
    """
    parts = (person or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


@dataclass
class Member:
    ward_id: int          # 0 = mayor, 1..15 = wards
    ward_name: str
    person: str
    office: str
    year: int
    web_name: str

    @property
    def is_mayor(self) -> bool:
        return self.ward_id == 0


# ── Fetch ────────────────────────────────────────────────────────────────────

async def fetch_council(client: httpx.AsyncClient,
                        year: Optional[int] = None) -> list[dict]:
    """Socrata rows. `year=None` returns whoever the city says is sitting."""
    params = {
        "$select": "year,current_council,ward_id,name_english,web_name,person,"
                   "position_english,email_link_english,phone,website",
        "$order": "ward_id",
        "$limit": "500",
    }
    params["$where"] = (
        "current_council=true" if year is None else f"year={int(year)}"
    )
    r = await client.get(f"https://{HOST}/resource/{DATASET}.json", params=params)
    r.raise_for_status()
    return r.json()


def extract_members(rows: list[dict]) -> tuple[list[Member], list[str]]:
    out: list[Member] = []
    problems: list[str] = []
    for r in rows:
        pos = (r.get("position_english") or "").strip().lower()
        office = OFFICE_MAP.get(pos)
        if office is None:
            problems.append(f"unknown position_english {pos!r} — skipped")
            continue
        raw_ward = r.get("ward_id")
        try:
            ward_id = int(str(raw_ward).strip())
        except (TypeError, ValueError):
            problems.append(f"non-numeric ward_id {raw_ward!r} — skipped")
            continue
        person = (r.get("person") or "").strip()
        if not person:
            problems.append(f"ward {ward_id} has no `person` — skipped")
            continue
        try:
            yr = int(str(r.get("year")).strip())
        except (TypeError, ValueError):
            problems.append(f"ward {ward_id} has no usable `year` — skipped")
            continue
        out.append(Member(
            ward_id=ward_id,
            ward_name=(r.get("name_english") or "").strip(),
            person=person, office=office, year=yr,
            web_name=(r.get("web_name") or "").strip(),
        ))
    return out, problems


# ── Guards ───────────────────────────────────────────────────────────────────

async def verify_mapping(db: Database) -> tuple[dict[int, str], list[str]]:
    """ward number -> our constituency_id, checked against the DB every run.

    Returns the map and any problems. ⛔ A non-empty problem list aborts the
    whole run: if the ward numbering has moved we do not know which district we
    are writing to, and a roster write keyed on the wrong number is silent.
    """
    problems: list[str] = []
    mapping: dict[int, str] = {}

    rows = await db.fetch(
        """
        SELECT constituency_id, name, authority_district_id
          FROM constituency_boundaries
         WHERE source_set = $1 AND boundary_kind = 'district'
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
        """,
        WARD_SET,
    )
    for r in rows:
        raw = (r["authority_district_id"] or "").strip()
        if not raw.isdigit():
            problems.append(
                f"{r['constituency_id']} has authority_district_id {raw!r}, "
                f"which is not a ward number — the numeric join is unavailable"
            )
            continue
        n = int(raw)
        if n in mapping:
            problems.append(f"ward {n} is claimed by two live polygons")
            continue
        mapping[n] = r["constituency_id"]

    if len(rows) != EXPECTED_WARDS:
        problems.append(
            f"expected {EXPECTED_WARDS} live {WARD_SET} districts, found {len(rows)}"
        )
    missing = [n for n in range(1, EXPECTED_WARDS + 1) if n not in mapping]
    if missing:
        problems.append(f"ward numbers absent from our geometry: {missing}")

    muni = await db.fetchrow(
        """
        SELECT constituency_id, boundary_kind FROM constituency_boundaries
         WHERE constituency_id = $1
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
        """,
        MUNICIPALITY_CID,
    )
    if muni is None:
        problems.append(
            f"{MUNICIPALITY_CID} is not a live boundary — the MAYOR has nowhere "
            f"to attach; he is elected city-wide, not in a ward"
        )
    elif muni["boundary_kind"] != "municipality":
        problems.append(
            f"{MUNICIPALITY_CID} is boundary_kind='{muni['boundary_kind']}', "
            f"expected 'municipality'"
        )
    else:
        mapping[0] = MUNICIPALITY_CID
    return mapping, problems


def assert_publisher_caught_up(members: list[Member],
                               today: Optional[date] = None) -> list[str]:
    """⛔ THE MB TRAP, AND IT IS THE INVERSE OF ONTARIO'S.

    AMO and CivicInfo BC publish a CANDIDATE list that becomes a result — the
    danger there is reading it too early. Winnipeg publishes neither: it carries
    a settled council and, per its own metadata, is "updated each election year
    with data on new set of Council members". So `current_council=true` keeps
    pointing at the OUTGOING council until a human at the city refreshes it.

    That inverts the failure. Running this the morning after 2026-10-28 would
    not read a half-counted election — it would confidently re-write the 2022
    council over the 2026 one, and every check would pass, because the data is
    internally consistent and simply old.

    So the assertion is on the FILE'S OWN `year`: if an election has been held
    and the rows still carry the previous cycle, the publisher has not caught up
    and there is nothing here worth ingesting yet.
    """
    today = today or date.today()
    if not members:
        return ["no members returned"]
    years = {m.year for m in members}
    if len(years) > 1:
        return [f"rows span multiple cycles {sorted(years)} — expected one"]
    file_year = years.pop()

    latest_held = max((y for y, d in ELECTION_DATES.items() if d <= today),
                      default=None)
    if latest_held is None:
        return []
    if file_year < latest_held:
        return [
            f"the {latest_held} election was held "
            f"({ELECTION_DATES[latest_held]}) but data.winnipeg.ca still marks "
            f"the {file_year} council as current. The city updates this dataset "
            f"by hand after each election and has not done so yet. REFUSING — "
            f"ingesting now would write the OUTGOING council over the incoming "
            f"one, and nothing downstream would notice."
        ]
    return []


# ── Compare ──────────────────────────────────────────────────────────────────

@dataclass
class SeatVerdict:
    ward_id: int
    ward_name: str
    constituency_id: str
    authority: Optional[str]      # who the city says holds it
    held: Optional[str]           # who we say
    verdict: str                  # agree | stale | gap | orphan


@dataclass
class CompareStats:
    year: Optional[int] = None
    seats: list[SeatVerdict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def count(self, v: str) -> int:
        return sum(1 for s in self.seats if s.verdict == v)


async def compare_mb_municipal_roster(
    db: Database, year: Optional[int] = None,
) -> CompareStats:
    """Read-only, SEAT-ANCHORED diff. Writes nothing.

    ★ Anchored on the ward NUMBER, so each verdict is about one seat and one
    person. That is what makes a loose name comparison safe here: a ward holds
    exactly one councillor, so "the city says X and we say Y for ward 7" is
    unambiguous in a way that a council-wide name-set diff never is.
    """
    st = CompareStats()
    mapping, problems = await verify_mapping(db)
    st.problems.extend(problems)
    if st.problems:
        return st

    async with httpx.AsyncClient(
        timeout=45.0, follow_redirects=True, headers={"User-Agent": USER_AGENT},
    ) as client:
        rows = await fetch_council(client, year=year)

    members, parse_problems = extract_members(rows)
    st.problems.extend(parse_problems)
    if year is None:
        st.problems.extend(assert_publisher_caught_up(members))
    else:
        sup = superseded_by(year)
        if sup is not None:
            st.problems.append(
                f"cycle {year} is superseded by {sup} (election "
                f"{ELECTION_DATES[sup]}) — REFUSING. Writing it would retire "
                f"sitting councillors and reinstate their predecessors. Omit "
                f"--year to use whoever the city marks current_council."
            )
    if st.problems:
        return st
    st.year = members[0].year if members else None

    by_ward = {m.ward_id: m for m in members}
    if len(by_ward) != len(members):
        st.problems.append("two members share a ward_id — refusing")
        return st

    held: dict[str, dict] = {}
    for r in await db.fetch(
        """
        SELECT id, name, elected_office, constituency_id
          FROM politicians
         WHERE is_active AND level = 'municipal' AND province_territory = 'MB'
           AND constituency_id = ANY($1::text[])
        """,
        list(mapping.values()),
    ):
        held[r["constituency_id"]] = dict(r)

    for ward_id in sorted(mapping):
        cid = mapping[ward_id]
        m = by_ward.get(ward_id)
        h = held.get(cid)
        auth_name = m.person if m else None
        held_name = h["name"] if h else None
        if m and h:
            v = "agree" if norm_name(m.person) == norm_name(h["name"]) else "stale"
        elif m and not h:
            v = "gap"          # the city fills a seat we hold nobody for
        elif h and not m:
            v = "orphan"       # we hold someone the city does not list
        else:
            continue
        st.seats.append(SeatVerdict(
            ward_id=ward_id,
            ward_name=(m.ward_name if m else (h or {}).get("name", "")),
            constituency_id=cid, authority=auth_name, held=held_name, verdict=v,
        ))
    return st


# ── Apply ────────────────────────────────────────────────────────────────────

@dataclass
class ApplyStats:
    year: Optional[int] = None
    installed: int = 0
    rekeyed: int = 0
    updated: int = 0
    retired: int = 0
    skipped: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


async def apply_mb_municipal_roster(
    db: Database, year: Optional[int] = None, dry_run: bool = True,
) -> ApplyStats:
    """Write the Winnipeg roster. ⛔ The per-seat verdict is the authorisation.

    Only `stale` and `gap` seats are written — the two cases where the city
    names a holder and we either disagree or hold nobody. `agree` needs no
    write. `orphan` — we hold someone the city does not list for that ward — is
    REFUSED, because that is either a retirement the city has recorded or a
    publisher omission, and this cannot tell them apart.
    """
    cmp_st = await compare_mb_municipal_roster(db, year=year)
    st = ApplyStats(year=cmp_st.year, problems=list(cmp_st.problems))
    if st.problems:
        return st

    async with httpx.AsyncClient(
        timeout=45.0, follow_redirects=True, headers={"User-Agent": USER_AGENT},
    ) as client:
        rows = await fetch_council(client, year=year)
    members, _ = extract_members(rows)
    by_ward = {m.ward_id: m for m in members}

    for seat in cmp_st.seats:
        if seat.verdict == "agree":
            continue
        if seat.verdict == "orphan":
            st.skipped.append(
                f"ward {seat.ward_id} ({seat.ward_name}): we hold "
                f"{seat.held!r} and the city lists nobody. That is EITHER a "
                f"retirement OR a publisher omission and this cannot tell "
                f"which — refusing."
            )
            continue

        m = by_ward.get(seat.ward_id)
        if m is None:
            continue
        await _install(db, m, seat, st, dry_run)
    return st


async def _install(db: Database, m: Member, seat: SeatVerdict,
                   st: ApplyStats, dry_run: bool) -> None:
    sid = f"{SOURCE_PREFIX}:{COUNCIL_SLUG}:{slugify(m.person)}"
    existing = await db.fetchrow("SELECT id FROM politicians WHERE source_id = $1", sid)

    if existing is None:
        # ★ Re-key rather than replace — the person keeps their id, socials,
        # offices and websites, and leaves the Open North sweep. Scoped to MB
        # municipal by NAME, because a re-elected member may have changed ward
        # and their old constituency_id is therefore not a safe filter.
        existing = await db.fetchrow(
            """
            SELECT id FROM politicians
             WHERE is_active AND level = 'municipal' AND province_territory = 'MB'
               AND regexp_replace(lower(unaccent(name)), '[^a-z0-9]+', '', 'g')
                 = regexp_replace(lower(unaccent($1)), '[^a-z0-9]+', '', 'g')
             LIMIT 1
            """,
            m.person,
        )
        if existing is not None:
            if not dry_run:
                await db.execute(
                    "UPDATE politicians SET source_id = $2, updated_at = now() "
                    "WHERE id = $1::uuid", existing["id"], sid,
                )
            st.rekeyed += 1

    if existing is not None:
        if not dry_run:
            await db.execute(
                """
                UPDATE politicians
                   SET elected_office = $2, constituency_id = $3,
                       constituency_name = $4, is_active = true, updated_at = now()
                 WHERE id = $1::uuid
                """,
                existing["id"], m.office, seat.constituency_id,
                m.ward_name or "Winnipeg",
            )
        st.updated += 1
        # ⛔ Retire the person this seat is being taken FROM — but only that one
        # person, and only when the seat actually changed hands. Winnipeg is one
        # council of 16; a cohort-wide deactivation here would be 15 collateral
        # retirements to fix one by-election.
        if seat.verdict == "stale" and seat.held:
            await _retire(db, seat, st, dry_run)
        return

    # ⛔ Same duplicate-person guard as BC: a same-named MB municipal row outside
    # the re-key's scope (retired, or detached by a cutover) is a STOP.
    clash = await db.fetchrow(
        """
        SELECT id, is_active, constituency_id FROM politicians
         WHERE level = 'municipal' AND province_territory = 'MB'
           AND regexp_replace(lower(unaccent(name)), '[^a-z0-9]+', '', 'g')
             = regexp_replace(lower(unaccent($1)), '[^a-z0-9]+', '', 'g')
         LIMIT 1
        """,
        m.person,
    )
    if clash is not None:
        st.problems.append(
            f"{m.person} (ward {m.ward_id}): an MB municipal row already exists "
            f"(id={clash['id']}, is_active={clash['is_active']}) that the re-key "
            f"did not find. REFUSING to insert a second row for one person."
        )
        return

    if seat.verdict == "stale" and seat.held:
        await _retire(db, seat, st, dry_run)

    first, last = split_name(m.person)
    if not dry_run:
        import json
        row = await db.fetchrow(
            """
            INSERT INTO politicians (
                name, first_name, last_name, level, province_territory,
                constituency_id, constituency_name, elected_office,
                source_id, is_active, extras)
            VALUES ($1,$2,$3,'municipal','MB',$4,$5,$6,$7,true,$8::jsonb)
            RETURNING id
            """,
            m.person, first, last, seat.constituency_id,
            m.ward_name or "Winnipeg", m.office, sid,
            json.dumps({"city_of_winnipeg": {
                "elected_year": m.year, "ward_id": m.ward_id,
                "web_name": m.web_name or None,
                "source": f"data.winnipeg.ca/resource/{DATASET}.json",
            }}),
        )
        await db.execute(
            """
            INSERT INTO politician_terms (politician_id, office, level,
                province_territory, constituency_id, started_at, source)
            VALUES ($1::uuid, $2, 'municipal', 'MB', $3, $4, $5)
            """,
            row["id"], m.office, seat.constituency_id,
            ELECTION_DATES.get(m.year), f"{SOURCE_PREFIX}:{COUNCIL_SLUG}",
        )
    st.installed += 1


async def _retire(db: Database, seat: SeatVerdict, st: ApplyStats,
                  dry_run: bool) -> None:
    """Three-step retirement: audit row, close the term, then deactivate.

    ⛔ Never a bare `is_active = false`. `politician_changes` is the audit trail
    and an open `politician_terms` row left open makes a departed member look
    like a sitting one to anything that joins through terms.
    """
    row = await db.fetchrow(
        """
        SELECT id, name FROM politicians
         WHERE is_active AND level = 'municipal' AND province_territory = 'MB'
           AND constituency_id = $1
           AND regexp_replace(lower(unaccent(name)), '[^a-z0-9]+', '', 'g')
             = regexp_replace(lower(unaccent($2)), '[^a-z0-9]+', '', 'g')
         LIMIT 1
        """,
        seat.constituency_id, seat.held,
    )
    if row is None:
        return
    if not dry_run:
        # ⓘ Shape follows sk_mlas._detect_sk_retirements: change_type='retired',
        # old_value is JSONB, severity='notable'. There is no `source` or
        # `field_name` column on this table — the provenance goes in old_value.
        import json
        await db.execute(
            """
            INSERT INTO politician_changes
                (politician_id, change_type, old_value, new_value, severity)
            VALUES ($1::uuid, 'retired', $2::jsonb, NULL, 'notable')
            """,
            row["id"],
            json.dumps({
                "name": row["name"],
                "constituency_id": seat.constituency_id,
                "ward_id": seat.ward_id,
                "replaced_by": seat.authority,
                "source": f"data.winnipeg.ca/resource/{DATASET}.json",
            }),
        )
        await db.execute(
            "UPDATE politician_terms SET ended_at = now() "
            "WHERE politician_id = $1::uuid AND ended_at IS NULL", row["id"],
        )
        await db.execute(
            "UPDATE politicians SET is_active = false, updated_at = now() "
            "WHERE id = $1::uuid", row["id"],
        )
    st.retired += 1
