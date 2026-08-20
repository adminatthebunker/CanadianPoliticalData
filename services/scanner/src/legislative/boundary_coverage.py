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
from typing import Optional

from ..db import Database

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
                 count(*) FILTER (
                   WHERE constituency_id IS NOT NULL
                     AND NOT EXISTS (
                       SELECT 1 FROM constituency_boundaries b
                        WHERE b.constituency_id = politicians.constituency_id)
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


async def check_municipal_integrity(db: Database) -> list[MunicipalProblem]:
    """Per-seat municipal checks. Empty list means clean."""
    out: list[MunicipalProblem] = []

    rows = await db.fetch(
        """
        SELECT p.name, p.elected_office, p.constituency_id
          FROM politicians p
         WHERE p.is_active AND p.level = 'municipal'
           AND p.constituency_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM constituency_boundaries b
                            WHERE b.constituency_id = p.constituency_id)
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

    # ⚠ Near-identical overlapping polygons make a smallest-first lookup
    # planner-dependent — the Peel defect, fixed in 0083. Cheap to re-check.
    dupes = await db.fetchval(
        """
        SELECT count(*) FROM constituency_boundaries a
          JOIN constituency_boundaries b
            ON b.constituency_id > a.constituency_id
           AND b.level = 'municipal' AND b.boundary_kind = 'district'
           AND ST_Intersects(a.boundary, b.boundary)
           AND ST_Area(ST_Intersection(a.boundary, b.boundary))
                 / least(ST_Area(a.boundary), ST_Area(b.boundary)) >= 0.98
           AND ST_Area(a.boundary) / ST_Area(b.boundary) BETWEEN 0.98 AND 1.02
         WHERE a.level = 'municipal' AND a.boundary_kind = 'district'
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
    return out
