# Gatineau — 19 districts, 2025-11-02 generation.
#
# ⛔ NOT the Données Québec GeoJSON. Package `vgat_-1582475471` offers five
# formats; only ONE of them (GeoJSON) is a Données-Québec-side copy, and that
# copy is the SUPERSEDED map. The other four (CSV / KML / SHP / XLSX) are
# `www.gatineau.ca/upload/donneesouvertes/…` URLs served live by the city. So a
# harvester that reaches for GeoJSON — the obvious choice, and the one every
# other QC spec uses — gets the old map from a package that also serves the new
# one. Measured:
#
#   DQ GeoJSON  last-modified 2025-04-24, DAT_REC 20210101, CONS = 2021-25 council
#   city SHP    last-modified 2025-11-25, DAT_REC 20240101, CONS = 2025-29 council
#
# ★ AND THE TWO ARE NOT THE SAME MAP. District-for-district IoU between them is
# 100.0000% for seventeen of nineteen and:
#
#   de Hull-Wright                        96.4566%
#   du Parc-de-la-Montagne-Saint-Raymond  96.9578%
#
# — a real two-district adjustment along their shared limit. ⚠ Note what that
# does to the usual checks: 19 districts before and after, all 19 names
# identical, and NOTHING below 95%. A clean `--compare` summary would have been
# reported as "the map did not move". It moved. What caught it was the `DAT_REC`
# stamp (2021 -> 2024) and the councillor field, not the geometry comparison.
#
# ⓘ Cheap reusable test, after Terrebonne's `_archive_<date>` sibling: when a
# publisher offers the same layer in several formats, HEAD every one of them.
# Divergent `last-modified` headers inside a single package mean the package is
# not a package — it is a live directory and a stale mirror wearing one title.

# ⛔ Gatineau writes every district name with its leading article — `d'Aylmer`,
# `de Lucerne`, `du Plateau`, `de l'Orée-du-Parc`, `de la Rivière-Blanche`. Our
# 19 held ids, and MAMH's own 2025 election results, carry the bare toponym:
# `gatineau-districts/aylmer`, `.../oree-du-parc`, `.../riviere-blanche`.
#
# The slug is minted from `name`, so without this the load mints nineteen NEW
# ids (`daylmer`, `de-lucerne`, `de-loree-du-parc`) beside the nineteen we hold
# and detaches the entire council. One rule rather than a nineteen-line lookup:
# strip a leading French article, and only a leading one. Verified to reproduce
# all 19 held slugs exactly; `expect_districts=19` plus the loader's
# `slug_matches_existing` telemetry is what catches it if a name ever changes
# shape.
#
# ⚠ Trois-Rivières, three specs down, KEEPS its articles (`de Châteaudun` ->
# `trois-rivieres-districts/de-chateaudun`). The convention is per-city because
# the mirror that minted the ids was per-city. Do not generalise this helper.
_GATINEAU_ARTICLE = re.compile(r"^(?:d'|de\s+l'|de\s+la\s+|de\s+les\s+|de\s+|du\s+|des\s+)")


def _gatineau_label(props: dict) -> Optional[str]:
    """`d'Aylmer` -> `Aylmer`; `de l'Orée-du-Parc` -> `Orée-du-Parc`."""
    raw = str(props.get("DISTRICT") or "").strip()
    if not raw:
        return None
    return _GATINEAU_ARTICLE.sub("", raw, count=1).strip() or raw


SPEC = BoundarySpec(
    jurisdiction="gatineau-districts",
    # Byte-for-byte the archive the city serves; the .cpg says UTF-8 and the
    # loader honours it, so `Deschênes` and `Val-Tétreau` survive.
    source_path="municipal-quebec/current/gatineau-districts-2025-11.zip",
    # .prj is bare `GCS_WGS_1984` — degrees, not metres. Declared per rule 2;
    # the first coordinate is (-75.884863, 45.466906), which is a sanity check,
    # not the authority.
    src_epsg=4326,
    level="municipal",
    province_territory="QC",
    source_set="gatineau-districts",
    id_prefix="gatineau-districts",
    authority="ville-de-gatineau",
    boundaries_version="2025",
    # Ruling A10.4 — the municipal general election this map first governed.
    effective_from=date(2025, 11, 2),
    effective_to=None,
    name_field="DISTRICT",
    name_builder=_gatineau_label,
    # `CODEID` is the stable district code and `NUM` the ballot order; they
    # disagree — Mitigomijokan is CODEID 19 / NUM 5 — because the district was
    # added late and inserted into the sequence rather than appended. CODEID is
    # the one that does not move when the order does.
    authority_id_field="CODEID",
    boundary_kind="district",
    expect_districts=19,
    licence="cc-by-4.0",
    notes="Ville de Gatineau, www.gatineau.ca/upload/donneesouvertes/"
          "DISTRICT_ELECTORAUX.zip (last-modified 2025-11-25). Licensed through "
          "Données Québec package `vgat_-1582475471` ('Districts électoraux', "
          "publisher Ville de Gatineau, cc-by), which lists this exact URL as "
          "its SHP resource. "
          "⛔ The same package's GeoJSON resource is a Données-Québec-side copy "
          "dated 2025-04-24 carrying DAT_REC 20210101 and the 2021-25 council, "
          "and it differs from this file at Hull-Wright (96.46% IoU) and "
          "Parc-de-la-Montagne—Saint-Raymond (96.96%). Do not use it. "
          "⚠ The city writes district names with their leading article "
          "(`d'Aylmer`, `de l'Orée-du-Parc`); MAMH's election results and our "
          "own ids do not (`aylmer`, `oree-du-parc`). `_gatineau_label` strips "
          "the article so the 19 slugs land on the 19 ids we already hold — "
          "without it every id would be minted fresh (`daylmer`) and the whole "
          "council would detach. "
          "⚠ Carries the sitting councillor (CONS), party (PART) and a "
          "gatineau.ca email per district, refreshed to the 2025-elected "
          "council — a roster source as well as a geometry source."
)
