"""Re-attach municipal rosters to the geometry a cutover moved out from under them.

★ WHY THIS EXISTS
─────────────────
A boundary cutover renames or replaces a `source_set` and re-keys its
`constituency_id`s. The roster is a separate table joined on that id, and
nothing in the cutover touches it. So every cutover this programme has shipped
has silently severed its council's roster, and no check looked at the edge
between the two halves.

Measured 2026-08-28: 142 sitting municipal officials across 18 councils held
`constituency_id IS NULL` while their council's geometry sat right there —
Calgary 14, Winnipeg 14, Welland 12, Fredericton 12, Edmonton 12, Regina 10,
Moncton 8, Grimsby 8, Lincoln 8, Saint John 7. A councillor whose
`constituency_name` reads `Ward 1` against a live polygon
`calgary-wards/ward-1`. No new data was needed for any of them.

⛔ THE MATCHING RULE: NAMES NARROW, GEOGRAPHY DECIDES
────────────────────────────────────────────────────
`Ward 1` exists in hundreds of source_sets and `District 1` in dozens of Québec
municipalities — migration 0106 mis-counted 286 rows instead of 203 by scoping
on a district name, and 0089 exists because a Gatineau councillor was attached
to a Québec City district 400 km away.

⚠ Matching the WHOLE COUNCIL at once is necessary but NOT sufficient, and the
first version of this module was wrong about that. The idea was that `Ward 1`
is ambiguous while {Ward 1 … Ward 14} is a fingerprint. It is not: cities
number their wards identically, so Calgary's fourteen ward names are covered
exactly by `hamilton-wards` and `london-wards` too. The refusal path caught it
on the first dry run — nine councils reported as ambiguous ties — which is the
only reason this note is a design comment and not an incident report.

Names therefore only narrow the field. The winner is chosen GEOGRAPHICALLY:

  1. Find the council's own municipality polygon — the one an already-attached
     member of that council sits on (`boundary_kind = 'municipality'`, or the
     StatCan CSD outline the mayor takes).
  2. Keep only candidate sets whose districts actually lie INSIDE it, tested
     with ST_Contains against ST_PointOnSurface of each district.
  3. Require exactly one survivor covering every name.

A ward called `Ward 1` in Hamilton is not inside Calgary, so the ambiguity
disappears against a fact no naming convention can counterfeit. Where a council
has no municipality polygon to anchor on, this refuses rather than falling back
to a name heuristic: an unattached council is a visible problem, a wrongly
attached one is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..db import Database


@dataclass
class ReattachStats:
    councils_examined: int = 0
    councils_matched: int = 0
    attached: int = 0
    problems: list[str] = field(default_factory=list)


async def reattach_municipal_roster(
    db: Database, council: Optional[str] = None, dry_run: bool = False,
) -> ReattachStats:
    st = ReattachStats()

    councils = await db.fetch(
        """
        SELECT split_part(p.source_id, ':', 2) AS council,
               count(*) FILTER (WHERE p.constituency_id IS NULL) AS detached,
               count(*) FILTER (WHERE p.constituency_id IS NOT NULL) AS attached
          FROM politicians p
         WHERE p.is_active AND p.level = 'municipal'
           AND p.source_id LIKE '%:%:%'
           AND ($1::text IS NULL OR split_part(p.source_id, ':', 2) = $1)
         GROUP BY 1
        HAVING count(*) FILTER (WHERE p.constituency_id IS NULL) > 0
         ORDER BY 2 DESC
        """,
        council,
    )

    for c in councils:
        st.councils_examined += 1
        slug_of = c["council"]

        # The detached members of this council, and the slug each one wants.
        # ⓘ `want` resolves through constituency_name_alias (migration 0120):
        # a roster and a boundary publisher can spell the same district
        # differently, and where they do, an explicit reasoned row says so.
        # Never a fuzzy match — see the table comment.
        members = await db.fetch(
            """
            SELECT p.id, p.name,
                   COALESCE(a.target_slug, cpd_slugify(p.constituency_name)) AS want
              FROM politicians p
              LEFT JOIN constituency_name_alias a
                     ON a.council = split_part(p.source_id, ':', 2)
                    AND a.alias_slug = cpd_slugify(p.constituency_name)
             WHERE p.is_active AND p.level = 'municipal'
               AND p.constituency_id IS NULL
               AND p.constituency_name IS NOT NULL
               AND split_part(p.source_id, ':', 2) = $1
            """,
            slug_of,
        )
        wants = {m["want"] for m in members if m["want"]}
        if not wants:
            # Every detached member is nameless — an at-large council, which is
            # correct and complete, not broken. Say nothing.
            continue

        # The council's own footprint: the municipality polygon an
        # already-attached member of this council sits on. Without it there is
        # nothing to test candidate sets against, so refuse (see module docs).
        anchor = await db.fetchval(
            """
            SELECT b.constituency_id
              FROM politicians p
              JOIN constituency_boundaries b
                ON b.constituency_id = p.constituency_id
             WHERE p.is_active AND p.level = 'municipal'
               AND split_part(p.source_id, ':', 2) = $1
               AND b.boundary_kind = 'municipality'
               AND b.effective_from <= CURRENT_DATE
               AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
             LIMIT 1
            """,
            slug_of,
        )
        if anchor is None:
            st.problems.append(
                f"{slug_of}: no municipality polygon to anchor on — cannot "
                f"tell this council's wards from an identically-numbered "
                f"council's, refusing"
            )
            continue

        # Which live set contains these slugs, and are its districts actually
        # inside this council's municipality?
        cands = await db.fetch(
            """
            SELECT b.source_set,
                   count(DISTINCT split_part(b.constituency_id, '/', 2)) AS hits
              FROM constituency_boundaries b
              JOIN constituency_boundaries anc
                ON anc.constituency_id = $2
             WHERE b.level = 'municipal'
               AND (b.boundary_kind = 'district' OR b.boundary_kind IS NULL)
               AND b.effective_from <= CURRENT_DATE
               AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
               AND split_part(b.constituency_id, '/', 2) = ANY($1::text[])
               -- ★ The discriminator. A Hamilton ward is not inside Calgary.
               -- PointOnSurface, not Centroid: a crescent-shaped ward's
               -- centroid can fall outside the ward itself.
               AND ST_Contains(
                     ST_CollectionExtract(ST_MakeValid(anc.boundary), 3),
                     ST_PointOnSurface(
                       ST_CollectionExtract(ST_MakeValid(b.boundary), 3)))
             GROUP BY 1
             ORDER BY 2 DESC
            """,
            sorted(wants), anchor,
        )
        if not cands:
            st.problems.append(
                f"{slug_of}: {len(wants)} district name(s) match no live "
                f"polygon anywhere — geometry is genuinely missing or the map "
                f"changed (e.g. {sorted(wants)[0]})"
            )
            continue

        best = cands[0]
        if len(cands) > 1 and cands[1]["hits"] == best["hits"]:
            # Two sets, both named right AND both geographically inside this
            # municipality. That is a real ambiguity (nested tiers, or a
            # duplicate set a cutover failed to retire), not a naming clash.
            st.problems.append(
                f"{slug_of}: {best['source_set']} and {cands[1]['source_set']} "
                f"both cover {best['hits']} names inside this municipality — "
                f"ambiguous, refusing (this is the 0089 failure mode)"
            )
            continue

        # ⚠ A PARTIAL COVER IS NOT A REASON TO REFUSE, and an earlier draft had
        # this wrong. Full cover was standing in for identity — "if it matches
        # every ward it must be the right city". Geography now establishes
        # identity directly, so a shortfall no longer casts doubt on the SET;
        # it says our map of that city is incomplete. Refusing then throws away
        # ten provable attachments to punish two missing polygons. Attach what
        # is provable, report the rest as the coverage defect it is.
        #
        # ⛔ And report it from what was ACTUALLY WRITTEN, never from the
        # candidate query's hit count. The two use deliberately different
        # predicates: set-selection is spatially filtered (that is the whole
        # discriminator), the write is not (once the set is identified, every
        # slug match in it is correct). Fredericton has two wards lying outside
        # the StatCan CSD outline — annexed land the census boundary predates —
        # so the candidate query scored it 10/12 while the write attached all
        # 12. Reporting the selection count told the operator two polygons were
        # missing when none were.
        st.councils_matched += 1
        if dry_run:
            st.attached += len(members)
            continue

        res = await db.execute(
            """
            UPDATE politicians p
               SET constituency_id = b.constituency_id, updated_at = now()
              FROM constituency_boundaries b
             -- ⚠ Scalar subquery, not a LEFT JOIN: `p` is the UPDATE target
             -- and Postgres will not let a FROM-clause join reference it
             -- ("invalid reference to FROM-clause entry for table p").
             WHERE p.is_active AND p.level = 'municipal'
               AND p.constituency_id IS NULL
               AND split_part(p.source_id, ':', 2) = $1
               AND b.source_set = $2
               AND (b.boundary_kind = 'district' OR b.boundary_kind IS NULL)
               AND b.effective_from <= CURRENT_DATE
               AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
               AND split_part(b.constituency_id, '/', 2)
                 = COALESCE(
                     (SELECT a.target_slug FROM constituency_name_alias a
                       WHERE a.council = split_part(p.source_id, ':', 2)
                         AND a.alias_slug = cpd_slugify(p.constituency_name)),
                     cpd_slugify(p.constituency_name))
            """,
            slug_of, best["source_set"],
        )
        n = 0
        try:
            n = int(str(res).rsplit(" ", 1)[-1])
        except ValueError:
            pass
        st.attached += n
        if n < len(members):
            st.problems.append(
                f"{slug_of}: attached {n} of {len(members)} detached members "
                f"from {best['source_set']} — the remaining "
                f"{len(members) - n} have no polygon under that name, which "
                f"is a map to go and get, not a link to repair"
            )

    return st
