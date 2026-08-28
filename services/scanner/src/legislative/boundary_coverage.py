"""Sentinel: does every jurisdiction's electoral geography still add up?

Four jurisdictions in the 2026 boundary programme had a PERFECT district count
over wrong or incomplete data, so this checks four independent things and treats
them differently.

⛔ Why `active_politicians == seat_count` is NOT one of them
-----------------------------------------------------------
It was the obvious assertion and it is wrong. Ontario sits at 122 members for
124 seats today, and both gaps are correct — Scarborough Southwest and
York—Simcoe are genuinely vacant, with a by-election called for 2026-09-03.
Vacancies are normal. An alarm that fires on correct data gets muted, and a muted
alarm is worse than no alarm.

So the asymmetry is deliberate:
  • `actives > seats`  → BREACH. More members than seats means duplicate roster
    rows, which is how British Columbia served two MLAs for five districts.
  • `actives < seats`  → REPORTED as a vacancy count, never a breach.

★ Why the fingerprint exists, and why total area is not enough
--------------------------------------------------------------
Total area is INVARIANT under redistribution — Yukon's superseded 19-district
map sums to 485,224 km² against the authoritative 21-district map's 485,298, a
0.015% difference, because it is the same territory divided differently. A
total-area alarm cannot see a redraw at all; it only catches projection errors
and extent changes.

The fingerprint is an md5 over the sorted per-district areas, so ANY change to
the internal division changes it even when the total does not. Newfoundland is
why this half is not optional: its next commission is due this calendar year and
the statute pins the seat count at 40, so neither a count check nor an area check
could see that landing.

⚠ The fingerprint fires on any legitimate re-load too. That is intended — it is a
"the geometry changed, confirm you meant it" alarm, and the fix is to update
BASELINES in the same commit as the load.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..db import Database
from .boundary_loader import slugify

# Number of federal electoral districts. ⚠ NOT read from
# `jurisdiction_sources.seats`, which records 440 for 'federal' — that figure
# counts something other than House seats and would certify a 97-district gap as
# correct.
FEDERAL_SEATS = 343

# Per-district area tolerance for the fingerprint's companion total check.
AREA_TOLERANCE = 0.01  # 1%

# Snapshot taken 2026-08-19, after ALL 13 provinces/territories and the
# federal House were moved onto their authoritative sources.
# `(district_count, total_area_km2)`.
#
# ⓘ Several of these legitimately exceed the jurisdiction's land-plus-
# freshwater area because the agency's own districts extend over marine
# waters — NT is 1.61M against 1.35M because Nunakput reaches into the
# Beaufort Sea, and NU and NS are the same shape. Do not 'correct' them
# toward StatCan land areas; the number recorded here is what the authority
# publishes, which is the thing drift should be measured against.
# ⚠ Update these in the same commit as any deliberate re-load.
BASELINES: dict[tuple[str, str], tuple[int, float]] = {
    ("federal", "CA"): (343, 14_159_247.2),
    ("provincial", "AB"): (87, 663_109.2),
    ("provincial", "BC"): (93, 1_039_594.4),
    ("provincial", "MB"): (57, 649_948.3),
    ("provincial", "NB"): (49, 77_794.9),
    ("provincial", "NL"): (40, 405_904.5),
    ("provincial", "NS"): (56, 73_706.9),
    ("provincial", "NT"): (19, 1_609_305.1),
    ("provincial", "NU"): (22, 4_932_875.1),
    ("provincial", "ON"): (124, 1_048_378.7),
    ("provincial", "PE"): (27, 5_641.2),
    ("provincial", "QC"): (125, 1_696_239.5),
    ("provincial", "SK"): (61, 652_365.2),
    ("provincial", "YT"): (21, 485_297.9),
}


@dataclass
class CoverageRow:
    jurisdiction: str
    level: str
    seats: Optional[int]
    districts: int
    actives: int
    attached: int
    orphans: int
    vacancies: int
    total_area: float
    # ⚠ Reported, never a breach. Open North ingestion was retired 2026-08-19
    # (migration 0087) because the mirror was actively corrupting authoritative
    # data. Roughly 840 federal and provincial rows still SOURCE from it and now
    # have no refresh path until a per-jurisdiction replacement is built. A
    # frozen roster is wrong slowly and visibly; the mirror was wrong quickly and
    # silently. This surfaces the freeze so it is a known cost rather than a
    # surprise — making it a breach would just mean 12 red lines every week until
    # the last replacement ships.
    roster_frozen: int = 0
    roster_stale_days: Optional[int] = None
    breaches: list[str] = field(default_factory=list)

    @property
    def breached(self) -> bool:
        return bool(self.breaches)


async def check_boundary_coverage(
    db: Database, check_area: bool = True,
) -> list[CoverageRow]:
    """One row per jurisdiction; `breaches` non-empty means something is wrong."""
    seats_by_ju = {
        r["jurisdiction"]: r["seats"]
        for r in await db.fetch(
            "SELECT jurisdiction, seats FROM jurisdiction_sources "
            "WHERE seats IS NOT NULL"
        )
    }

    rows = await db.fetch(
        """
        WITH bnd AS (
          -- ⚠ Federal rows carry a PER-ROW province (derived from FED_NUM's
          -- SGC prefix), so grouping on province_territory splits the House
          -- into 13 buckets, each compared against the national 343. Collapse
          -- federal to 'CA' here exactly as the roster side does, or the two
          -- halves never join.
          SELECT level,
                 CASE WHEN level = 'federal' THEN 'CA'
                      ELSE COALESCE(province_territory, 'CA') END AS ju,
                 count(*) AS districts,
                 COALESCE(sum(area_sqkm), 0) AS total_area,
                 -- ★ Sorted per-district areas, so a redistribution that holds
                 -- the count AND the total still changes the digest.
                 md5(string_agg(round(area_sqkm::numeric, 1)::text, ','
                                ORDER BY round(area_sqkm::numeric, 1),
                                         constituency_id)) AS fingerprint
            FROM constituency_boundaries
           WHERE level IN ('provincial', 'federal')
             AND effective_from <= CURRENT_DATE
             AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
           GROUP BY 1, 2
        ), ros AS (
          SELECT level,
                 CASE WHEN level = 'federal' THEN 'CA'
                      ELSE province_territory END AS ju,
                 count(*) AS actives,
                 count(*) FILTER (WHERE constituency_id IS NOT NULL) AS attached,
                 -- ⛔ The live-window predicate is load-bearing. Without it
                 -- this asks "was this ever a district?", not "is it one
                 -- today?" — and a superseded generation is END-DATED, never
                 -- deleted, so EXISTS stays true forever and the check passes
                 -- for all time. That is the same fail-open shape that blinded
                 -- duplicate-generation, duplicate-geometry, wrong-tier and
                 -- displaced in August; this was the fifth instance, found
                 -- 2026-08-27 while checking what Quebec's flip would do. It
                 -- would have reported 0 orphans while six MNAs detached.
                 count(*) FILTER (
                   WHERE constituency_id IS NOT NULL
                     AND NOT EXISTS (
                       SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = politicians.constituency_id
                          AND b.effective_from <= CURRENT_DATE
                          AND (b.effective_to IS NULL
                               OR b.effective_to >= CURRENT_DATE))
                 ) AS orphans
            FROM politicians
           WHERE is_active
             AND level IN ('provincial', 'federal')
             -- Senators hold no district; counting them would put federal
             -- permanently 100 over its seat count.
             AND (level <> 'federal' OR elected_office = 'MP')
           GROUP BY 1, 2
        )
        SELECT COALESCE(b.level, r.level) AS level,
               COALESCE(b.ju, r.ju) AS ju,
               COALESCE(b.districts, 0) AS districts,
               COALESCE(b.total_area, 0) AS total_area,
               b.fingerprint,
               COALESCE(r.actives, 0) AS actives,
               COALESCE(r.attached, 0) AS attached,
               COALESCE(r.orphans, 0) AS orphans
          FROM bnd b
          FULL OUTER JOIN ros r ON r.level = b.level AND r.ju = b.ju
         ORDER BY 1, 2
        """
    )

    # How many sitting members still source from the retired Open North mirror,
    # and how long since anything touched them.
    frozen_by: dict[tuple[str, str], tuple[int, Optional[int]]] = {}
    for f in await db.fetch(
        """
        SELECT level,
               CASE WHEN level = 'federal' THEN 'CA'
                    ELSE province_territory END AS ju,
               count(*) AS n,
               (now()::date - max(updated_at)::date) AS stale_days
          FROM politicians
         WHERE is_active AND level IN ('federal', 'provincial')
           AND source_id LIKE 'opennorth:%'
         GROUP BY 1, 2
        """
    ):
        frozen_by[(f["level"], f["ju"])] = (f["n"], f["stale_days"])

    out: list[CoverageRow] = []
    for r in rows:
        level, ju = r["level"], r["ju"]
        seats = FEDERAL_SEATS if level == "federal" else seats_by_ju.get(ju)
        districts = r["districts"]
        actives, attached = r["actives"], r["attached"]
        orphans = r["orphans"]
        breaches: list[str] = []

        if seats is None:
            breaches.append("no seat count recorded in jurisdiction_sources")
        else:
            if districts != seats:
                breaches.append(f"{districts} districts vs {seats} seats")
            # ⛔ Strictly greater. See the module docstring: a shortfall is a
            # vacancy, an excess is a duplicate.
            if actives > seats:
                breaches.append(
                    f"{actives} sitting members for {seats} seats "
                    f"— duplicate roster rows"
                )
        if attached < actives:
            breaches.append(f"{actives - attached} sitting members with no district")
        if orphans:
            breaches.append(f"{orphans} members point at a non-existent boundary")

        base = BASELINES.get((level, ju))
        if check_area and base is not None:
            exp_n, exp_area = base
            if exp_area > 0 and r["total_area"] > 0:
                drift = abs(r["total_area"] - exp_area) / exp_area
                if drift > AREA_TOLERANCE:
                    breaches.append(
                        f"area {r['total_area']:,.0f} km² is {drift:.1%} from the "
                        f"recorded {exp_area:,.0f} — geometry or projection changed"
                    )

        frozen = frozen_by.get((level, ju), (0, None))
        out.append(CoverageRow(
            jurisdiction=ju, level=level, seats=seats, districts=districts,
            actives=actives, attached=attached, orphans=orphans,
            vacancies=max(0, (seats or 0) - actives) if seats else 0,
            total_area=float(r["total_area"] or 0),
            roster_frozen=frozen[0], roster_stale_days=frozen[1],
            breaches=breaches,
        ))
    return out


# ── Municipal ────────────────────────────────────────────────────────────────
#
# ⛔ `districts == seats` HAS NO MUNICIPAL ANALOGUE and must not be attempted.
# A council is not one-seat-one-polygon:
#
#   Fort Erie   6 ward polygons + 1 city polygon for 7 seats
#   Vancouver   1 polygon for 18 seats — at-large is the BC statutory default,
#               and that is complete, not broken
#   Montréal    63 polygons for 65 seats, across three nested tiers
#   Niagara     32 seats spread over 13 polygons belonging to OTHER councils
#
# What does hold is a per-SEAT rule, in two clauses:
#
#   1. Every sitting municipal politician with a constituency_id resolves to a
#      live boundary row. (Fails today on exactly 2 — Fort Erie wards 2 and 4,
#      the only orphans in the table, lost to a silent fetch failure in 2026-04.)
#   2. A politician whose office is unambiguously CITY-WIDE sits on a
#      `municipality` polygon, and a borough mayor sits on a `borough` polygon.
#
# ⚠ Clause 2 deliberately says nothing about `Councillor` / `Conseiller` /
# `Regional Councillor`. Those are legitimately either tier — ward-elected in
# most of Ontario and Québec, at-large across BC and in a dozen other councils —
# so asserting on them would fire on correct data. Only the offices that CANNOT
# be ward-elected are checked.

# Offices that are city-wide by definition -> must sit on a `municipality` row.
CITY_WIDE_OFFICES = (
    "Mayor", "Maire", "Lord Mayor", "Maire de la Ville de Montréal",
    "Deputy Mayor", "Councillor at Large", "Commissioner",
    "Regional Chair", "Chair", "Warden", "Deputy Warden",
)
# Offices that are borough-level by definition -> must sit on a `borough` row.
BOROUGH_OFFICES = ("Maire d'arrondissement",)


@dataclass
class MunicipalProblem:
    kind: str
    detail: str
    count: int
    # ⚠ Reported, never failed. Same ruling as a roster shortfall being a
    # VACANCY rather than a breach (see the module docstring): a gap in what we
    # have COLLECTED is not a corruption of what we hold. Failing the daily job
    # on a known, worked-on backlog trains the operator to ignore it, and an
    # ignored sentinel is the condition that let the 2026-08-23 regression run
    # for five days.
    advisory: bool = False


async def check_municipal_integrity(db: Database) -> list[MunicipalProblem]:
    """Per-seat municipal checks. Empty list means clean."""
    out: list[MunicipalProblem] = []

    rows = await db.fetch(
        """
        SELECT p.name, p.elected_office, p.constituency_id
          FROM politicians p
         WHERE p.is_active AND p.level = 'municipal'
           AND p.constituency_id IS NOT NULL
           -- ⛔ Live window, same reason as the provincial/federal orphan
           -- check above: end-dated rows are still rows. Without this, a
           -- municipal cutover that retires a generation detaches the whole
           -- council and this check reports nothing.
           AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                            WHERE b.constituency_id = p.constituency_id
                              AND b.effective_from <= CURRENT_DATE
                              AND (b.effective_to IS NULL
                                   OR b.effective_to >= CURRENT_DATE))
         ORDER BY p.constituency_id
        """
    )
    if rows:
        out.append(MunicipalProblem(
            "orphaned",
            "sitting members pointing at a boundary that does not exist: "
            + ", ".join(f"{r['name']} ({r['constituency_id']})" for r in rows[:6]),
            len(rows),
        ))

    rows = await db.fetch(
        """
        SELECT p.elected_office, b.boundary_kind, count(*) AS n
          FROM politicians p
          JOIN constituency_boundaries b ON b.constituency_id = p.constituency_id
         WHERE p.is_active AND p.level = 'municipal'
           AND ( (p.elected_office = ANY($1::text[])
                  AND b.boundary_kind IS DISTINCT FROM 'municipality')
              OR (p.elected_office = ANY($2::text[])
                  AND b.boundary_kind IS DISTINCT FROM 'borough') )
         GROUP BY 1, 2 ORDER BY 3 DESC
        """,
        list(CITY_WIDE_OFFICES), list(BOROUGH_OFFICES),
    )
    if rows:
        out.append(MunicipalProblem(
            "wrong-tier",
            "; ".join(
                f"{r['elected_office']} on a "
                f"{r['boundary_kind'] or 'NULL'} polygon ×{r['n']}"
                for r in rows[:6]
            ),
            sum(r["n"] for r in rows),
        ))

    # ── Slug-function divergence ────────────────────────────────────────
    # ⛔ TWO IMPLEMENTATIONS OF ONE FUNCTION, AND THEY MUST NOT DRIFT.
    # `boundary_loader.slugify` (Python) mints every `constituency_id`;
    # `cpd_slugify` (SQL, migration 0080) is what the roster attach joins on.
    # `qc_municipal_roster.slugify` documents itself as matching the former. If
    # any of the three disagree on a name, ids are minted one way and looked up
    # another, and the symptom is not an error — it is a member who quietly fails
    # to attach.
    #
    # ★ This is not hypothetical. Python's NFKD does not touch LIGATURES — `œ` is
    # one character, not an accented `o` — while Postgres `unaccent()` expands
    # them. Montréal's `Champlain–L'Île-des-Sœurs` was minted as
    # `champlain-lile-des-s-urs` (the `œ` became a hyphen mid-word) while the
    # roster looked for `champlain-lile-des-soeurs`. Three councillors did not
    # attach and nothing reported a problem.
    #
    # Cheap: ~1,900 names, one round trip.
    rows = await db.fetch(
        """
        SELECT constituency_id, name, authority, cpd_slugify(name) AS sql_slug
          FROM constituency_boundaries WHERE name IS NOT NULL
        """
    )
    drift = [r for r in rows if slugify(r["name"]) != r["sql_slug"]]

    # ⚠ And the second half: an id MINTED BY AN EARLIER slugify keeps whatever
    # that version produced. Fixing the function does not retroactively fix the
    # ids it wrote, so `champlain-lile-des-s-urs` survives a corrected slugify
    # and still fails to match. Only checked for loader-minted rows (`authority`
    # set) — mirror rows legitimately carry ids we did not derive.
    # ⚠ Skip ids minted from `slug_field` rather than from the name — federal
    # districts key on Elections Canada's FED_NUM
    # (`federal-electoral-districts/10001`) and CSD polygons on the StatCan code,
    # and neither is meant to equal the name slug. Without this exclusion the
    # check reports 463 "failures", all of them correct rows, which is exactly the
    # muted-alarm problem this module's header warns about.
    stale = [
        r for r in rows
        if r["authority"]
        and not r["constituency_id"].split("/", 1)[-1].isdigit()
        and r["constituency_id"].split("/", 1)[-1] != slugify(r["name"])
    ]
    if stale:
        out.append(MunicipalProblem(
            "stale-slug-id",
            "loader-minted ids that no longer match slugify(name) — minted by an "
            "earlier version of the function and never re-keyed: "
            + ", ".join(
                f"{r['constituency_id']} (name {r['name']!r} -> {slugify(r['name'])!r})"
                for r in stale[:4]
            ),
            len(stale),
        ))

    if drift:
        out.append(MunicipalProblem(
            "slug-divergence",
            "cpd_slugify (SQL) and boundary_loader.slugify (Python) disagree — "
            "ids are minted one way and looked up the other: "
            + ", ".join(
                f"{r['name']!r} py={slugify(r['name'])!r} sql={r['sql_slug']!r}"
                for r in drift[:4]
            ),
            len(drift),
        ))

    # ── Live duplicate generations ──────────────────────────────────────
    # ⛔ One constituency_id live under two `boundaries_version`s. Both satisfy
    # the effective-date window, so every point-in-polygon over that area returns
    # the district TWICE — and because the ids are identical, the roster still
    # resolves and nothing else looks wrong.
    #
    # ★ This is how a load and a cutover come apart. The upsert key is
    # (constituency_id, boundaries_version), so loading a new generation over an
    # existing one INSERTS beside it rather than replacing it; retiring the old
    # one is the migration's job, deliberately, because only a migration knows a
    # generation is superseded. Miss that step and the result is silent
    # double-counting — the 0084 defect, found by hand then and worth never
    # finding by hand again.
    #
    # ⚠ Scans every level, not just municipal: the failure mode is a property of
    # the versioning scheme, not of municipal data.
    rows = await db.fetch(
        """
        WITH live AS (
          SELECT level, source_set, constituency_id, boundaries_version
            FROM constituency_boundaries
           WHERE effective_from <= CURRENT_DATE
             AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
        )
        SELECT level, source_set, count(*) AS ids,
               string_agg(DISTINCT boundaries_version, ' + '
                          ORDER BY boundaries_version) AS versions
          FROM (SELECT level, source_set, constituency_id, boundaries_version
                  FROM live) l
         GROUP BY level, source_set, constituency_id
        HAVING count(*) > 1
        """
    )
    if rows:
        by_set: dict = {}
        for r in rows:
            key = (r["source_set"], r["versions"])
            by_set[key] = by_set.get(key, 0) + 1
        out.append(MunicipalProblem(
            "duplicate-generation",
            "constituency_ids live under two generations at once — a cutover "
            "migration must retire the superseded one: "
            + ", ".join(f"{ss} ({v}) ×{n}" for (ss, v), n in
                        sorted(by_set.items(), key=lambda t: -t[1])[:6]),
            len(rows),
        ))

    # ── Council cohesion ────────────────────────────────────────────────
    # ⛔ A member must sit on a polygon that TOUCHES one of their colleagues'.
    # Municipal district slugs are nowhere near unique — `district-1` exists in
    # 13 Québec sets, `plateau` is both Gatineau's and Québec City's — so an
    # attach that joins on the slug without scoping to the municipality is
    # ambiguous, and Postgres resolves ambiguity by plan choice, not geography.
    # It put Gatineau's councillor for Plateau on Québec City's Plateau, 400 km
    # away (repaired in 0089).
    #
    # ★ Deliberately GEOMETRIC rather than a source_set/slug convention check:
    # the convention is what was wrong, so testing it against itself proves
    # nothing. Contiguity is a fact about the world that no naming scheme can
    # fake.
    #
    # ⚠ Only for councils holding more than one DISTINCT polygon. An at-large
    # council — Burnaby, Abbotsford, Coquitlam — puts its whole membership on one
    # CSD polygon, which is correct and has no colleague polygon to touch.
    rows = await db.fetch(
        """
        WITH m AS (
          -- ⚠ ST_MakeValid at read time, deliberately. This check once
          -- aborted the ENTIRE sentinel with `GEOSIntersects:
          -- TopologyException` because 28 QC polygons were self-intersecting,
          -- so nothing downstream of it ran and no summary line was printed
          -- for five days. A validity defect is reported by the
          -- `invalid-geometry` class below, never by taking the run down.
          SELECT p.name, split_part(p.source_id, ':', 2) AS council,
                 b.constituency_id,
                 ST_CollectionExtract(ST_MakeValid(b.boundary), 3) AS boundary
            FROM politicians p
            JOIN constituency_boundaries b ON b.constituency_id = p.constituency_id
           WHERE p.is_active AND p.level = 'municipal'
        )
        SELECT a.council, a.name, a.constituency_id
          FROM m a
         WHERE (SELECT count(DISTINCT x.constituency_id)
                  FROM m x WHERE x.council = a.council) > 1
           AND NOT EXISTS (
                 SELECT 1 FROM m o
                  WHERE o.council = a.council
                    AND o.constituency_id <> a.constituency_id
                    AND ST_Intersects(o.boundary, a.boundary))
         ORDER BY a.council, a.name
        """
    )
    if rows:
        out.append(MunicipalProblem(
            "displaced",
            "sitting on a polygon disjoint from every colleague's, i.e. almost "
            "certainly another municipality's district: "
            + ", ".join(
                f"{r['name']} ({r['council']} -> {r['constituency_id']})"
                for r in rows[:6]
            ),
            len(rows),
        ))

    # ⚠ Near-identical overlapping polygons make a smallest-first lookup
    # planner-dependent — the Peel defect, fixed in 0083. Cheap to re-check.
    # ⛔ `boundary_kind = 'district'` on BOTH sides is what made this check
    # blind to the 2026-08-23 mirror regression. A re-ingested Open North row
    # carries `boundary_kind IS NULL` — it has no tier at all — so Toronto's 25
    # wards sat live TWICE at 100% overlap and this predicate excluded every
    # pair. Treat NULL as a district: an untiered row is exactly the kind that
    # duplicates, so excluding it inverts the check's purpose.
    #
    # ⚠ Also now scoped to LIVE rows. Without it, removing the kind filter would
    # count deliberately retired generations (QC's end-dated 2017 map) as
    # duplicates — a retired generation overlapping its successor is the system
    # working, not a defect.
    dupes = await db.fetchval(
        """
        WITH live AS (
          SELECT constituency_id,
                 ST_CollectionExtract(ST_MakeValid(boundary), 3) AS g
            FROM constituency_boundaries
           WHERE level = 'municipal'
             AND (boundary_kind = 'district' OR boundary_kind IS NULL)
             AND effective_from <= CURRENT_DATE
             AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
        )
        SELECT count(*) FROM live a
          JOIN live b
            ON b.constituency_id > a.constituency_id
           AND ST_Intersects(a.g, b.g)
           AND ST_Area(ST_Intersection(a.g, b.g))
                 / least(ST_Area(a.g), ST_Area(b.g)) >= 0.98
           AND ST_Area(a.g) / ST_Area(b.g) BETWEEN 0.98 AND 1.02
        """,
        timeout=300,
    )
    if dupes:
        out.append(MunicipalProblem(
            "duplicate-geometry",
            "pairs of near-identical municipal district polygons — a "
            "smallest-first lookup cannot choose deterministically between them",
            int(dupes),
        ))

    # ── Invalid geometry ────────────────────────────────────────────────
    # ⚠ The checks above now repair at read time so a self-intersection cannot
    # abort the run. That makes it this check's job to say so out loud —
    # otherwise the repair silently masks a defect in the stored data, and a
    # polygon PostGIS has to fix on every read is a polygon that will break the
    # next thing that touches it raw.
    rows = await db.fetch(
        """
        SELECT level, source_set, count(*) AS n
          FROM constituency_boundaries
         WHERE NOT ST_IsValid(boundary)
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY level, source_set
         ORDER BY n DESC
        """
    )
    if rows:
        out.append(MunicipalProblem(
            "invalid-geometry",
            "live polygons fail ST_IsValid and are being repaired on every "
            "read — fix them in the table: "
            + ", ".join(f"{r['source_set']} ×{r['n']}" for r in rows[:6]),
            sum(r["n"] for r in rows),
        ))

    # ── Open North mirror signature ─────────────────────────────────────
    # ⛔ THE 2026-08-23 REGRESSION, CAUGHT DIRECTLY.
    #
    # A single Open North run re-created 1,926 rows and reverted twelve applied
    # cutover migrations. Every existing check missed it: `duplicate-generation`
    # groups by source_set and the cutovers deliberately RENAMED the set;
    # `duplicate-geometry` required a boundary_kind the mirror rows do not
    # carry; `wrong-tier` cannot fire on NULL. Three checks, all failing open.
    #
    # ★ So test the signature itself rather than its consequences. The loader
    # produces neither `boundaries_version='current'` nor
    # `effective_from='2023-01-01'` — only the mirror ever did. At federal and
    # provincial level all 14 jurisdictions are on authoritative sources, so
    # ANY such row is a defect. Municipal keeps the source_set qualifier: ~782
    # legitimately un-replaced mirror rows are the only data that exists for
    # those places, and flagging them every day would train the operator to
    # ignore this line.
    rows = await db.fetch(
        """
        SELECT b.level, b.source_set, count(*) AS n
          FROM constituency_boundaries b
         WHERE b.boundaries_version = 'current'
           AND b.effective_from = DATE '2023-01-01'
           -- ⚠ `boundary_kind IS NULL` is not decoration, it is the whole
           -- discriminator. The mirror never writes a tier; every deliberately
           -- kept row has one. Without this clause the check reports the ten
           -- `census-subdivisions/*` mayoral polygons 0093 preserved inside
           -- ward sets, Montréal's 18 boroughs, Québec's 5 and Sainte-Anne's
           -- 5 held districts — 38 rows that are correct and must stay. Found
           -- the hard way while writing 0101, whose first draft would have
           -- deleted all 38.
           AND b.boundary_kind IS NULL
           AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
           AND (b.level <> 'municipal'
                OR EXISTS (SELECT 1 FROM constituency_boundaries n
                            WHERE n.source_set = b.source_set
                              AND n.boundaries_version <> 'current'))
         GROUP BY b.level, b.source_set
         ORDER BY n DESC
        """
    )
    if rows:
        out.append(MunicipalProblem(
            "mirror-signature",
            "Open North mirror rows are live in a jurisdiction already moved "
            "onto an authoritative source — an ingest has reverted a cutover: "
            + ", ".join(f"{r['source_set']} ×{r['n']}" for r in rows[:6]),
            sum(r["n"] for r in rows),
        ))

    # ── Untiered rows under a sitting official ──────────────────────────
    # ⚠ `wrong-tier` compares an office class against `boundary_kind`. NULL is
    # neither a match nor a mismatch, so it passes — which is how 257 sitting
    # municipal officials came to sit on rows with no tier at all and nothing
    # said a word. Absence of a tier is its own defect, not a free pass.
    rows = await db.fetch(
        """
        SELECT split_part(p.source_id, ':', 2) AS council, count(*) AS n
          FROM politicians p
          JOIN constituency_boundaries b
            ON b.constituency_id = p.constituency_id
         WHERE p.is_active AND p.level = 'municipal'
           AND b.boundary_kind IS NULL
           AND b.effective_from <= CURRENT_DATE
           AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
         GROUP BY 1 ORDER BY n DESC
        """
    )
    if rows:
        out.append(MunicipalProblem(
            "untiered",
            "sitting officials on boundary rows with no boundary_kind, which "
            "every tier check silently passes: "
            + ", ".join(f"{r['council']} ×{r['n']}" for r in rows[:6]),
            sum(r["n"] for r in rows),
        ))

    # ── One district, two live generations, DIFFERENT set names ─────────
    # ⛔ The blind spot in `duplicate-generation` above. It groups by
    # (level, source_set, constituency_id) — but a cutover's whole job is to
    # strip the generation out of the set name, so the superseded row and its
    # replacement end up under two DIFFERENT sets and never group together:
    #
    #   current                    federal-electoral-districts-2023-representation-order/10001
    #   2023-representation-order  federal-electoral-districts/10001
    #
    # ★ Key on the district identity — the id tail — scoped by jurisdiction.
    # ⚠ Federal/provincial only. Municipal tails are nowhere near unique
    # (`district-1` exists in 13 Québec sets), so the same key there would
    # report a hundred non-findings; municipal duplication is caught
    # geometrically by `duplicate-geometry` instead.
    rows = await db.fetch(
        """
        SELECT level, province_territory,
               split_part(constituency_id, '/', 2) AS district,
               string_agg(DISTINCT source_set, ' + ' ORDER BY source_set) AS sets
          FROM constituency_boundaries
         WHERE level IN ('federal', 'provincial')
           AND effective_from <= CURRENT_DATE
           AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
         GROUP BY 1, 2, 3
        HAVING count(DISTINCT source_set) > 1
        """
    )
    if rows:
        by_sets: dict = {}
        for r in rows:
            by_sets[r["sets"]] = by_sets.get(r["sets"], 0) + 1
        out.append(MunicipalProblem(
            "duplicate-district",
            "one district live under two source_sets at once — a point-in-"
            "polygon returns it twice: "
            + ", ".join(f"{k} ×{n}" for k, n in
                        sorted(by_sets.items(), key=lambda t: -t[1])[:4]),
            len(rows),
        ))

    # ── detached-council ─────────────────────────────────────────────────
    #
    # ★ WHY THIS EXISTS. On 2026-08-28, 129 sitting Québec municipal officials
    # held constituency_id IS NULL. 92 of them were attachable the whole time:
    # the cutover migrations renamed and reloaded the polygon sets, and nothing
    # re-ran the roster matcher afterwards. Re-running
    # `ingest-qc-municipal-roster` linked all 92 with no new data. The geometry
    # was right, the roster was right, and the edge between them was missing —
    # a state no existing check could see, because `orphaned` only fires on a
    # constituency_id that points at NOTHING, and these pointed at nothing at
    # all.
    #
    # ⚠ The predicate is deliberately RELATIVE, not absolute. A NULL
    # constituency_id is normal and correct for an at-large council — Vancouver
    # elects 18 councillors city-wide, which is the BC statutory default, and
    # asserting on NULL alone would fire on every one of them forever. What is
    # NOT normal is a council where some members attach and others do not:
    # that means the set resolves, the join works, and these specific people
    # fell through it.
    # ⛔ Two different defects wear the same symptom and must not share a
    # severity. A member with no district is either
    #
    #   FIXABLE   the polygon exists, in a set this council already uses, and
    #             nothing linked them — a cutover severed the edge. Costs one
    #             `reattach-municipal-roster` run. This is a BREACH.
    #   MISSING   the polygon does not exist. No amount of re-running helps;
    #             somebody has to go and get the map. This is a coverage gap,
    #             reported and not failed.
    #
    # Collapsing them makes the sentinel permanently red on a known backlog,
    # which is worse than silence because it looks like noise.
    rows = await db.fetch(
        """
        WITH detached AS (
          -- Resolved through constituency_name_alias (0120) so a spelling
          -- disagreement between the roster and the boundary publisher is not
          -- reported as missing geometry. Montréal's three were exactly that.
          SELECT split_part(p.source_id, ':', 2) AS council,
                 p.id,
                 COALESCE(a.target_slug,
                          cpd_slugify(p.constituency_name)) AS want
            FROM politicians p
            LEFT JOIN constituency_name_alias a
                   ON a.council = split_part(p.source_id, ':', 2)
                  AND a.alias_slug = cpd_slugify(p.constituency_name)
           WHERE p.is_active AND p.level = 'municipal'
             AND p.source_id LIKE '%:%:%'
             AND p.constituency_id IS NULL
             AND p.constituency_name IS NOT NULL
        ), used AS (
          -- The sets this council demonstrably belongs to, evidenced by its
          -- OWN attached members. No name or geometry heuristic needed: if a
          -- colleague resolves into that set, so should they.
          SELECT DISTINCT split_part(p.source_id, ':', 2) AS council,
                 b.source_set
            FROM politicians p
            JOIN constituency_boundaries b
              ON b.constituency_id = p.constituency_id
           WHERE p.is_active AND p.level = 'municipal'
             AND p.source_id LIKE '%:%:%'
        )
        SELECT d.council,
               count(*) AS n,
               count(*) FILTER (WHERE EXISTS (
                 SELECT 1 FROM constituency_boundaries b
                  JOIN used u ON u.source_set = b.source_set
                             AND u.council = d.council
                  WHERE split_part(b.constituency_id, '/', 2) = d.want
                    -- ⚠ Districts only, and this matters. Without it, a
                    -- councillor whose constituency_name is just the city
                    -- name matches the municipality OUTLINE and is scored
                    -- fixable — but `reattach-municipal-roster` will not
                    -- attach a ward councillor to a whole-city polygon, so
                    -- the sentinel would demand a fix no tool performs.
                    -- Sainte-Anne-de-Bellevue's six posts against five
                    -- districts is exactly that shape.
                    AND (b.boundary_kind = 'district'
                         OR b.boundary_kind IS NULL)
                    AND b.effective_from <= CURRENT_DATE
                    AND (b.effective_to IS NULL
                         OR b.effective_to >= CURRENT_DATE)
               )) AS fixable
          FROM detached d
         GROUP BY 1
         ORDER BY 2 DESC
        """
    )
    fixable = [r for r in rows if r["fixable"]]
    missing = [r for r in rows if r["n"] > r["fixable"]]
    if fixable:
        out.append(MunicipalProblem(
            "detached-council",
            "sitting members whose district polygon EXISTS in a set their own "
            "council already uses, but is not linked — a cutover severed the "
            "edge. Fix with `reattach-municipal-roster`: "
            + ", ".join(f"{r['council']} {r['fixable']}" for r in fixable[:6]),
            sum(r["fixable"] for r in fixable),
        ))
    if missing:
        out.append(MunicipalProblem(
            "missing-district-polygon",
            "sitting members whose district has no polygon at all — a map to "
            "go and get, not a link to repair: "
            + ", ".join(f"{r['council']} {r['n'] - r['fixable']}"
                        for r in missing[:8]),
            sum(r["n"] - r["fixable"] for r in missing),
            advisory=True,
        ))

    return out


# ── Municipal roster freeze ──────────────────────────────────────────────────


@dataclass
class FrozenMunicipalRoster:
    province: str
    total: int
    frozen: int
    stale_days: Optional[int]

    def describe(self) -> str:
        pct = (100.0 * self.frozen / self.total) if self.total else 0.0
        # ⚠ "touch", not "verified". updated_at is bumped by any write,
        # cosmetic ones included, so it is a floor on staleness and never
        # evidence of currency. politician_changes.detected_at only advances on
        # a real delta and is the better proxy when one is needed.
        age = f", oldest write {self.stale_days}d ago" if self.stale_days else ""
        return (f"{self.province}: {self.frozen}/{self.total} sitting municipal "
                f"officials ({pct:.0f}%) still source from the retired Open "
                f"North mirror{age}")


async def check_municipal_roster_freeze(db: Database) -> list[FrozenMunicipalRoster]:
    """How much of the municipal roster is frozen, per province.

    ★ WHY THIS IS SEPARATE FROM `roster_frozen`. The federal/provincial frozen
    count in check_boundary_coverage() filters `level IN ('federal',
    'provincial')` and so has never counted a single municipal official. It
    reported 1057 while another ~912 sat frozen underneath it, unmentioned.
    A freshness number that silently excludes the least-fresh half of the
    dataset is worse than no number.

    ⚠ Advisory by construction. A frozen roster is not a corruption — the rows
    are the last thing the mirror said and they are still internally
    consistent. It is a CURRENCY claim the dataset should not be making, and
    the fix is a replacement ingester per province, not a repair. Québec is the
    only province that has one (MAMH's election result, source prefix
    `mamh-qc:`); everywhere else is 100% frozen.
    """
    return [
        FrozenMunicipalRoster(
            province=r["pt"], total=r["total"], frozen=r["frozen"],
            stale_days=r["stale_days"],
        )
        for r in await db.fetch(
            """
            SELECT COALESCE(province_territory, '??') AS pt,
                   count(*) AS total,
                   count(*) FILTER (WHERE source_id LIKE 'opennorth:%') AS frozen,
                   (now()::date - min(updated_at)::date) AS stale_days
              FROM politicians
             WHERE is_active AND level = 'municipal'
             GROUP BY 1
            HAVING count(*) FILTER (WHERE source_id LIKE 'opennorth:%') > 0
             ORDER BY 3 DESC
            """
        )
    ]


# ── Pending flips ────────────────────────────────────────────────────────────

PENDING_FLIP_HORIZON_DAYS = 60


@dataclass
class PendingFlip:
    level: str
    jurisdiction: str
    source_set: str
    version: str
    starts: date
    incoming: int
    outgoing: int
    orphans: int
    seats: Optional[int]

    def describe(self) -> str:
        delta = self.incoming - self.outgoing
        sign = f"+{delta}" if delta > 0 else str(delta)
        bits = [
            f"{self.starts} {self.level}/{self.jurisdiction} {self.source_set}"
            f" -> v{self.version}: {self.outgoing} live districts become "
            f"{self.incoming} ({sign})"
        ]
        if self.orphans:
            bits.append(f"⛔ {self.orphans} sitting members would detach")
        if self.seats is not None and self.incoming != self.seats:
            bits.append(
                f"⚠ jurisdiction_sources.seats is {self.seats} and will not "
                f"agree — update it in the same change that ingests the "
                f"election result"
            )
        return " | ".join(bits)


async def check_pending_flips(
    db: Database, horizon_days: int = PENDING_FLIP_HORIZON_DAYS
) -> list[PendingFlip]:
    """Generations that go live soon, and what they will do when they do.

    ★ Every boundary regression this programme has hit was visible in advance
    and nobody was looking. A flip is not an event that happens to us — it is
    a dated row already sitting in the table. This turns each one into a task
    with a deadline instead of a Monday-morning surprise.

    Reports rather than breaches: a pending flip is normal. It is the
    *contents* of the report — orphaned members, a seat count that will stop
    agreeing — that need acting on before the date arrives.
    """
    rows = await db.fetch(
        """
        WITH upcoming AS (
          SELECT level,
                 COALESCE(province_territory, 'CA') AS ju,
                 source_set,
                 boundaries_version AS version,
                 min(effective_from) AS starts,
                 -- ⚠ Districts only, on BOTH sides of the comparison. A
                 -- municipal set holds the city outline (boundary_kind
                 -- 'municipality') and sometimes boroughs alongside its
                 -- wards, and an incoming generation usually reloads only the
                 -- wards. Counting raw rows made every Ontario 2026 map look
                 -- like it was losing a ward when it was not.
                 count(*) FILTER (
                   WHERE boundary_kind = 'district' OR boundary_kind IS NULL
                 ) AS incoming
            FROM constituency_boundaries
           WHERE effective_from > CURRENT_DATE
             AND effective_from <= CURRENT_DATE + $1::int
           GROUP BY 1, 2, 3, 4
        )
        SELECT u.*,
               -- What is live in that set the day before the flip.
               (SELECT count(*) FROM constituency_boundaries o
                 WHERE o.source_set = u.source_set
                   AND (o.boundary_kind = 'district' OR o.boundary_kind IS NULL)
                   AND o.effective_from <= u.starts - 1
                   AND (o.effective_to IS NULL
                        OR o.effective_to >= u.starts - 1)) AS outgoing,
               -- Members who resolve today but will not on the flip date.
               --
               -- ⚠ Keyed on the boundary row the member currently resolves
               -- to, NOT on a prefix match against source_set. id_prefix and
               -- source_set are allowed to differ (Montréal's roster sits in
               -- `montreal-boroughs-and-districts`), and a cutover renames the
               -- set while leaving ids alone — a LIKE would silently score
               -- those sets zero.
               (SELECT count(*) FROM politicians p
                 WHERE p.is_active
                   AND p.constituency_id IS NOT NULL
                   AND EXISTS (SELECT 1 FROM constituency_boundaries b
                                WHERE b.constituency_id = p.constituency_id
                                  AND b.source_set = u.source_set
                                  AND b.effective_from <= CURRENT_DATE
                                  AND (b.effective_to IS NULL
                                       OR b.effective_to >= CURRENT_DATE))
                   AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                                    WHERE b.constituency_id = p.constituency_id
                                      AND b.effective_from <= u.starts
                                      AND (b.effective_to IS NULL
                                           OR b.effective_to >= u.starts))
               ) AS orphans
          FROM upcoming u
         ORDER BY u.starts, u.level, u.source_set
        """,
        horizon_days,
    )

    seats_by_ju = {
        r["jurisdiction"]: r["seats"]
        for r in await db.fetch(
            "SELECT jurisdiction, seats FROM jurisdiction_sources "
            "WHERE level = 'provincial'"
        )
    }

    out: list[PendingFlip] = []
    for r in rows:
        # Seat counts only exist for provincial/federal; a council has no
        # one-seat-one-polygon rule (see the municipal section above).
        seats = seats_by_ju.get(r["ju"]) if r["level"] == "provincial" else None
        out.append(PendingFlip(
            level=r["level"], jurisdiction=r["ju"], source_set=r["source_set"],
            version=r["version"], starts=r["starts"],
            incoming=r["incoming"], outgoing=r["outgoing"],
            orphans=r["orphans"], seats=seats,
        ))
    return out
