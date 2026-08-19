# ✅ COMPLETED ONE-SHOT — retained for provenance, referenced by migration
# 0070. Ran once on 2026-08-19, inserting exactly one row. Deliberately NOT
# promoted into SPECS: `jurisdiction="quebec-2017-chicoutimi"` is a
# pseudo-jurisdiction, and the registry should describe generations, not
# individual backfills. The live Quebec spec is SPECS["quebec"] (2026).
#
# Quebec 2017 — insert the ONE division we never held, and nothing else.
#
# We hold 124 of the 125 districts in the 2017 map. `Chicoutimi` (CO_CEP 918) is
# absent: a single dropped row in the Open North mirror, with its neighbours
# present on both sides. Until it is added, every address in Chicoutimi gets no
# provincial answer.
#
# ★ WHY A row_filter INSTEAD OF RELOADING ALL 125
# -----------------------------------------------
# The 124 rows we hold were measured at 99.887% mean overlap against this exact
# authoritative file, 0 below 95% — they are the correct generation, and this
# generation is retired in days. Replacing them buys nothing and costs two real
# risks:
#
#   ⛔ The 2017 file spells CO_CEP 370 `Bourget`. That district was renamed
#      `Camille-Laurin` in 2021, MID-GENERATION, and our row already carries the
#      new name with politicians linked to the `camille-laurin` slug. A
#      name-keyed reload would mint `quebec-electoral-districts/bourget`,
#      orphaning the roster link and leaving two rows for one district.
#   ⚠ It would rewrite 124 polygons days before they become historical.
#
# So: load exactly one district. `expect_districts=1` turns "the filter matched
# something unexpected" into an abort rather than a surprise.
#
# ⓘ This is also the first use of `row_filter` in a registered load.

SPEC = BoundarySpec(
    jurisdiction="quebec-2017-chicoutimi",
    source_path="quebec/current/circonscriptions_electorales_2017_shapefile.zip",
    # Flat archive, no directory prefix, accented member name, UPPERCASE .CPG.
    zip_member="Circonscriptions_électorales_2017_shapefile.shp",
    # Same EPSG:3798 as 2026. The 2017 .prj names itself `LambertAQ` and lists
    # the two standard parallels in the opposite order with an explicit
    # Scale_Factor 1.0; LCC is symmetric in its parallels and 1.0 is the default,
    # so the definitions are identical. Verified against the file, not assumed —
    # rule 2 forbids sharing a CRS across generations on faith.
    src_epsg=3798,
    level="provincial",
    province_territory="QC",
    # Generation-free prefix. Migration 0070 moves the other 124 onto it in the
    # same breath; this row simply arrives already correct.
    source_set="quebec-electoral-districts",
    id_prefix="quebec-electoral-districts",
    authority="elections-quebec",
    boundaries_version="2017",
    # ⛔ The LEGAL date, not the 2023-01-01 that opennorth.py hardcoded for every
    # row it ever wrote. The 2017 delimitation was published in the Gazette
    # officielle partie 2 no. 9B on 2017-03-02 but took effect at the dissolution
    # that preceded the 2018 general election: 2018-08-23.
    effective_from=date(2018, 8, 23),
    # ⛔ Retired the day before the 2026 map takes effect. Set HERE as well as in
    # 0070 so this row is never the one that survives into the 29th with a NULL
    # effective_to and drags a second generation live.
    effective_to=date(2026, 8, 28),
    name_field="NM_CEP",
    name_fr_field=None,
    authority_id_field="CO_CEP",
    row_filter=lambda p: str(p.get("NM_CEP") or "").strip() == "Chicoutimi",
    expect_districts=1,
    licence="elections-quebec-non-commercial",
    notes="Single-district backfill of the 2017 generation; see 0070.",
)
