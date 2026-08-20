# Montréal — the 2025 electoral districts, from the city's own open data.
#
# ⛔ Our 44 district polygons are the 2021 map, superseded at the 2025-11-02
# municipal general election. The roster was rebuilt from the MAMH election
# results on 2026-08-19 and only 206 of 396 Québec municipal members could be
# attached, because the 2025 district names do not slug-match 2021 polygons.
# Montréal is the largest single block of that gap: 27 city councillors and 2
# borough mayors unattached.
#
# ⚠ 58 districts, not 59 — the 2021 map had 59. This is a real redistribution,
# not a re-publication.
#
# ⓘ This file carries DISTRICTS ONLY. Montréal's 18 borough polygons came from
# the Open North mirror and are not replaced here; they were re-typed from
# 'district' to 'borough' in migration 0082 and keep their ids. Ville-Marie's
# borough polygon remains absent from our data entirely — the city publishes
# borough limits as a separate dataset, which is follow-up work.

SPEC = BoundarySpec(
    jurisdiction="montreal-districts",
    source_path="municipal-quebec/current/montreal-districts-electoraux-2025.geojson",
    # ⚠ Already WGS84 degrees — first coordinate [-73.5233, 45.5958], no `crs`
    # member. Montréal publishes in 4326 directly, unlike the provincial QC
    # files which are EPSG:3798.
    src_epsg=4326,
    level="municipal",
    province_territory="QC",
    # ⚠ Same source_set and id_prefix as the rows we already hold, deliberately.
    # The set is MIXED — it holds the CSD polygon, 18 borough polygons and the
    # districts — and only the districts are being replaced. Keeping the prefix
    # means the roster attaches by the same slug scheme it always has.
    source_set="montreal-boroughs-and-districts",
    id_prefix="montreal-boroughs-and-districts",
    authority="ville-de-montreal",
    boundaries_version="2025",
    # The 2025 municipal general election.
    effective_from=date(2025, 11, 2),
    effective_to=None,
    name_field="NOM_DISTRICT",
    name_fr_field=None,      # the file is French; there is no second form
    # ⚠ NO_DISTRICT is the unpadded number ('71'), CODE_DISTRICT the zero-padded
    # string ('071'). Taking the padded one because it is the stable published
    # identifier and sorts correctly.
    authority_id_field="CODE_DISTRICT",
    boundary_kind="district",
    expect_districts=58,
    licence="cc-by-4.0",
    notes="Ville de Montréal via Données Québec, dataset "
          "`vmtl-districts-electoraux`, resource 'Districts électoraux 2025'. "
          "CC-BY 4.0 — commercial use and redistribution explicit, attribution "
          "to the city. Gate-free direct download. "
          "⚠ Districts only; the 18 borough polygons and the CSD row in this "
          "source_set come from elsewhere and are not touched by this load. "
          "⚠ NOM_ARR names the parent borough on every district and is the "
          "hierarchy Montréal publishes — worth capturing when "
          "constituency_boundaries grows a parent column.",
)
