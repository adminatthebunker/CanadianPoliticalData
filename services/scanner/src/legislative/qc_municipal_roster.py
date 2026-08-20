"""Québec municipal roster from the MAMH general-election results.

⛔ WHY THIS EXISTS: the Open North municipal roster for Québec is a full
election cycle stale. Queried 2026-08-19, it still served **Valérie Plante** as
mayor of Montréal — 9½ months after Soraya Martinez Ferrada won on 2025-11-02.
Open North is UP; it is simply not maintained, so re-running
`ingest-all-councils` cannot fix it. The 2025 municipal general election
replaced or reconfirmed every one of the 348 Québec municipal officials we hold,
and we had none of it.

The Ministère des Affaires municipales publishes the full province-wide result
as one CC-BY CSV — 12,658 candidates, 7,835 elected, 1,061 municipalities — so a
single file replaces 24 separate scrapes.

★ Rows written here carry a `mamh-qc:` source_id rather than `opennorth:`, and
that is deliberate. `compare_politicians.detect_retirements` sweeps
`opennorth:{set}:%` and deactivates anything the Open North feed omits; it did
exactly that to a hand-verified Manitoba by-election member three hours after she
was added. A roster sourced from the election authority must not be at the mercy
of a stale mirror, so it lives outside that prefix.

⚠ The corollary: running `ingest-all-councils` for Québec would now insert the
stale Open North rows alongside these as duplicates. Those sets are skip-listed
in `opennorth.py` for that reason.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..db import Database

DEFAULT_CSV = "/data/rosters/quebec-municipal/current/Elec2025_Mun.csv"

# The 2025 Québec municipal general election.
ELECTION_DATE = "2025-11-02"

# ⛔ BOTH statuses are winners. `Élu sans opposition` (4,607 province-wide)
# outnumbers `Élu` (3,228); testing for equality with 'Élu' silently drops 59% of
# the elected officials in Québec.
WINNER_PREFIX = "Élu"

SOURCE_PREFIX = "mamh-qc"

# ⛔ EVERY district/borough attach MUST be scoped to the municipality that owns
# the polygon. `district-1` exists in THIRTEEN Québec source sets, and even named
# districts collide: `plateau` is both Gatineau's and Québec City's, `saint-
# charles` is both Kirkland's and Longueuil's, `carrefour` is both Laval's (as
# `Le Carrefour`) and Sherbrooke's.
#
# An unscoped join is not merely ambiguous, it is silently WRONG and
# planner-dependent: it put Gatineau's councillor for Plateau on Québec City's
# Plateau, 400 km away. Migration 0089 repairs the three it produced.
#
# One set per municipality, named `<slug>-districts` — and note the set holds
# that municipality's boroughs too, so `saguenay-districts` contains
# `saguenay-boroughs/chicoutimi`. Montréal is the sole exception.
SOURCE_SET_OVERRIDES = {"montreal": "montreal-boroughs-and-districts"}

# The two MAMH post types that sit in a district. `Maire` and
# `Maire d'arrondissement` take the municipality and borough polygons instead.
COUNCILLOR_OFFICES = {"Conseiller", "Conseiller d'arrondissement"}


def source_set_for(muni: str) -> str:
    """The one boundary source_set that owns `muni`'s district/borough polygons."""
    return SOURCE_SET_OVERRIDES.get(muni, f"{muni}-districts")


def slugify(s: str) -> str:
    """Match `boundary_loader.slugify` so roster slugs join to boundary ids."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("'", "").replace("’", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


@dataclass
class RosterStats:
    municipalities: int = 0
    winners: int = 0
    inserted: int = 0
    updated: int = 0
    rekeyed: int = 0
    deactivated: int = 0
    attached: int = 0
    unattached: int = 0
    problems: list[str] = field(default_factory=list)


def read_winners(csv_path: Path, municipality_slugs: set[str]) -> dict[str, list[dict]]:
    """Elected officials, grouped by municipality slug."""
    # ⚠ utf-8-SIG: the file carries a BOM, and a plain utf-8 read leaves it
    # glued to the first column name so `Code de la municipalité` never matches.
    text = csv_path.read_text(encoding="utf-8-sig")
    out: dict[str, list[dict]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if not (row.get("Statut du candidat") or "").startswith(WINNER_PREFIX):
            continue
        muni = slugify(row.get("Nom de la municipalité", ""))
        if muni not in municipality_slugs:
            continue
        out.setdefault(muni, []).append(row)
    return out


def _numbered_posts(rows: list[dict]) -> set[int]:
    """
    Councillor post numbers for a municipality that identifies districts by
    number — empty if any councillor carries a district NAME instead.

    ⚠ All-or-nothing on purpose. A municipality that names some districts and
    numbers others is a shape we have not seen and would be guessing at.
    """
    posts: set[int] = set()
    for r in rows:
        if (r.get("Type de poste") or "").strip() not in COUNCILLOR_OFFICES:
            continue
        if (r.get("Nom du district électoral") or "").strip():
            return set()
        try:
            n = int((r.get("Identifiant du poste") or "").strip())
        except ValueError:
            return set()
        if n < 1:
            return set()
        posts.add(n)
    return posts


async def ingest_qc_municipal_roster(
    db: Database, csv_path: str = DEFAULT_CSV, dry_run: bool = False,
) -> RosterStats:
    st = RosterStats()

    # ⚠ Discover the councils from BOTH prefixes, or this runs exactly once.
    # The first run re-keys every matched row from `opennorth:` to `mamh-qc:`,
    # so a discovery query scoped to `opennorth:` finds nothing on the second run
    # and the whole ingest silently becomes a no-op — councils=0, winners=0.
    # Idempotence matters here: this is how the roster gets refreshed after a
    # by-election or a corrected source file.
    councils = await db.fetch(
        """
        SELECT DISTINCT
               CASE WHEN source_id LIKE 'mamh-qc:%'
                    THEN 'conseil-municipal-de-' || split_part(source_id, ':', 2)
                    ELSE split_part(source_id, ':', 2)
               END AS council
          FROM politicians
         WHERE level = 'municipal' AND province_territory = 'QC' AND is_active
           AND (source_id LIKE 'opennorth:conseil-municipal-de-%'
                OR source_id LIKE 'mamh-qc:%')
        """
    )
    # `conseil-municipal-de-montreal` -> `montreal`
    muni_of = {
        r["council"]: r["council"].replace("conseil-municipal-de-", "")
        for r in councils
    }
    st.municipalities = len(muni_of)
    winners = read_winners(Path(csv_path), set(muni_of.values()))

    missing = sorted(set(muni_of.values()) - set(winners))
    if missing:
        raise RuntimeError(
            f"{len(missing)} held Québec councils have no 2025 result in the "
            f"MAMH file: {missing}. Refusing to run — deactivating a council "
            f"because its name did not match would wipe it."
        )

    # ── Ownership map: municipality -> the source_set holding its polygons ───
    # Every attach below joins through this. Built once, asserted once: a
    # municipality whose set is absent would silently attach nobody, which reads
    # as "that council has no districts" rather than as a broken convention.
    owned = {muni: source_set_for(muni) for muni in muni_of.values()}
    known_sets = {
        r["source_set"] for r in await db.fetch(
            """
            SELECT DISTINCT source_set FROM constituency_boundaries
             WHERE level = 'municipal' AND province_territory = 'QC'
            """
        )
    }
    unknown = sorted(m for m, ss in owned.items() if ss not in known_sets)
    if unknown:
        raise RuntimeError(
            f"{len(unknown)} held Québec councils resolve to a boundary "
            f"source_set that does not exist: "
            f"{[(m, owned[m]) for m in unknown]}. Either the set was never "
            f"loaded or it breaks the `<slug>-districts` convention — add it to "
            f"SOURCE_SET_OVERRIDES rather than letting the attach no-op."
        )

    # ── Which municipalities identify districts by NUMBER ────────────────────
    # ⛔ MAMH names the district for only 758 of 7,835 winners province-wide. For
    # everyone else the district is carried as `Identifiant du poste` — 0 for the
    # mayor, 1..N for the councillors — and our polygons for exactly those
    # municipalities are named `District N`.
    #
    # ★ That the post number IS the district number was measured, not assumed:
    # for every incumbent re-elected to the same post, MAMH's post id was
    # compared against the district number their pre-2025 `politician_terms` row
    # still carries. 53 of 53 agree, 0 disagree.
    #
    # ⛔ Admit a municipality only when its polygon slugs are EXACTLY
    # {district-1 .. district-C} for C councillors elected. A bare count check is
    # not enough and a count MISmatch is disqualifying on its own: Brossard
    # elected 12 councillors against 9 polygons, so its council grew and post 3
    # is no longer district 3. Attaching those would be worse than leaving them
    # NULL.
    #
    # ⚠ This buys ATTACHMENT, not vintage. Stable numbering is weak evidence the
    # maps were not redrawn in place, and no evidence at all that they were not.
    numbered: set[str] = set()
    for muni, source_set in sorted(owned.items()):
        posts = _numbered_posts(winners[muni])
        if not posts:
            continue
        slugs = {
            r["slug"] for r in await db.fetch(
                """
                SELECT split_part(constituency_id, '/', 2) AS slug
                  FROM constituency_boundaries
                 WHERE source_set = $1 AND boundary_kind = 'district'
                   AND effective_from <= CURRENT_DATE
                   AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                """,
                source_set,
            )
        }
        wanted = {f"district-{n}" for n in posts}
        if slugs and slugs == wanted:
            numbered.add(muni)
        elif slugs and slugs & wanted:
            st.problems.append(
                f"{muni}: {len(posts)} numbered posts elected but the polygon "
                f"set holds {len(slugs)} districts — council resized, so post N "
                f"is no longer district N. Left unattached deliberately."
            )

    for council, muni in sorted(muni_of.items()):
        rows = winners[muni]
        st.winners += len(rows)
        seen: set[str] = set()

        for r in rows:
            given = (r.get("Prénom") or "").strip()
            family = (r.get("Nom") or "").strip()
            name = f"{given} {family}".strip()
            office = (r.get("Type de poste") or "").strip()
            party = (r.get("Nom du parti ou de l'équipe") or "").strip() or None
            borough = (r.get("Nom de l'arrondissement") or "").strip()
            district = (r.get("Nom du district électoral") or "").strip()

            # ⛔ Where MAMH names no district, the district has no name: for a
            # numbered municipality `District N` IS the name, and it is exactly
            # what our polygon carries. Gated on `numbered`, which admits a
            # municipality only when its polygon slugs are precisely the posts
            # elected.
            if not district and muni in numbered and office in COUNCILLOR_OFFICES:
                district = f"District {(r.get('Identifiant du poste') or '').strip()}"

            # The constituency the office is actually elected for: a district
            # where one is named, else the borough, else the whole municipality.
            constituency = district or borough or r.get("Nom de la municipalité", "")
            sid = f"{SOURCE_PREFIX}:{muni}:{slugify(name)}"
            seen.add(sid)
            if dry_run:
                continue

            existing = await db.fetchrow(
                "SELECT id FROM politicians WHERE source_id = $1", sid,
            )
            if existing is None:
                # ★ RE-KEY A RE-ELECTED MEMBER RATHER THAN REPLACE THEM.
                #
                # The 348 Open North rows for Québec carry 209 socials, 259
                # constituency offices and 264 websites, and most of these people
                # were RE-elected on 2025-11-02. Deactivating them and inserting a
                # fresh row would strand every one of those attachments on an
                # inactive row — the same defect that put 424 BC speeches on the
                # wrong politician (migration 0069).
                #
                # So when the winner matches a sitting Open North row by name,
                # that row is kept and its source_id is moved to `mamh-qc:`. The
                # person keeps their id, their offices, their socials and their
                # websites, and simultaneously leaves the Open North retirement
                # sweep.
                existing = await db.fetchrow(
                    """
                    SELECT id FROM politicians
                     WHERE level = 'municipal' AND province_territory = 'QC'
                       AND is_active
                       AND source_id LIKE $1
                       AND regexp_replace(lower(unaccent(name)), '[^a-z0-9]+', '', 'g')
                         = regexp_replace(lower(unaccent($2)), '[^a-z0-9]+', '', 'g')
                     LIMIT 1
                    """,
                    f"opennorth:{council}:%", name,
                )
                if existing:
                    await db.execute(
                        "UPDATE politicians SET source_id = $2 WHERE id = $1::uuid",
                        existing["id"], sid,
                    )
                    st.rekeyed += 1

            if existing:
                await db.execute(
                    """
                    UPDATE politicians
                       SET name = $2, first_name = $3, last_name = $4,
                           elected_office = $5, party = $6,
                           constituency_name = $7, is_active = true,
                           -- ⛔ Clear the old attachment. A re-keyed row keeps
                           -- its id (and its socials, offices and websites),
                           -- but the person may have changed SEAT: Stéphane
                           -- Boyer was Laval's councillor for Duvernay-Pont-Viau
                           -- before being elected mayor, and carrying his old
                           -- constituency_id forward left the mayor of Laval
                           -- attached to a single district polygon. The attach
                           -- pass below re-derives it from the 2025 result.
                           constituency_id = NULL,
                           updated_at = now()
                     WHERE id = $1::uuid
                    """,
                    existing["id"], name, given, family, office, party, constituency,
                )
                st.updated += 1
            else:
                await db.execute(
                    """
                    INSERT INTO politicians
                        (source_id, name, first_name, last_name, level,
                         province_territory, elected_office, party,
                         constituency_name, is_active)
                    VALUES ($1,$2,$3,$4,'municipal','QC',$5,$6,$7,true)
                    ON CONFLICT (source_id) DO NOTHING
                    """,
                    sid, name, given, family, office, party, constituency,
                )
                st.inserted += 1

        if dry_run:
            continue

        # ⛔ Deactivate the stale Open North cohort for this council. Safe in a
        # way the Open North sweep is not: the replacement comes from the
        # election authority's own result, not from another mirror's silence.
        res = await db.execute(
            """
            UPDATE politicians
               SET is_active = false, updated_at = now()
             WHERE level = 'municipal' AND province_territory = 'QC' AND is_active
               AND source_id LIKE $1
            """,
            f"opennorth:{council}:%",
        )
        try:
            st.deactivated += int(str(res).rsplit(" ", 1)[-1])
        except ValueError:
            pass

    if not dry_run:
        # Attach to geometry by slug. Districts and boroughs both live in the
        # municipality's own source_set; the mayor takes the whole-municipality
        # polygon.
        # ── Attach, by TIER ─────────────────────────────────────────────
        # ⛔ A single slug join is wrong here, because a municipal council spans
        # three tiers and the same name can exist at two of them. Matching
        # `cpd_slugify(constituency_name)` against every municipal polygon put
        # the MAYOR OF LAVAL on a single district polygon.
        #
        # ⚠ `cpd_slugify` (migration 0080), never a hand-written regex: it strips
        # apostrophes and periods before hyphenating, and Québec district names
        # are full of them (`d'Ahuntsic`, `de L'Île-des-Soeurs`).
        #
        # Mayors take the whole-municipality polygon; borough mayors take the
        # borough; everyone else takes a district within their own municipality's
        # source_set.
        # ⚠ `owned` scopes every pass below to the municipality that owns the
        # polygon. Passed as two parallel arrays rather than derived in SQL, so
        # the convention lives in exactly one place (`source_set_for`) and is
        # asserted before any row is touched.
        munis = sorted(owned)
        sets = [owned[m] for m in munis]

        # The mayor's polygon may live in the municipality's own set OR in
        # `census-subdivisions`, which is where the StatCan CSD outlines sit.
        await db.execute(
            """
            WITH owned AS (SELECT unnest($2::text[]) AS muni,
                                  unnest($3::text[]) AS source_set)
            UPDATE politicians p
               SET constituency_id = b.constituency_id, updated_at = now()
              FROM constituency_boundaries b, owned o
             WHERE p.is_active AND p.level = 'municipal'
               AND p.source_id LIKE $1
               AND p.constituency_id IS NULL
               AND p.elected_office IN ('Maire', 'Maire de la Ville de Montréal')
               AND o.muni = split_part(p.source_id, ':', 2)
               AND b.source_set IN (o.source_set, 'census-subdivisions')
               AND b.level = 'municipal' AND b.province_territory = 'QC'
               AND b.boundary_kind = 'municipality'
               AND cpd_slugify(b.name) = cpd_slugify(p.constituency_name)
            """,
            f"{SOURCE_PREFIX}:%", munis, sets,
        )
        await db.execute(
            """
            WITH owned AS (SELECT unnest($2::text[]) AS muni,
                                  unnest($3::text[]) AS source_set)
            UPDATE politicians p
               SET constituency_id = b.constituency_id, updated_at = now()
              FROM constituency_boundaries b, owned o
             WHERE p.is_active AND p.level = 'municipal'
               AND p.source_id LIKE $1
               AND p.constituency_id IS NULL
               AND p.elected_office = 'Maire d''arrondissement'
               AND o.muni = split_part(p.source_id, ':', 2)
               AND b.source_set = o.source_set
               AND b.level = 'municipal' AND b.province_territory = 'QC'
               AND b.boundary_kind = 'borough'
               AND cpd_slugify(b.name) = cpd_slugify(p.constituency_name)
            """,
            f"{SOURCE_PREFIX}:%", munis, sets,
        )
        await db.execute(
            """
            WITH owned AS (SELECT unnest($2::text[]) AS muni,
                                  unnest($3::text[]) AS source_set)
            UPDATE politicians p
               SET constituency_id = b.constituency_id, updated_at = now()
              FROM constituency_boundaries b, owned o
             WHERE p.is_active AND p.level = 'municipal'
               AND p.source_id LIKE $1
               AND p.constituency_id IS NULL
               AND o.muni = split_part(p.source_id, ':', 2)
               AND b.source_set = o.source_set
               AND b.level = 'municipal' AND b.province_territory = 'QC'
               AND b.boundary_kind = 'district'
               AND b.effective_from <= CURRENT_DATE
               AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
               AND split_part(b.constituency_id, '/', 2)
                 = cpd_slugify(p.constituency_name)
            """,
            f"{SOURCE_PREFIX}:%", munis, sets,
        )
        # ── Fallback pass: French articles, elision, spacing, tiers ─────
        # ⛔ Two publishers, two conventions for the same district — and the ways
        # they differ are NOT one problem:
        #
        #   roster  `du Sault-au-Récollet`   polygon  `Sault-au-Récollet`   article
        #   roster  `de Lennoxville`         polygon  `Lennoxville`         article
        #   roster  `d'Ascot`                polygon  `Ascot`               ELISION
        #   roster  `DeLorimier`             polygon  `De Lorimier`         SPACING
        #   roster  `de l'Est`               polygon  `Est`                 both
        #
        # ⚠ ELISION defeated the previous version. `d'Ascot` slugifies to
        # `dascot` — the apostrophe is REMOVED, not hyphenated — so a regex
        # stripping a leading `d-` never fires. It has to come off the RAW name,
        # before slugification.
        #
        # ⚠ And SPACING pulls the opposite way: `DeLorimier` -> `delorimier`
        # while `De Lorimier` -> `de-lorimier`, so stripping the article from the
        # polygon side alone yields `lorimier` and matches nothing. Article
        # removal cannot be unconditional; the hyphen-collapsed form WITHOUT it
        # is a separate key.
        #
        # Hence four keys per side rather than one rewrite: exact, de-articled,
        # de-hyphenated, and both. A match on any is accepted — but only where the
        # key is unambiguous WITHIN THE MUNICIPALITY and reaches one polygon.
        #
        # ⚠ Still a SECOND pass, over rows the exact join left NULL. A looser
        # comparison must never outrank an exact one.
        #
        # ★ And it now spans BOROUGHS, not only districts. Montréal's smaller
        # boroughs elect their city councillor borough-wide rather than by
        # district, so `Conseiller` for `Anjou` or `Lachine` has no district to
        # match — the constituency IS the borough. Restricting the fallback to
        # `boundary_kind = 'district'` made those unattachable by construction,
        # along with every borough mayor whose MAMH name carries an article
        # (`Le Plateau-Mont-Royal` vs `Plateau-Mont-Royal`).
        await db.execute(
            """
            WITH owned AS (SELECT unnest($2::text[]) AS muni,
                                  unnest($3::text[]) AS source_set),
            bkeys AS (
              SELECT b.constituency_id, b.source_set, k.key
                FROM constituency_boundaries b
               CROSS JOIN LATERAL (
                 SELECT unnest(ARRAY[
                   cpd_slugify(b.name),
                   regexp_replace(cpd_slugify(b.name),
                     '^(de-la-|de-l-|de-|du-|des-|d-|la-|le-|les-)', ''),
                   regexp_replace(cpd_slugify(b.name), '-', '', 'g'),
                   regexp_replace(
                     regexp_replace(cpd_slugify(b.name),
                       '^(de-la-|de-l-|de-|du-|des-|d-|la-|le-|les-)', ''),
                     '-', '', 'g')
                 ]) AS key
               ) k
               WHERE b.level = 'municipal' AND b.province_territory = 'QC'
                 AND b.boundary_kind IN ('district', 'borough')
                 AND b.effective_from <= CURRENT_DATE
                 AND (b.effective_to IS NULL OR b.effective_to >= CURRENT_DATE)
            ), uniq AS (
              -- ⚠ A key reaching two different polygons is DROPPED. Collapsing
              -- articles and hyphens can make two real districts look alike, and
              -- a wrong attachment is worse than none.
              SELECT source_set, key, min(constituency_id) AS constituency_id
                FROM bkeys
               GROUP BY source_set, key
              HAVING count(DISTINCT constituency_id) = 1
            ), pkeys AS (
              SELECT p.id, o.source_set, k.key
                FROM politicians p
                JOIN owned o ON o.muni = split_part(p.source_id, ':', 2)
               CROSS JOIN LATERAL (
                 SELECT regexp_replace(
                          regexp_replace(p.constituency_name,
                                         '^(de |du |des |de la |le |la |les )',
                                         '', 'i'),
                          -- ⚠ THREE quotes: `''` is one literal apostrophe
                          -- inside a SQL string. Five silently matched a
                          -- DOUBLE apostrophe, i.e. nothing, and the elision
                          -- pass no-opped while looking correct.
                          '^(d|l)''', '', 'i') AS base
               ) e
               CROSS JOIN LATERAL (
                 SELECT unnest(ARRAY[
                   cpd_slugify(e.base),
                   regexp_replace(cpd_slugify(e.base), '-', '', 'g'),
                   cpd_slugify(p.constituency_name),
                   regexp_replace(cpd_slugify(p.constituency_name), '-', '', 'g')
                 ]) AS key
               ) k
               WHERE p.is_active AND p.level = 'municipal'
                 AND p.source_id LIKE $1
                 AND p.constituency_id IS NULL
            ), matched AS (
              SELECT pk.id, min(u.constituency_id) AS constituency_id
                FROM pkeys pk
                JOIN uniq u ON u.source_set = pk.source_set AND u.key = pk.key
               GROUP BY pk.id
              HAVING count(DISTINCT u.constituency_id) = 1
            )
            UPDATE politicians p
               SET constituency_id = m.constituency_id, updated_at = now()
              FROM matched m
             WHERE p.id = m.id
            """,
            f"{SOURCE_PREFIX}:%", munis, sets,
        )

        st.attached = await db.fetchval(
            """
            SELECT count(*) FROM politicians
             WHERE is_active AND level = 'municipal' AND source_id LIKE $1
               AND constituency_id IS NOT NULL
            """,
            f"{SOURCE_PREFIX}:%",
        ) or 0
        st.unattached = await db.fetchval(
            """
            SELECT count(*) FROM politicians
             WHERE is_active AND level = 'municipal' AND source_id LIKE $1
               AND constituency_id IS NULL
            """,
            f"{SOURCE_PREFIX}:%",
        ) or 0
    return st
