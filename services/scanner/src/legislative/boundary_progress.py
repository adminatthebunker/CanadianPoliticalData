"""Generated progress tracker for the boundary + Open North replacement programme.

★ WHY THIS IS GENERATED AND NOT WRITTEN.

The prose corpus under `docs/research/boundaries/` carried the programme's
coverage matrices by hand. Four days after the programme shipped, every count in
them was wrong, and because `/docs/` was gitignored there was no diff to notice
it in. Meanwhile `check-boundary-coverage` — which had the real numbers — was
print-only, and its output survived solely as `scanner_jobs.stdout_tail`, a
rolling 4 KB tail that truncates the per-jurisdiction lines away.

So the counts are derived here and the prose keeps only the reasoning. A number
nobody types is a number that cannot drift.

⛔ THREE TRAPS THIS MODULE EXISTS TO AVOID, all of which produced a wrong
   headline figure during its own construction:

1. `effective_to IS NULL` is NOT the live set. It counts DORMANT FUTURE
   generations (Pickering's 2026 map, loaded and waiting) as though they were
   in force, and it drops generations that are end-dated but have not expired
   yet. Use LIVE_WINDOW. This is `docs/gotchas.md` § "Every EXISTS against
   constituency_boundaries must filter the live window", and it cost six
   sentinel checks that failed open.

2. `boundary_kind = 'municipality'` rows are city OUTLINES, not districts.
   Counting them alongside districts made 34 boundary sets look "partially
   replaced" when in truth each had exactly one authoritative row — the
   outline — and none of its districts.

3. `authority IS NULL` on a LIVE row does not always mean remaining work. A
   superseded generation stays live until the day its successor takes force:
   Québec's 2017 provincial map is 124 mirror rows serving lookups right now
   and correctly so, with an authoritative 127-district successor already
   loaded and dated 2026-10-05 (migration 0117). Reporting that as a 124-row
   backlog invents work; reporting it as done hides that today's answers are
   still mirror geometry. It is neither, so it gets its own column.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..db import Database

# Rows in force TODAY. See trap 1 above.
LIVE_WINDOW = (
    "effective_from <= CURRENT_DATE "
    "AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)"
)

# See trap 2. Districts and boroughs are seats; municipality rows are outlines.
DISTRICTS_ONLY = "boundary_kind IS DISTINCT FROM 'municipality'"


@dataclass
class GeometryRow:
    level: str
    pt: str
    live: int
    authoritative: int
    successor_dated: int   # mirror now, authoritative successor already dated
    remaining: int         # mirror now, nothing queued — the real backlog

    @property
    def pct(self) -> float:
        return (100.0 * self.authoritative / self.live) if self.live else 0.0


async def geometry_progress(db: Database) -> list[GeometryRow]:
    """Three-state geometry classification, per level and jurisdiction."""
    return [
        GeometryRow(
            level=r["level"], pt=r["pt"], live=r["live"],
            authoritative=r["authoritative"],
            successor_dated=r["successor_dated"], remaining=r["remaining"],
        )
        for r in await db.fetch(
            f"""
            WITH live AS (
                SELECT * FROM constituency_boundaries
                 WHERE {LIVE_WINDOW} AND {DISTRICTS_ONLY}
            )
            SELECT l.level,
                   COALESCE(l.province_territory, 'CA') AS pt,
                   count(*) AS live,
                   count(*) FILTER (WHERE l.authority IS NOT NULL)
                       AS authoritative,
                   count(*) FILTER (
                       WHERE l.authority IS NULL AND EXISTS (
                           SELECT 1 FROM constituency_boundaries s
                            WHERE s.source_set = l.source_set
                              AND s.authority IS NOT NULL
                              AND s.effective_from > CURRENT_DATE)
                   ) AS successor_dated,
                   count(*) FILTER (
                       WHERE l.authority IS NULL AND NOT EXISTS (
                           SELECT 1 FROM constituency_boundaries s
                            WHERE s.source_set = l.source_set
                              AND s.authority IS NOT NULL
                              AND s.effective_from > CURRENT_DATE)
                   ) AS remaining
              FROM live l
             GROUP BY 1, 2
             ORDER BY 1, 6 DESC, 2
            """
        )
    ]


@dataclass
class RemainingSet:
    pt: str
    source_set: str
    live: int
    remaining: int


async def remaining_sets(db: Database) -> list[RemainingSet]:
    """The named backlog — which maps somebody still has to go and get."""
    return [
        RemainingSet(pt=r["pt"], source_set=r["source_set"],
                     live=r["live"], remaining=r["remaining"])
        for r in await db.fetch(
            f"""
            WITH live AS (
                SELECT * FROM constituency_boundaries
                 WHERE {LIVE_WINDOW} AND {DISTRICTS_ONLY} AND level = 'municipal'
            )
            SELECT COALESCE(l.province_territory, '??') AS pt,
                   l.source_set,
                   count(*) AS live,
                   count(*) FILTER (WHERE l.authority IS NULL) AS remaining
              FROM live l
             GROUP BY 1, 2
            HAVING count(*) FILTER (WHERE l.authority IS NULL) > 0
               AND NOT EXISTS (
                   SELECT 1 FROM constituency_boundaries s
                    WHERE s.source_set = l.source_set
                      AND s.authority IS NOT NULL
                      AND s.effective_from > CURRENT_DATE)
             ORDER BY 4 DESC, 1, 2
            """
        )
    ]


@dataclass
class RosterRow:
    level: str
    pt: str
    active: int
    replaced: int      # re-keyed to a replacement ingester
    legacy_live: int   # mirror prefix, but a native ID keeps it refreshed
    no_path: int       # mirror prefix, no native ID, no replacement ingester


async def roster_progress(db: Database) -> list[RosterRow]:
    """Open North roster replacement, split by whether a refresh path exists.

    ⛔ The three buckets are about REFRESH PATH, not freshness. Nothing on
    `politicians` records when we last confirmed a person still holds a seat;
    `updated_at` only moves when a field changes, so a stable roster looks
    stale and a mass sweep looks fresh. `no_path` is the honest exposure
    number — rows with no mechanism that could ever correct them — and that is
    all it is.
    """
    from .boundary_coverage import HAS_NATIVE_ID
    return [
        RosterRow(level=r["level"], pt=r["pt"], active=r["active"],
                  replaced=r["replaced"], legacy_live=r["legacy_live"],
                  no_path=r["no_path"])
        for r in await db.fetch(
            f"""
            SELECT level,
                   COALESCE(province_territory, 'CA') AS pt,
                   count(*) AS active,
                   count(*) FILTER (
                       WHERE source_id NOT LIKE 'opennorth:%') AS replaced,
                   count(*) FILTER (
                       WHERE source_id LIKE 'opennorth:%'
                         AND {HAS_NATIVE_ID}) AS legacy_live,
                   count(*) FILTER (
                       WHERE source_id LIKE 'opennorth:%'
                         AND NOT {HAS_NATIVE_ID}) AS no_path
              FROM politicians
             WHERE is_active AND source_id IS NOT NULL
             GROUP BY 1, 2
             ORDER BY 6 DESC, 1, 2
            """
        )
    ]


# ⚠ Statutory-cycle inferences, NOT confirmed against each province's own Act.
# Ontario's is corroborated by our own dormant 2026 maps; the other three are
# not corroborated by anything. Confirm before acting on them. `None` means the
# province has a replacement ingester and the date carries no exposure.
ELECTION_CLIFF: dict[str, tuple[str, Optional[str]]] = {
    "ON": ("2026-10-26", "amo-on: (AMO per-cycle API)"),
    "BC": ("2026-10-17", None),
    "MB": ("2026-10-28", None),
    "PE": ("2026-11-02", None),
    "QC": ("2029-11-04", "mamh-qc: (MAMH election result)"),
}


# ── Rendering ────────────────────────────────────────────────────────────────

def _table(headers: list[str], rows: list[list[str]], align: str) -> list[str]:
    """align: one char per column — 'l' or 'r'."""
    sep = ["---" if a == "l" else "---:" for a in align]
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(sep) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


async def render_progress(db: Database, generated_at: str) -> str:
    """Build the whole tracker. Deterministic given the DB state."""
    from .boundary_coverage import check_pending_flips

    geo = await geometry_progress(db)
    sets = await remaining_sets(db)
    roster = await roster_progress(db)
    flips = await check_pending_flips(db)

    L: list[str] = [
        "# Boundary + Open North replacement — progress",
        "",
        "⛔ **Generated file. Do not hand-edit.** Regenerate with "
        "`boundary-progress`; run it in the same change that lands a cutover.",
        "",
        "The prose dossiers in this directory carry the *reasoning* — licences, "
        "traps, per-jurisdiction findings. This file carries the *counts*, "
        "because the hand-maintained coverage matrices were wrong within four "
        "days of the programme shipping.",
        "",
    ]

    # ── Geometry ──
    by_level: dict[str, list[GeometryRow]] = {}
    for g in geo:
        by_level.setdefault(g.level, []).append(g)

    L += ["## Geometry — is the map ours?", "",
          "Keyed on `constituency_boundaries.authority`, which is NULL until a "
          "set is cut over to the agency that publishes it. Counts districts "
          "and boroughs only — municipality rows are city outlines, not seats "
          "— and only generations in force **today**.", ""]

    tot = {k: 0 for k in ("live", "auth", "succ", "rem")}
    lvl_rows = []
    for level in ("federal", "provincial", "municipal"):
        rs = by_level.get(level, [])
        live = sum(r.live for r in rs)
        auth = sum(r.authoritative for r in rs)
        succ = sum(r.successor_dated for r in rs)
        rem = sum(r.remaining for r in rs)
        tot["live"] += live; tot["auth"] += auth
        tot["succ"] += succ; tot["rem"] += rem
        pct = (100.0 * auth / live) if live else 0.0
        lvl_rows.append([level, str(live), str(auth), f"{pct:.1f}%",
                         str(succ), str(rem)])
    pct_all = (100.0 * tot["auth"] / tot["live"]) if tot["live"] else 0.0
    lvl_rows.append(["**total**", f"**{tot['live']}**", f"**{tot['auth']}**",
                     f"**{pct_all:.1f}%**", f"**{tot['succ']}**",
                     f"**{tot['rem']}**"])
    L += _table(
        ["level", "live", "authoritative", "%", "successor dated", "remaining"],
        lvl_rows, "lrrrrr")
    L += ["",
          "**successor dated** — mirror geometry still in force, with an "
          "authoritative replacement already loaded and dated. It resolves on "
          "a known day with no work: all of it is Québec's 2017 provincial "
          "map, live until 2026-10-04, superseded 2026-10-05 by the "
          "127-district successor (migration `0117`). ⚠ Until that date, "
          "Québec provincial lookups return mirror polygons.", "",
          "**remaining** — mirror geometry with nothing queued behind it. "
          "This is the backlog.", ""]

    muni = [g for g in by_level.get("municipal", []) if g.live]
    if muni:
        L += ["### Municipal districts by province", ""]
        L += _table(
            ["province", "live", "authoritative", "%", "remaining"],
            [[m.pt, str(m.live), str(m.authoritative), f"{m.pct:.1f}%",
              str(m.remaining)] for m in muni], "lrrrr")
        L += [""]

    if sets:
        L += ["### The named remainder", "",
              f"{sum(s.remaining for s in sets)} district rows across "
              f"{len(sets)} sets. Each is a map somebody has to go and get.",
              ""]
        L += _table(["province", "set", "live", "remaining"],
                    [[s.pt, f"`{s.source_set}`", str(s.live), str(s.remaining)]
                     for s in sets], "llrr")
        L += [""]

    # ── Roster ──
    L += ["## Roster — is the person ours?", "",
          "⛔ `source_id LIKE 'opennorth:%'` counts **provenance, not "
          "staleness**, and over-reports the exposure by ~948 rows. A row "
          "carrying a native legislature ID (CLAUDE.md convention #1) is "
          "matched by exact FK from its own legislature's pipeline every day; "
          "the prefix is just the provenance of its first write. All 332 "
          "\"frozen\" federal MPs are in that bucket.", "",
          "⚠ These are **refresh-path** buckets, not freshness. Nothing on "
          "`politicians` records when we last confirmed a person still holds "
          "a seat.", ""]

    r_rows, r_tot = [], {k: 0 for k in ("a", "r", "l", "n")}
    for r in roster:
        r_tot["a"] += r.active; r_tot["r"] += r.replaced
        r_tot["l"] += r.legacy_live; r_tot["n"] += r.no_path
        if r.no_path or r.legacy_live:
            r_rows.append([f"{r.level} {r.pt}", str(r.active), str(r.replaced),
                           str(r.legacy_live), str(r.no_path)])
    r_rows.append(["**total (all rows)**", f"**{r_tot['a']}**",
                   f"**{r_tot['r']}**", f"**{r_tot['l']}**",
                   f"**{r_tot['n']}**"])
    L += _table(["scope", "active", "replaced", "legacy prefix, live pipeline",
                 "no replacement path"], r_rows, "lrrrr")
    L += ["",
          f"**{r_tot['n']} rows have no replacement path.** That is the honest "
          "exposure number.", ""]

    # ── Cliff ──
    L += ["## Election cliff", "",
          "⚠ Dates other than Ontario's are **statutory-cycle inferences, not "
          "confirmed against each province's own Act**. Ontario's is "
          "corroborated by our own dormant 2026 maps. Confirm before acting.",
          ""]
    cliff = []
    for pt, (date, ingester) in sorted(ELECTION_CLIFF.items(),
                                       key=lambda kv: kv[1][0]):
        exposed = sum(r.no_path for r in roster
                      if r.pt == pt and r.level == "municipal")
        cliff.append([pt, date, str(exposed),
                      f"`{ingester}`" if ingester else "⛔ **none**"])
    L += _table(["province", "next municipal election", "rows with no path",
                 "replacement ingester"], cliff, "llrl")
    L += [""]

    # ── Flips ──
    L += ["## Boundary generations flipping within 60 days", ""]
    if flips:
        L += [f"- {f.describe()}" for f in flips]
    else:
        L += ["_None._"]
    L += ["",
          "---",
          "",
          f"_Generated {generated_at} by `boundary-progress`. "
          "Do not hand-edit — regenerate._"]
    return "\n".join(L) + "\n"
