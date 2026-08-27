"""
Authoritative electoral-boundary loader.

Replaces boundary ingestion by side effect. Today boundaries arrive only through
`opennorth.py:_ingest_set`, inside the per-representative handler: a district gets
a polygon only if a *sitting representative for it* appears in Open North's
roster, and any failure is swallowed by a bare `except Exception: log.exception`.
That is why 41 BC districts silently vanished and Nunavut has none at all. This
module is boundary-first, source-agnostic, and fails loudly.

Research: `docs/research/boundaries/` (21 jurisdiction dossiers, 2026-08-18).

Design rules, each earned from a documented failure
---------------------------------------------------

**1. ⛔ Never `ST_SetSRID` — always `ST_Transform`.** Migration `0003` exists
because Fort Erie's wards arrived in EPSG:26917 (UTM metres) and were *labelled*
4326 without reprojection, putting centroids past the edge of the world. The
`boundary_in_wgs84_bounds` CHECK now catches that, and this loader must not rely
on it.

**2. ⛔ The source EPSG is declared, never sniffed.** `.prj` files routinely carry
no `AUTHORITY` clause, so auto-detection fails; EPSG:3005 and 3153 have identical
projection parameters and differ only by datum; and Ontario's GeoJSON has no
`crs` member at all while being NAD83 rather than the WGS84 RFC 7946 mandates.
Every spec states its EPSG explicitly.

**3. ⛔ Count DISTINCT district IDs, not records.** Elections Canada's 45th-GE file
has 352 records for 343 districts because island fragments are separate rows —
loading it naively creates duplicate `constituency_id` values.

**4. ⛔ A rejected geometry fails the run.** Partial loads that look successful are
how BC ended up serving 52 confidently-wrong polygons through a general election.

**5. ⛔ `constituency_id` prefixes never encode a generation.** The unique key is
`(constituency_id, boundaries_version)`, so the id is generation-independent by
design and the version carries the generation. Baking a year in forces a full
`politicians` UPDATE on every future redistribution — 12 of our 13 existing
prefixes have that defect.
"""

from __future__ import annotations

import io
import json
import logging
import re
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Union

from ..db import Database

log = logging.getLogger(__name__)

# ~555 m. Matches what opennorth.py used, so simplified geometry stays
# comparable across sources. Feature-size-aware tolerance is a known follow-up:
# 12 micro-districts in Montréal currently simplify to NULL.
SIMPLIFY_TOLERANCE = 0.005


@dataclass
class BoundarySpec:
    """How to turn one authoritative file into `constituency_boundaries` rows."""

    jurisdiction: str                 # dossier slug, e.g. "ontario"
    # One path, or several. ⚠ Manitoba ships its 57 divisions as TWO shapefiles,
    # neither complete (25 Rural + 32 Urban) — and both outer archives are named
    # `…_Public_Urban.zip`, one of which holds the Rural feature class. A loader
    # that reads "the archive it recognises" gets a silently partial province.
    source_path: Union[str, list[str]]
    src_epsg: Optional[int]           # ⛔ declared, never sniffed — see rule 2
    level: str                        # federal | provincial | municipal
    province_territory: Optional[str]
    source_set: str                   # generation-free — see rule 5
    id_prefix: str                    # generation-free `constituency_id` prefix
    authority: str                    # issuing agency slug
    boundaries_version: str           # the generation label
    effective_from: date
    effective_to: Optional[date] = None
    # Some agencies ship a CUSTOM projection with no EPSG code at all. Elections
    # Ontario's is `EO_Lambert_Conformal_Conic` — Lambert CC, CM -84, SP 44.5/54.5,
    # FE 1,000,000, NAD83, metres — which matches no standard EPSG (notably NOT
    # 3161, Ontario MNR Lambert, which uses CM -85 / SP 44.5,53.5 / FE 930,000).
    # For those, give the proj4 string transcribed from the .prj and leave
    # src_epsg None. PostGIS transforms from a proj4 string directly, so this
    # avoids inserting bespoke rows into spatial_ref_sys.
    src_proj4: Optional[str] = None
    boundary_kind: str = "district"
    name_field: str = "NAME"
    name_fr_field: Optional[str] = None
    # ⛔ Some agencies publish ONE bilingual field rather than two. New Brunswick's
    # `PED_Names_` is "English / Français" where the forms differ (20 of 49) and a
    # single value where they don't ("Caraquet"). Set the separator and the loader
    # splits it: element 0 becomes `name`, element 1 becomes `name_fr`.
    #
    # Not cosmetic — the slug derives from `name`, so unsplit NB mints slugs like
    # `restigouche-west-restigouche-ouest`. Measured: unsplit gives 9 of 22 matched
    # and 13 orphaned; split gives 22 matched, 27 new, 0 orphaned.
    #
    # ⚠ Give the bare separator ("/"), not " / ". NB's 2024 layer pads with spaces
    # and its earlier generations do not, so a padded literal silently no-ops on
    # the older files. Parts are stripped after splitting.
    name_split: Optional[str] = None
    authority_id_field: Optional[str] = None
    # Override when the agency's own name does not slugify to our existing id.
    slug_field: Optional[str] = None
    # Member path(s) inside the archive(s), parallel to source_path. None = the
    # single .shp found by scanning.
    zip_member: Optional[Union[str, list[Optional[str]]]] = None
    # ⚠ Saskatchewan nests: ESK_KML_Shape_Files_Mar2024.zip →
    # ShapeFile/Constituency/Constituency30th.zip → ConstituencyGE30th.shp. Give
    # the inner archive's path within the outer one.
    nested_zip: Optional[str] = None
    # ⛔ Nova Scotia and PEI publish POLLING DIVISIONS, not districts: 1,817
    # features for 56, and 270 for 27. Set this to the district-identifying field
    # and every feature sharing a value is unioned into one row.
    dissolve_by: Optional[str] = None
    # ⛔ PEI carries 26 junk rows (DIST_NO = 0, blank name) that would mint a
    # phantom 28th district. Predicate over the attribute dict; False drops.
    row_filter: Optional[Callable[[dict], bool]] = None
    # ⛔ Exact-match corrections to the NAME FIELD, applied per feature before
    # anything else reads it. `{wrong: right}`.
    #
    # For the case where the AUTHORITY's own data is wrong and we are right —
    # which happens exactly once in the corpus. Newfoundland's `DIST_NAME` is its
    # ENTIRE attribute schema (no ID field of any kind), and district 7 is
    # spelled `Cartwright - L'Anse aux Clair`; the correct name is
    # `L'Anse au Clair`. Elections NL's own poll-map filename, its 2011 file, and
    # our rows all say "au". With no ID to fall back on, a name typo is total key
    # failure for that district.
    #
    # ⚠ `slug_field` CANNOT express this: it overrides the grouping key only,
    # while `constituency_id` is minted from `row["name"]`, which always comes
    # from `name_field`. And a mutating `row_filter` — which does work today,
    # because the filter runs before the name is read — would silently stop
    # working if that order ever changed. A declarative field cannot be broken by
    # reordering.
    #
    # ⛔ NEVER edit the staged file instead. The archive is the byte-for-byte
    # artifact the agency published; a hand-patched .dbf makes every later
    # provenance question unanswerable.
    name_fixups: Optional[dict] = None
    # ⛔ Per-row province, for sources whose rows span more than one province.
    # `province_territory` above is a SCALAR written to every row, which is right
    # for a provincial source and wrong for a national one: Elections Canada's
    # file has no province column at all, yet `constituency_boundaries` carries
    # one per row and our 342 federal rows already have it populated correctly.
    # Loading with the scalar would null all 342.
    #
    # Given the feature's attributes, return a province code (or None). Takes
    # precedence over `province_territory` whenever it returns a value.
    province_resolver: Optional[Callable[[dict], Optional[str]]] = None
    # ⛔ Per-row `source_set` / `id_prefix`, for AGGREGATOR files whose rows span
    # more than one owning body. `source_set` above is a SCALAR written to every
    # row, which is right for one agency publishing one jurisdiction and wrong
    # for a province publishing all of its municipalities at once: Nova Scotia
    # ships 238 districts across 49 municipalities in ONE file, New Brunswick 330
    # wards across 90 local governments.
    #
    # Same shape as `province_resolver`, and for the same reason. Given the
    # feature's attributes, return the set slug that owns it — used for BOTH
    # `source_set` and the `constituency_id` prefix, which is the invariant every
    # municipal set in the table already satisfies. Return None to reject the
    # feature loudly (NB has one ward whose `elect_comm` is null and which cannot
    # be attributed to any local government).
    #
    # ⛔ It also widens the GROUP KEY. Without that, "Ward 1" in Fredericton and
    # "Ward 1" in Moncton are one group, and 90 local governments dissolve into
    # a single set of ward numbers. The resolver runs before grouping for exactly
    # that reason.
    #
    # ⚠ Do not write 139 near-identical specs instead. The per-municipality
    # naming exceptions belong in the resolver, where they are one dict.
    set_resolver: Optional[Callable[[dict], Optional[str]]] = None
    # ⛔ Build the display name where the agency publishes NONE. Distinct from
    # `name_fixups`, which overrides a name the agency did publish and is
    # deliberately hostile territory. Nova Scotia's province-wide file carries
    # `mun`, `poll_dist`, `mu_code`, `co_code`, `reg_num`, `shape_leng`,
    # `shape_area` — and no district name in any of them. `poll_dist` is a code
    # (`AN01`, `TUW1`, `WOAL`), not a label.
    #
    # So there is nothing to override and nothing to preserve: without this the
    # only options are a district displayed to the public as "AN01", or 210
    # hand-written `name_fixups` entries.
    #
    # Return None to fall back to `name_field`.
    name_builder: Optional[Callable[[dict], Optional[str]]] = None
    # Assert the district count after filtering and dissolving. A mismatch aborts
    # the run rather than loading a plausible-looking wrong number of rows.
    expect_districts: Optional[int] = None
    # ⛔ With `set_resolver`, `expect_districts` alone goes half-blind: it counts
    # districts across every set at once, so a municipality mapped to the wrong
    # set slug moves rows between sets without changing the total. These two are
    # what keeps the one assertion that has caught every silent partial load.
    #
    # `expect_sets` — how many distinct sets the file must produce.
    # `expect_per_set` — exact district counts for named sets. A SUBSET is fine:
    # assert the ones whose true count is independently known (the sets we
    # already hold, or a published council size) and leave the rest.
    expect_sets: Optional[int] = None
    expect_per_set: Optional[dict] = None
    # ⚠ Whether the agency INTENDS `authority_district_id` to be unique across
    # the whole aggregator. Only meaningful with `set_resolver`.
    #
    # True for Nova Scotia, whose `poll_dist` embeds the municipal code
    # (`TUW1`, `AN01`) and is therefore province-wide by construction — so a
    # duplicate is an upstream defect worth reporting, and NS has one (`BWAL`
    # for both Bridgewater and Berwick).
    #
    # ⛔ False by default, because the common case is the opposite: New
    # Brunswick's id is the bare ward NUMBER, so ward 8 exists in Fredericton and
    # Tracadie and "At-Large / Général" in sixteen bodies. Reporting those as
    # duplicates buries a real finding under 300 lines of non-findings.
    authority_id_unique_across_sets: bool = False
    # ⚠ Which held source_set `--compare` measures against, when it is not this
    # spec's own. Municipal comparisons are scoped to the set (see
    # `held_scope`), which is what makes them meaningful — but that scoping
    # blocks the one case where the set name itself is what is changing.
    #
    # Toronto is held as `toronto-wards-2018`, generation baked into the set
    # name, and this spec loads it as `toronto-wards` + version `2018`. Without
    # this the comparison reports held=0 and every ward as new, turning a cutover
    # check into no check at all.
    compare_held_source_set: Optional[str] = None
    licence: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.src_epsg is None and not self.src_proj4:
            raise ValueError(
                f"{self.jurisdiction}: declare exactly one of src_epsg or "
                f"src_proj4 — the source CRS is never sniffed (rule 2)"
            )

    def source_crs_sql(self, geom_expr: str) -> str:
        """SQL that reprojects `geom_expr` from the declared source CRS to 4326."""
        if self.src_proj4:
            # ST_Transform(geom, from_proj text, to_srid int). The geometry has no
            # meaningful SRID of its own here, so it is left at 0 and the proj4
            # string supplies the source definition.
            return f"ST_Transform({geom_expr}, {_sql_lit(self.src_proj4)}, 4326)"
        return f"ST_Transform(ST_SetSRID({geom_expr}, {self.src_epsg}), 4326)"


def _sql_lit(s: str) -> str:
    """Single-quoted SQL literal. proj4 strings are ASCII and contain no quotes."""
    return "'" + s.replace("'", "''") + "'"


# Characters Postgres `unaccent()` expands but Unicode NFKD leaves alone. Kept
# deliberately short: every entry is one `unaccent` actually rewrites, so the two
# implementations stay in step. ß is here because unaccent maps it to `ss`, not
# because any Canadian district needs it.
_LIGATURES = {
    "\u0153": "oe", "\u0152": "OE",   # œ Œ  — Sœurs, cœur
    "\u00e6": "ae", "\u00c6": "AE",   # æ Æ
    "\u00df": "ss",                    # ß
    "\u00f8": "o",  "\u00d8": "O",    # ø Ø
    "\u0111": "d",  "\u0110": "D",    # đ Đ
    "\u0142": "l",  "\u0141": "L",    # ł Ł
}


def slugify(name: str) -> str:
    """
    District name -> url slug, matching the existing Open-North-derived ids.

    Em dashes, hyphens and apostrophes all collapse to a single '-', accents fold
    to ASCII, and periods drop. Verified against Ontario: 'Chatham-Kent—Leamington'
    -> 'chatham-kent-leamington', "Toronto—St. Paul's" -> 'toronto-st-pauls'.
    """
    # ⛔ LIGATURES FIRST — NFKD does not touch them. `œ` is a single character,
    # not an accented `o`, so it survives normalisation, survives the
    # combining-mark strip, and is then eaten by the `[^a-z0-9]+` rule below.
    # Montréal's `Champlain–L'Île-des-Sœurs` slugified to
    # `champlain-lile-des-s-urs` — the `œ` became a hyphen mid-word — and that id
    # was minted into the table.
    #
    # ★ The real defect was DIVERGENCE, not the mangling. `cpd_slugify`
    # (migration 0080) uses Postgres `unaccent()`, whose rules DO expand
    # ligatures, so the SQL side produced `champlain-lile-des-soeurs` while this
    # produced something else — and `qc_municipal_roster` joins roster names
    # slugified one way against ids minted the other. The two must agree, and
    # `check-boundary-coverage` now asserts that they do over every row.
    s = name
    for lig, expansion in _LIGATURES.items():
        s = s.replace(lig, expansion)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("'", "").replace("’", "").replace(".", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


# ── Readers ─────────────────────────────────────────────────────────────────

def _read_geojson(path: Path) -> Iterator[tuple[dict, dict]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    feats = doc.get("features") if doc.get("type") == "FeatureCollection" else [doc]
    for f in feats or []:
        geom = f.get("geometry")
        if geom and geom.get("coordinates"):
            yield f.get("properties") or {}, geom


def _open_shapefile_reader(zf: zipfile.ZipFile, member: Optional[str]):
    """
    Build a pyshp Reader over members of an open zip.

    ⚠ Encoding: `.cpg` sidecars carry an UPPERCASE extension on federal 2023,
    MB 2018, NWT, Nunavut and both Quebec archives. A case-sensitive `*.cpg` glob
    returns empty and every accented name mojibakes, so the lookup below is
    case-insensitive. Files that ship no `.cpg` at all (SK prior, MB 2008, BC 2015)
    are cp1252.
    """
    import shapefile  # pyshp

    names = zf.namelist()
    # ⚠ Exclude AppleDouble resource forks. A macOS-bundled archive carries a
    # `__MACOSX/._Foo.shp` stub alongside the real `Foo.shp`; picking the stub
    # yields an unreadable "shapefile" with no records. The nested-zip lookup
    # already filtered these (SK arrives inside a macOS bundle) and this path did
    # not, so an archive read with `zip_member=None` was exposed.
    base = member or next(
        (n for n in names
         if n.lower().endswith(".shp")
         and "__MACOSX" not in n
         and not Path(n).name.startswith("._")),
        None,
    )
    if base is None:
        raise ValueError("no .shp found in archive")
    if base.lower().endswith(".shp"):
        base = base[:-4]

    def pick(ext: str) -> Optional[str]:
        want = (base + ext).lower()
        return next((n for n in names if n.lower() == want), None)

    cpg = pick(".cpg")
    if cpg:
        raw = zf.read(cpg).decode("ascii", "ignore").strip().lower()
        enc = "utf-8" if "utf" in raw else (raw or "cp1252")
    else:
        enc = "cp1252"

    shp, dbf = pick(".shp"), pick(".dbf")
    if not shp or not dbf:
        raise ValueError(f"missing .shp or .dbf for {base!r} in archive")
    return shapefile.Reader(
        shp=zf.open(shp), dbf=zf.open(dbf), encoding=enc, encodingErrors="replace"
    )


def _read_shapefile(
    path: Path, member: Optional[str], nested_zip: Optional[str] = None
) -> Iterator[tuple[dict, dict]]:
    """Shapefile reader via `pyshp` — pure Python, no GDAL anywhere in this stack."""
    import shapefile  # pyshp

    if nested_zip:
        # ⚠ Saskatchewan: a zip inside a zip, wrapped in a macOS bundle. pyshp
        # needs seekable streams, so the inner archive is read fully into memory
        # (a few MB) rather than streamed.
        outer = zipfile.ZipFile(path)
        try:
            inner_name = next(
                (n for n in outer.namelist()
                 if n.lower() == nested_zip.lower() and "__MACOSX" not in n),
                None,
            )
            if inner_name is None:
                raise ValueError(f"{path}: nested archive {nested_zip!r} not found")
            with zipfile.ZipFile(io.BytesIO(outer.read(inner_name))) as inner:
                rdr = _open_shapefile_reader(inner, member)
                for sr in rdr.iterShapeRecords():
                    geom = sr.shape.__geo_interface__
                    if geom and geom.get("coordinates"):
                        yield sr.record.as_dict(), geom
                return
        finally:
            outer.close()

    if member or path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path)
        rdr = _open_shapefile_reader(zf, member)
    else:
        rdr = shapefile.Reader(str(path), encodingErrors="replace")

    for sr in rdr.iterShapeRecords():
        geom = sr.shape.__geo_interface__
        if geom and geom.get("coordinates"):
            yield sr.record.as_dict(), geom


def _read_esrijson(path: Path) -> Iterator[tuple[dict, dict]]:
    """
    Raw Esri JSON (`f=json`), which PEI's service serves because it advertises no
    GeoJSON output. Features carry `attributes` and `rings` rather than
    `properties` and `coordinates`.

    ⚠ Esri ring winding is the OPPOSITE of GeoJSON's: outer rings clockwise, holes
    counter-clockwise. PostGIS `ST_MakeValid` normalises either way, so the rings
    are passed through as a GeoJSON Polygon without reordering.
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    for f in doc.get("features") or []:
        rings = (f.get("geometry") or {}).get("rings")
        if rings:
            yield f.get("attributes") or {}, {"type": "Polygon", "coordinates": rings}


def read_features(root: Path, spec: BoundarySpec) -> list[tuple[dict, dict]]:
    """All features across every source file in the spec, concatenated."""
    paths = [spec.source_path] if isinstance(spec.source_path, str) else list(spec.source_path)
    if spec.zip_member is None or isinstance(spec.zip_member, str):
        members: list[Optional[str]] = [spec.zip_member] * len(paths)
    else:
        members = list(spec.zip_member)
    if len(members) != len(paths):
        raise ValueError(
            f"{spec.jurisdiction}: {len(paths)} source_path(s) but "
            f"{len(members)} zip_member(s) — they must be parallel"
        )

    out: list[tuple[dict, dict]] = []
    for rel, member in zip(paths, members):
        path = root / rel
        if not path.exists():
            raise FileNotFoundError(f"{spec.jurisdiction}: source not staged: {path}")
        suffix = path.suffix.lower()
        if suffix in (".geojson",):
            got = list(_read_geojson(path))
        elif suffix == ".json":
            # Distinguish GeoJSON from raw Esri JSON by inspecting the payload,
            # not the extension — PEI ships .json and it is Esri.
            head = path.read_text(encoding="utf-8")[:400]
            got = list(_read_esrijson(path) if '"esriGeometry' in head or '"rings"' in head
                       else _read_geojson(path))
        else:
            got = list(_read_shapefile(path, member, spec.nested_zip))
        log.info("%s: %s -> %d features", spec.jurisdiction, rel, len(got))
        out.extend(got)
    return out


# ── Loader ──────────────────────────────────────────────────────────────────

@dataclass
class LoadStats:
    jurisdiction: str = ""
    features_read: int = 0
    distinct_ids: int = 0
    inserted: int = 0
    updated: int = 0
    rejected: int = 0
    filtered_out: int = 0
    parts_merged: int = 0
    slug_matches_existing: int = 0
    slug_new: int = 0
    # Reported so a correction that stops matching (because the agency fixed its
    # own data) shows up as 0 rather than passing unnoticed.
    name_fixups_applied: int = 0
    problems: list[str] = field(default_factory=list)


def group_features(
    feats: list[tuple[dict, dict]], spec: BoundarySpec, st: "LoadStats"
) -> dict[str, dict[str, Any]]:
    """
    Features -> one entry per district, applying the spec's row filter and
    accumulating every geometry part under its district key.

    Shared by the loader and by `compare_boundaries` deliberately: if the two
    grouped differently, a clean `--compare` would not predict what the load
    actually writes.
    """
    rows: dict[str, dict[str, Any]] = {}
    for props, geom in feats:
        # ⛔ Drop junk rows before anything else. PEI ships 26 features with
        # DIST_NO = 0 and a blank name; without this they mint a phantom district.
        if spec.row_filter is not None and not spec.row_filter(props):
            st.filtered_out += 1
            continue

        # ⚠ str(): a numeric name_field is normal, not exotic. Regina's is `ID`
        # (an int ward number) and GeoJSON preserves the JSON type, so
        # `(props.get(...) or "").strip()` raised AttributeError on an int and
        # killed the run BEFORE `name_builder` — which exists precisely to turn
        # that number into a label — ever got to see it.
        raw_name = str(props.get(spec.name_field) or "").strip()
        if spec.name_fixups:
            fixed = spec.name_fixups.get(raw_name)
            if fixed is not None:
                st.name_fixups_applied += 1
                raw_name = fixed
        split_fr: Optional[str] = None
        if spec.name_builder:
            built = spec.name_builder(props)
            if built:
                raw_name = built

        if spec.name_split and raw_name:
            bits = [b.strip() for b in raw_name.split(spec.name_split)]
            bits = [b for b in bits if b]
            if len(bits) > 2:
                st.problems.append(
                    f"{raw_name!r}: {len(bits)} parts on {spec.name_split!r}, "
                    f"expected at most 2 — taking the first two"
                )
            raw_name = bits[0] if bits else ""
            split_fr = bits[1] if len(bits) > 1 else None

        # ★ Identity. Two different things are going on here, and conflating them
        # is what made the previous version of this function a silent no-op: both
        # branches computed the same slug and the dissolve key was discarded.
        #
        #   • WITHOUT `dissolve_by` the source ships one record per district (or
        #     several for an island multi-part), so the district name IS the
        #     identity and an empty name is a rejectable defect.
        #
        #   • WITH `dissolve_by` the source ships POLLING DIVISIONS — NS 1,817 for
        #     56, PEI 270 for 27 — and the district-identifying field is the
        #     identity. The name is then a label carried redundantly on every
        #     division, and polling-division files routinely leave it blank on
        #     some rows. Rejecting those would drop real geometry out of the union
        #     and leave a district quietly missing a piece — which
        #     `expect_districts` cannot see, because the district still exists via
        #     its other rows.
        # ⛔ Resolve the owning set FIRST — it widens the group key. Two
        # municipalities in the same aggregator both having a "Ward 1" is the
        # normal case, not the exception.
        if spec.set_resolver:
            row_set = spec.set_resolver(props)
            if not row_set:
                st.rejected += 1
                st.problems.append(
                    f"feature (name={raw_name!r}) resolves to no owning set — "
                    f"it cannot be attributed to a municipality"
                )
                continue
        else:
            row_set = spec.source_set

        if spec.dissolve_by:
            key_raw = props.get(spec.dissolve_by)
            if key_raw is None or str(key_raw).strip() == "":
                st.rejected += 1
                st.problems.append(
                    f"feature with empty {spec.dissolve_by} (name={raw_name!r}) "
                    f"— cannot be attributed to a district"
                )
                continue
            gkey = f"{row_set}\x00{str(key_raw).strip()}"
        else:
            if not raw_name:
                st.rejected += 1
                st.problems.append(f"feature with empty {spec.name_field}")
                continue
            gkey = (f"{row_set}\x00"
                    f"{slugify(str(props.get(spec.slug_field) or raw_name))}")

        # ⛔ What the constituency_id slug is built FROM. Usually the district
        # name, but `slug_field` overrides it: federal ids are keyed on the
        # numeric FED_NUM (`federal-electoral-districts/10001`) because Elections
        # Canada's names are long, bilingual, em-dashed and periodically
        # re-spelled, and the number is the stable identity.
        slug_src = (
            str(props.get(spec.slug_field) or "").strip()
            if spec.slug_field else raw_name
        )

        aid = props.get(spec.authority_id_field) if spec.authority_id_field else None
        existing = rows.get(gkey)
        if existing is None:
            existing = rows[gkey] = {
                "group_key": gkey,
                "source_set": row_set,
                "name": None,
                "name_fr": None,
                "authority_district_id": None,
                "province_territory": None,
                # Every distinct spelling seen in this group, for the consistency
                # check below.
                "_names": Counter(),
                # Kept separately from _names: with slug_field set these differ,
                # and the id must follow the slug source while the display name
                # follows the name field.
                "_slugs": Counter(),
                # ⛔ Accumulate every part. Both multi-part districts (islands
                # stored as separate records) and polling-division dissolves land
                # here, and PostGIS unions them in one code path.
                "geometries": [geom],
            }
        else:
            existing["geometries"].append(geom)

        if raw_name:
            existing["_names"][raw_name] += 1
        if slug_src:
            existing["_slugs"][slug_src] += 1
        if existing["name_fr"] is None:
            existing["name_fr"] = split_fr if spec.name_split else (
                (props.get(spec.name_fr_field) or None)
                if spec.name_fr_field else None
            )
        if existing["authority_district_id"] is None and aid is not None:
            existing["authority_district_id"] = str(aid)
        if existing["province_territory"] is None and spec.province_resolver:
            existing["province_territory"] = spec.province_resolver(props)

    # ── Resolve each group to one constituency_id ───────────────────────────
    out: dict[str, dict[str, Any]] = {}
    for gkey, row in rows.items():
        names: Counter = row.pop("_names")
        slugs: Counter = row.pop("_slugs")
        if not names:
            # A dissolve group where EVERY division left the name blank. The
            # geometry is real, but there is nothing to slug — fail loudly rather
            # than mint `<prefix>/` and have the next such group collide with it.
            st.rejected += 1
            st.problems.append(
                f"{spec.dissolve_by}={gkey!r}: no feature carries a "
                f"{spec.name_field} — cannot derive a constituency_id"
            )
            continue

        # ⚠ Report, never silently pick. Divisions disagreeing on the spelling is
        # either a real upstream defect or a dissolve key that is too coarse, and
        # both need a human. The modal choice is a stopgap so the run still
        # produces a diagnosable result instead of splitting the district in two.
        if len(names) > 1:
            variants = ", ".join(f"{n!r}×{c}" for n, c in names.most_common())
            st.problems.append(
                f"{spec.dissolve_by or spec.name_field}={gkey!r}: "
                f"{len(names)} name spellings across its features ({variants}) "
                f"— taking the most common"
            )
        # ⚠ Built from the slug SOURCE, not from the display name — they are the
        # same string unless `slug_field` is set. Deriving the id from the name
        # here silently ignored slug_field and would have minted 343 name-based
        # federal ids matching none of the 342 FED_NUM-keyed rows we hold.
        row["name"] = names.most_common(1)[0][0]
        # ⚠ With `set_resolver` the prefix is the row's own set, not the spec's
        # scalar — an aggregator has no single correct prefix.
        prefix = row["source_set"] if spec.set_resolver else spec.id_prefix
        cid = f"{prefix}/{slugify((slugs.most_common(1)[0][0]) if slugs else row['name'])}"

        # ⛔ Two dissolve groups slugifying to the same id would union into one
        # district and take `distinct_ids` BELOW expectation — the failure mode
        # `expect_districts` reports with a misleading message pointing at the
        # wrong field. Catch it here, where the cause can actually be named.
        if cid in out:
            raise RuntimeError(
                f"{spec.jurisdiction}: {spec.dissolve_by or 'name'} values "
                f"{out[cid]['group_key'].split(chr(0))[-1]!r} and "
                f"{gkey.split(chr(0))[-1]!r} (set {row['source_set']!r}) "
                f"both slugify to {cid!r}. "
                f"Two distinct districts cannot share a constituency_id — the "
                f"dissolve key or the name field is wrong."
            )
        row["constituency_id"] = cid
        out[cid] = row
    return out


async def load_boundaries(
    db: Database,
    spec: BoundarySpec,
    data_root: str = "/data/boundaries",
    dry_run: bool = False,
) -> LoadStats:
    st = LoadStats(jurisdiction=spec.jurisdiction)
    feats = read_features(Path(data_root), spec)
    st.features_read = len(feats)

    rows = group_features(feats, spec, st)
    st.distinct_ids = len(rows)
    st.parts_merged = sum(len(r["geometries"]) - 1 for r in rows.values())

    # ⛔ Assert the district count BEFORE writing. NS dissolves 1,817 polling
    # divisions to 56 and PEI 270 to 27 — if either produced a different number
    # the filter or the dissolve key is wrong, and a plausible-looking wrong row
    # count is exactly what nobody notices.
    if spec.expect_districts is not None and st.distinct_ids != spec.expect_districts:
        raise RuntimeError(
            f"{spec.jurisdiction}: expected {spec.expect_districts} districts, "
            f"resolved {st.distinct_ids} from {st.features_read} features "
            f"(filtered {st.filtered_out}, rejected {st.rejected}). "
            f"Check row_filter / dissolve_by / name_field."
        )

    # ⛔ Aggregator assertions. `expect_districts` counts across every set at
    # once, so a municipality mapped to the wrong slug moves rows between sets
    # without moving the total — invisible to the total-count check alone.
    if spec.set_resolver:
        per_set: Counter = Counter(r["source_set"] for r in rows.values())
        if spec.expect_sets is not None and len(per_set) != spec.expect_sets:
            raise RuntimeError(
                f"{spec.jurisdiction}: expected {spec.expect_sets} owning sets, "
                f"resolved {len(per_set)} from {st.features_read} features. "
                f"Check set_resolver — a name it does not recognise either "
                f"collapses into another set or mints a new one."
            )
        # ⚠ Report, do not fail: an authority id reused across two owning bodies
        # is the PUBLISHER's defect, and it does not threaten our identity —
        # `constituency_id` is per-set and still distinct. Nova Scotia issues
        # `BWAL` to both Bridgewater and Berwick, and both also carry
        # `mu_code = BW`. 0091 scoped the uniqueness index to `source_set` so
        # this loads; this keeps it from loading *silently*.
        by_aid: dict = {}
        for r in (rows.values() if spec.authority_id_unique_across_sets else ()):
            aid = r.get("authority_district_id")
            if aid:
                by_aid.setdefault(aid, set()).add(r["source_set"])
        for aid, in_sets in sorted(by_aid.items()):
            if len(in_sets) > 1:
                st.problems.append(
                    f"authority id {aid!r} is issued to {len(in_sets)} different "
                    f"owning sets ({', '.join(sorted(in_sets))}) — an upstream "
                    f"duplicate; our constituency_ids stay distinct"
                )

        if spec.expect_per_set:
            wrong = {
                k: (per_set.get(k, 0), v)
                for k, v in spec.expect_per_set.items()
                if per_set.get(k, 0) != v
            }
            if wrong:
                raise RuntimeError(
                    f"{spec.jurisdiction}: per-set district counts wrong "
                    f"(got, expected): {wrong}. A set at 0 means set_resolver "
                    f"never produced that slug."
                )

    existing = {
        r["constituency_id"]
        for r in await db.fetch(
            "SELECT constituency_id FROM constituency_boundaries "
            # ⚠ Same national-spec caveat as in compare_boundaries: a spec with
            # province_territory=None must scope by level alone, or the
            # slug_matches_existing figure reads 0 for every federal district.
            "WHERE ($1::text IS NULL "
            "       OR province_territory IS NOT DISTINCT FROM $1) "
            "  AND level = $2",
            spec.province_territory, spec.level,
        )
    }
    # Compare on the generation-free form so a pending prefix change doesn't read
    # as 124 brand-new districts.
    existing_slugs = {e.split("/", 1)[1] for e in existing if "/" in e}
    for cid in rows:
        if cid.split("/", 1)[1] in existing_slugs:
            st.slug_matches_existing += 1
        else:
            st.slug_new += 1

    if dry_run:
        return st

    for cid, r in rows.items():
        try:
            # Rule 1 — reproject, never relabel. ST_Multi because sources mix
            # Polygon and MultiPolygon and the column is MultiPolygon.
            res = await db.fetchval(
                f"""
                WITH parts AS (
                  -- ⚠ ST_MakeValid runs HERE, per part, BEFORE the union — not
                  -- after it. Reprojection happens in this CTE, so a ring that
                  -- self-intersects as a result of it is invalid on the way IN
                  -- to ST_UnaryUnion. Repairing only the union's output means
                  -- feeding GEOS the bad ring first and hoping OverlayNG
                  -- survives; when it does not, the run aborts with a
                  -- TopologyException blaming the declared CRS.
                  SELECT ST_MakeValid({spec.source_crs_sql("ST_GeomFromGeoJSON(gj)")}) AS g
                    FROM unnest($1::text[]) AS t(gj)
                ), src AS (
                  -- One row per district regardless of how many parts arrived.
                  -- ST_UnaryUnion dissolves shared edges between polling
                  -- divisions; the outer ST_MakeValid catches anything the
                  -- union itself introduces.
                  SELECT ST_Multi(ST_CollectionExtract(
                           ST_MakeValid(ST_UnaryUnion(ST_Collect(g))), 3)) AS g
                    FROM parts
                )
                INSERT INTO constituency_boundaries
                  (constituency_id, name, name_fr, level, province_territory,
                   source_set, authority, authority_district_id, boundary_kind,
                   boundary, boundary_simple, centroid, area_sqkm,
                   boundaries_version, effective_from, effective_to)
                SELECT $2, $3, $4, $5, $6, $7, $8, $9, $10,
                       src.g,
                       ST_Multi(ST_CollectionExtract(ST_MakeValid(
                         ST_Simplify(src.g, {SIMPLIFY_TOLERANCE})), 3)),
                       ST_Centroid(src.g),
                       ST_Area(src.g::geography) / 1000000,
                       $11, $12, $13
                  FROM src
                ON CONFLICT (constituency_id, boundaries_version) DO UPDATE SET
                  name = EXCLUDED.name, name_fr = EXCLUDED.name_fr,
                  level = EXCLUDED.level,
                  province_territory = EXCLUDED.province_territory,
                  source_set = EXCLUDED.source_set,
                  authority = EXCLUDED.authority,
                  authority_district_id = EXCLUDED.authority_district_id,
                  boundary_kind = EXCLUDED.boundary_kind,
                  boundary = EXCLUDED.boundary,
                  boundary_simple = EXCLUDED.boundary_simple,
                  centroid = EXCLUDED.centroid,
                  area_sqkm = EXCLUDED.area_sqkm,
                  -- ⛔ effective_from / effective_to are DELIBERATELY NOT updated.
                  -- They are set once at insert and thereafter owned by the
                  -- cutover migrations, which are the only thing that knows a
                  -- generation has been retired. With them in this list, re-running
                  -- a spec resets effective_to to the spec's value (NULL) and
                  -- silently un-retires a generation that a migration had
                  -- end-dated — resurrecting it alongside its successor so every
                  -- district in that jurisdiction returns two rows.
                  --
                  -- This matters the moment Quebec's 2017 map is end-dated to
                  -- 2026-08-28 ahead of the 2026 map going live on the 29th: a
                  -- stray re-run of the 2017 spec would undo the cutover.
                  updated_at = now()
                RETURNING (xmax = 0) AS inserted
                """,
                [json.dumps(g) for g in r["geometries"]],
                cid, r["name"], r["name_fr"], spec.level,
                r.get("province_territory") or spec.province_territory,
                r.get("source_set") or spec.source_set,
                spec.authority, r["authority_district_id"],
                spec.boundary_kind,
                spec.boundaries_version, spec.effective_from, spec.effective_to,
            )
            if res:
                st.inserted += 1
            else:
                st.updated += 1
        except Exception as exc:
            # Rule 4 — do not swallow. A rejected geometry usually means the
            # declared EPSG is wrong, and a partial load is worse than none.
            raise RuntimeError(
                f"{spec.jurisdiction}: {cid} failed to load "
                f"(source CRS: {spec.src_proj4 or f'EPSG:{spec.src_epsg}'}) — {exc}"
            ) from exc

    return st


# ── Non-destructive vintage comparison ──────────────────────────────────────

@dataclass
class CompareStats:
    jurisdiction: str = ""
    authoritative: int = 0
    held: int = 0
    matched: int = 0
    mean_overlap: float = 0.0
    min_overlap: float = 0.0
    below_95: int = 0
    only_authoritative: list[str] = field(default_factory=list)
    only_held: list[str] = field(default_factory=list)
    worst: list[tuple[str, float]] = field(default_factory=list)
    # ⚠ --compare used to hand group_features a throwaway LoadStats, so every
    # rejection, filter and name-spelling conflict raised while grouping was
    # discarded. A comparison could look clean while the same grouping under
    # `load` logged dozens of problems — which defeats the point of running
    # --compare first.
    rejected: int = 0
    filtered_out: int = 0
    problems: list[str] = field(default_factory=list)


async def compare_boundaries(
    db: Database, spec: BoundarySpec, data_root: str = "/data/boundaries",
) -> CompareStats:
    """
    Measure staged authoritative geometry against what we already hold, WITHOUT
    writing anything.

    This is ruling A7 as a tool. A matching district count proves nothing — NWT,
    Nova Scotia, Saskatchewan and Calgary all had a perfect count and wrong
    geometry, because a redistribution can redraw districts while preserving both
    their names and their number. Only measured overlap distinguishes "our rows
    are the current generation" from "our rows are the previous one wearing
    current names".

    Reports intersection-over-larger per district, which is symmetric and does not
    reward a polygon merely for being big.

    ⚠ Interpretation depends on lineage. If our rows and the staged file descend
    from the SAME publisher, near-perfect overlap is expected and says nothing
    about currency. Cross-publisher comparisons additionally risk a drawing-
    convention artefact (water clipped vs not), which shows up as a uniform
    coastal-district penalty rather than a redistribution signature.
    """
    feats = read_features(Path(data_root), spec)
    st = CompareStats(jurisdiction=spec.jurisdiction)

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "CREATE TEMP TABLE _cmp (slug text primary key, "
                "g geometry(MultiPolygon,4326)) ON COMMIT DROP"
            )
            # ⛔ What counts as the same district on both sides.
            #
            # Normally the bare SLUG, deliberately: a cutover compares a new
            # generation against a differently-prefixed old one
            # (`…-districts-2018/x` vs `…-districts/x`), and keying on the full
            # id would report every district as new.
            #
            # ⚠ For an AGGREGATOR the prefix is the municipality, so the slug
            # alone is neither unique nor meaningful: 24 Nova Scotian towns elect
            # at large and all 24 slug to `at-large`, which collides on the
            # primary key before it can even mis-match. Key on the full id there.
            key_sql = ("constituency_id" if spec.set_resolver
                       else "split_part(constituency_id,'/',2)")

            # ⛔ And scope the HELD side to the spec's own set when the spec is
            # municipal. Municipal slugs collide constantly — `ward-4` exists in
            # Calgary, Strathcona County and Wood Buffalo — so a slug-keyed join
            # across a whole province silently compares Calgary's Ward 4 against
            # a county division 300 km away. Measured on Calgary: 26 "matches"
            # for 14 districts, five of them at 0.00% overlap, and a mean of
            # 49.77% that means nothing at all.
            #
            # ⚠ NOT applied to provincial/federal specs. There the whole point of
            # the slug key is to match ACROSS a generation whose set or prefix
            # changed (`…-districts-2018` vs `…-districts`), and scoping by
            # source_set would report every district as new — turning a cutover
            # comparison into no comparison.
            # Same grouping the loader uses — filter, dissolve, accumulate parts.
            # If compare grouped differently, a clean result would not predict
            # what the load writes.
            gst = LoadStats(jurisdiction=spec.jurisdiction)
            grouped = group_features(feats, spec, gst)
            st.authoritative = len(grouped)
            st.rejected = gst.rejected
            st.filtered_out = gst.filtered_out
            st.problems = gst.problems

            # ⚠ Computed AFTER grouping: an aggregator's scope is the set list it
            # just resolved, which does not exist until the features are grouped.
            if spec.set_resolver:
                # ⚠ An aggregator has no single set to scope to, but it does have
                # the set LIST it just resolved. Without this the report counts
                # every municipal row in the province as "held" and lists all of
                # them as "we hold, authority does not" — 365 lines of Ajax and
                # Belleville around 26 real findings.
                held_scope = "AND source_set = ANY($3::text[])"
                held_args = [sorted({r["source_set"] for r in grouped.values()})]
            elif spec.level == "municipal":
                held_scope = "AND source_set = $3"
                held_args = [spec.compare_held_source_set or spec.source_set]
            else:
                held_scope = ""
                held_args = []
            for cid, r in grouped.items():
                await conn.execute(
                    f"""
                    WITH parts AS (
                      -- ⚠ MakeValid per part, before the union — see the loader's
                      -- insert for why. Compare must reproduce the load exactly.
                      SELECT ST_MakeValid(
                               {spec.source_crs_sql("ST_GeomFromGeoJSON(gj)")}) AS g
                        FROM unnest($2::text[]) AS t(gj)
                    )
                    INSERT INTO _cmp (slug, g)
                    SELECT $1, ST_Multi(ST_CollectionExtract(
                             ST_MakeValid(ST_UnaryUnion(ST_Collect(g))), 3))
                      FROM parts
                    """,
                    cid if spec.set_resolver else cid.split("/", 1)[1],
                    [json.dumps(g) for g in r["geometries"]],
                )

            rows = await conn.fetch(
                f"""
                WITH held AS (
                  -- ⚠ ST_MakeValid on the HELD side too. The authoritative side
                  -- is repaired when _cmp is built, but our own rows are not
                  -- necessarily valid: the Open North mirror was written without
                  -- any validity step, and PEI's held polygons carry a
                  -- self-intersection at (-64.0415, 46.4280) that made
                  -- ST_Intersection raise a TopologyException and abort the whole
                  -- comparison. A vintage check must not be defeated by the
                  -- quality of the data it exists to assess.
                  SELECT {key_sql} AS slug,
                         ST_MakeValid(boundary) AS g
                    FROM constituency_boundaries
                   WHERE level = $1
                     -- ⚠ A NATIONAL spec carries province_territory=None while
                     -- every held federal row carries a real province, so
                     -- `IS NOT DISTINCT FROM NULL` matched nothing and --compare
                     -- reported held=0 for all 343 federal districts. When the
                     -- spec declares no province, scope by level alone.
                     AND ($2::text IS NULL
                          OR province_territory IS NOT DISTINCT FROM $2)
                     AND effective_from <= CURRENT_DATE
                     AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                     {held_scope}
                )
                SELECT c.slug,
                       ST_Area(ST_Intersection(c.g, h.g))
                         / greatest(ST_Area(c.g), ST_Area(h.g)) AS overlap
                  FROM _cmp c JOIN held h USING (slug)
                """,
                spec.level, spec.province_territory, *held_args,
                # ⚠ Ten minutes, against the pool's 60s default. This single
                # query does a full-resolution ST_Intersection per district, and
                # Newfoundland's 1:50,000 coastline blew straight through the
                # default — 40 districts of fjord at ~10x the vertex count of a
                # prairie province. Raising it here rather than on the pool keeps
                # the ingest paths on the short timeout, where a 60s query really
                # does mean something is wrong.
                # ⛔ Do not "fix" this by comparing boundary_simple instead: that
                # would measure our simplification tolerance, not the vintage the
                # check exists to establish.
                timeout=600,
            )
            # ⚠ Scoped exactly like the match above. Unscoped it reported
            # `held=53` for Calgary — every municipal row in Alberta — next to
            # `authoritative=14`, which reads as a catastrophic shortfall rather
            # than as a comparison against 14 of Calgary's own wards.
            st.held = await conn.fetchval(
                f"""SELECT count(*) FROM constituency_boundaries
                    WHERE level=$1
                      AND ($2::text IS NULL OR province_territory IS NOT DISTINCT FROM $2)
                      AND effective_from <= CURRENT_DATE
                      AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                      {held_scope}""",
                spec.level, spec.province_territory, *held_args,
            )
            st.only_authoritative = [
                r["slug"] for r in await conn.fetch(
                    f"""SELECT slug FROM _cmp WHERE slug NOT IN (
                         SELECT {key_sql}
                           FROM constituency_boundaries
                          WHERE level=$1
                            AND ($2::text IS NULL
                                 OR province_territory IS NOT DISTINCT FROM $2)
                            {held_scope})
                       ORDER BY slug""",
                    spec.level, spec.province_territory, *held_args)
            ]
            st.only_held = [
                r["slug"] for r in await conn.fetch(
                    f"""SELECT {key_sql} AS slug
                         FROM constituency_boundaries
                        WHERE level=$1
                      AND ($2::text IS NULL OR province_territory IS NOT DISTINCT FROM $2)
                          AND effective_from <= CURRENT_DATE
                          AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                          AND {key_sql} NOT IN (SELECT slug FROM _cmp)
                          {held_scope}
                        ORDER BY 1""",
                    spec.level, spec.province_territory, *held_args)
            ]

    vals = [float(r["overlap"]) for r in rows if r["overlap"] is not None]
    st.matched = len(vals)
    if vals:
        st.mean_overlap = sum(vals) / len(vals)
        st.min_overlap = min(vals)
        st.below_95 = sum(1 for v in vals if v < 0.95)
        st.worst = sorted(
            ((r["slug"], float(r["overlap"])) for r in rows if r["overlap"] is not None),
            key=lambda t: t[1],
        )[:5]
    return st

# ── Jurisdiction registry ───────────────────────────────────────────────────
#
# One entry per (jurisdiction, generation). Grows as each dossier's source is
# cleared; the loader itself never changes.

def _province_from_fed_num(props: dict) -> str:
    """Derive the province from the first two digits of FED_NUM.

    ⛔ No Elections Canada file carries a province column — only StatCan's does,
    and StatCan's cartographic boundaries are a CLIP rather than a
    generalisation (they are larger, not simpler), so they are not a substitute.
    The first two digits of FED_NUM are the Standard Geographical Classification
    province code and are stable across representation orders, so deriving is
    exact rather than a heuristic.
    """
    pr = {
        "10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON",
        "46": "MB", "47": "SK", "48": "AB", "59": "BC", "60": "YT", "61": "NT",
        "62": "NU",
    }
    code = str(props.get("FED_NUM") or "").strip()
    return pr.get(code[:2])




# ── Municipal aggregator helpers ────────────────────────────────────────────
# Promoted from `_draft_specs/`; see the two municipal SPECS entries below.

# Nova Scotia municipal polling districts — one province-wide file, 49
# municipalities, from data.novascotia.ca dataset `gcep-xeci`.
#
# ★ The first AGGREGATOR spec: one file fanning out into many source_sets via
# `set_resolver`. NS ships 238 districts across 49 municipalities and we
# currently read 2 of them.
#
# ⛔ HALIFAX AND CAPE BRETON ARE DELIBERATELY EXCLUDED, and this is the whole
# reason the spec has a row_filter. The province's file has NO district name
# field — `poll_dist` is a code (`HX07`), not a label — while the 28 rows we
# already hold for those two are properly named (`Halifax Peninsula North`,
# `Dartmouth Centre`) and carry 28 sitting councillors attached by those slugs.
# Loading codes over them would rename every district to `hx07`-style ids and
# orphan the entire roster of both councils, to gain nothing: Halifax already
# reconciles 16 of 16 against the authoritative layer and Cape Breton 12 of 12.
#
# ⚠ 24 of the remaining 47 municipalities have exactly ONE polling district —
# small towns that elect their whole council at large, which the code itself
# spells out (`WOAL` = Wolfville, at large). They are loaded as one district
# covering the town, which is what the province publishes.
#
# ⓘ We hold no roster for any of the 47, so nothing attaches yet. That is the
# point: a postcode in Truro or Annapolis Royal currently returns no municipal
# answer at all.
#
# Licence: Nova Scotia Open Government Licence (novascotia.ca/opendata/licence.asp)
# — one of only two municipal sources in the corpus with a named, linked licence.


# `poll_dist` is `<mu_code><suffix>` where suffix is a zero-padded number, `W<n>`
# for towns that number wards, or `AL` for at-large.
_NS_SUFFIX = re.compile(r"^(?P<mu>[A-Z]+?)(?P<kind>W?)(?P<num>\d+)$|^(?P<mu2>[A-Z]+)AL$")


def _ns_label(props: dict) -> str | None:
    """
    `poll_dist` code -> display name. `AN01` -> District 1, `TUW1` -> Ward 1,
    `WOAL` -> At Large.

    ⛔ The `W` is ambiguous and the ambiguity is not hypothetical: two NS
    municipal codes END in W (`BW` Bridgewater/Berwick, `SW`). For a code like
    `SW01` the pattern can read `SW` + `01` (District 1) or `S` + `W` + `01`
    (Ward 1) — and since the slug is derived from this label, picking wrong is
    an IDENTITY error, not a cosmetic one: `ward-1` and `district-1` are
    different constituency_ids.

    So the parse is verified against the province's own `mu_code` and a
    disagreement aborts the run. Checked across all 238 features at 0 mismatches;
    this is what keeps that true when NS adds a municipality.
    """
    code = (props.get("poll_dist") or "").strip().upper()
    mu_code = (props.get("mu_code") or "").strip().upper()
    m = _NS_SUFFIX.match(code)
    if not m:
        return None
    if m.group("mu2"):
        if mu_code and m.group("mu2") != mu_code:
            raise RuntimeError(
                f"nova-scotia-municipal: at-large code {code!r} implies "
                f"mu_code {m.group('mu2')!r} but the feature declares "
                f"{mu_code!r} ({props.get('mun')!r})"
            )
        return "At Large"
    if mu_code and m.group("mu") != mu_code:
        raise RuntimeError(
            f"nova-scotia-municipal: code {code!r} parses as prefix "
            f"{m.group('mu')!r} + {'W' if m.group('kind') else ''}"
            f"{m.group('num')!r}, but the feature declares mu_code {mu_code!r} "
            f"({props.get('mun')!r}). The W is ambiguous for mu_codes ending in "
            f"W and the slug derives from this label — refusing to guess."
        )
    num = int(m.group("num"))
    return f"Ward {num}" if m.group("kind") == "W" else f"District {num}"


def _ns_slugify_mun(name: str) -> str:
    """
    Municipality display name -> our source_set slug.

    ⛔ `-town` IS LOAD-BEARING, not decoration. In Nova Scotia a town and the
    county surrounding it are SEPARATE municipalities with separate councils and
    the same name: Antigonish, Digby, Lunenburg, Pictou, Shelburne and Yarmouth
    each appear twice in this file. Stripping the type merged six pairs of real
    councils — 49 municipalities resolved to 41 slugs, caught by `expect_sets`.

    ⚠ Applied to every town, not only the six that collide. A rule that fires
    only on today's collisions silently breaks when NS next incorporates a town
    named after its county, and the loss would be a merge — the hardest kind of
    error to notice, because the row count still looks plausible.
    """
    s = name.strip()
    if s.startswith("Town of "):
        return slugify(s[len("Town of "):]) + "-town"
    for prefix in (
        "Municipality of the County of ", "Municipality of the District of ",
        "Municipality of ", "Region of ", "District of ",
    ):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    for suffix in (" Regional Municipality", " Municipality"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    return slugify(s)


def _ns_set_for(props: dict) -> str | None:
    mun = (props.get("mun") or "").strip()
    if not mun:
        return None
    return f"{_ns_slugify_mun(mun)}-districts"


# New Brunswick local-government and rural-district wards — one province-wide
# file, from gnb.socrata.com dataset `7zs3-pcvk`.
#
# 330 wards across 94 owning bodies (78 local governments + 16 rural districts).
# We currently read 3 of them.
#
# ⛔ THREE TRAPS, all of which silently produce a plausible-looking wrong result.
#
# 1. `name_e` IS NOT A NAME. It is the literal string "Ward" on all 330 rows
#    (`name_f` is "Quartier"). Filtering or naming on it yields one district
#    called "Ward" for the entire province. The ward number is `ward`; the owning
#    body is `elect_comm`.
#
# 2. `elect_comm` IS NOT UNIQUE. Four names are used by BOTH a local government
#    and a rural district — Butternut Valley, District of Tobique Valley,
#    Nouvelle-Arcadie, and Southwest rural district. Keying the set on the name
#    alone merges four pairs of distinct bodies, which `expect_sets` catches. The
#    slug therefore carries the type.
#
#    ⚠ `eng_label` is no help: the RD codes are not unique either — RD5, RD8 and
#    RD12 are each shared by two rural districts.
#
# 3. ONE ROW HAS NO `elect_comm` AT ALL. See `_set_for` for how it is attributed,
#    and why that is an inference rather than a lookup.
#
# ★ Fredericton is the vintage proof. The authoritative ward labels are
# 1..12 PLUS `4-Lincoln` — thirteen. We hold twelve. That sub-ward exists because
# Lincoln was annexed under NB's 2023 local governance reform, so our NB sets are
# demonstrably pre-reform.
#
# ⓘ GeoNB (`geonb.snb.ca/downloads/lg/geonb_lg_gl_wards_quartiers_shp.zip`) is
# the publisher of record and is live. Socrata is used purely for format —
# GeoJSON with server-side filtering versus a zipped shapefile. The licence
# conclusion (Open Government Licence – New Brunswick) is unaffected by that
# choice.


_NB_TYPE_SUFFIX = {"LG": "-wards", "RD": "-rural-district-wards"}


def _nb_english(name: str) -> str:
    """
    The English half of a bilingual `elect_comm`.

    Rural districts are published as "Kent rural district / District rural de
    Kent"; local governments are single-form. Splitting unconditionally is safe
    because no single-form name contains a slash.
    """
    return name.split("/")[0].strip()


def _nb_core(name: str) -> str:
    """Drop the legal-status wrapper so the slug is the place, not its status."""
    s = _nb_english(name)
    for prefix in (
        "The City of ", "City of ", "Town of ", "Village of ",
        "Regional Municipality of ", "Rural Community of ",
        "Municipality of ", "Municipalité de ", "Municipalité régionale de ",
        "District of ", "Districts of ",
    ):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # "Southwest rural district" -> "Southwest"; the suffix is re-added by type,
    # so without this the slug reads `…-rural-district-rural-district-wards`.
    s = re.sub(r"\s+rural district$", "", s, flags=re.IGNORECASE)
    return s.strip()


def _nb_set_for(props: dict) -> str | None:
    kind = (props.get("type") or "").strip().upper()
    name = (props.get("elect_comm") or "").strip()

    if not name:
        # ⛔ THE ONE UNATTRIBUTED ROW. Exactly one feature in the file has a null
        # `elect_comm`: type RD, `eng_label` RD2, ward 2.
        #
        # Attributed to Restigouche on two independent lines of evidence:
        #
        #   • RD2 names Restigouche UNIQUELY among the 15 labelled rural
        #     districts, and Restigouche is published with ward 1 only — so a
        #     ward 2 labelled RD2 has exactly one home.
        #   • It shares a 52.0 km border with Restigouche ward 1, its longest by
        #     a wide margin (Chaleur 40.5 km, Greater Miramichi 34.6 km).
        #
        # ⚠ Stated as an INFERENCE, not a lookup. Narrowly conditioned on the row
        # we actually examined, so a second null row — or a different one —
        # falls through and is rejected loudly rather than silently inheriting
        # this attribution.
        if kind == "RD" and (props.get("eng_label") or "").strip().upper() == "RD2" \
                and str(props.get("ward") or "").strip() == "2":
            return "restigouche-rural-district-wards"
        return None

    suffix = _NB_TYPE_SUFFIX.get(kind)
    if not suffix:
        return None
    return slugify(_nb_core(name)) + suffix


def _nb_label(props: dict) -> str | None:
    ward = str(props.get("ward") or "").strip()
    if not ward:
        return None
    # At-large bodies carry the bilingual literal "At-Large / Général" in the
    # ward field itself.
    if ward.lower().startswith("at-large"):
        return "At Large"
    return f"Ward {ward}"


# Calgary wards — City of Calgary open data, Socrata `tz8z-hyaz`.
#
# ⛔ THE THIRD CONFIRMED A7 CASE, after SK (61 -> 61) and NT (19/19).
# Our 14 held rows match the SUPERSEDED 2017–2021 generation at mean 0.36%
# (band 0.28–0.42%, 14/14 within 2%) and the current one at mean 4.76%,
# max 17.53%, only 6/14 within 2%. No ward matches the current generation better
# than it matches the old one. The count check passes perfectly at 14 -> 14,
# which is precisely A7's point: a full district count proves nothing.
#
# ⚠ A8.1's counter-argument noted and dismissed: Calgary is landlocked, so the
# offshore-envelope drawing convention that makes coastal comparisons unreliable
# cannot be what produces a 17.53% delta on Ward 11.
#
# Consequence today: addresses near Ward 11 resolve to the wrong councillor.
#
# ⚠ Licence unread — the dataset declares the literal string "See Terms of Use"
# with no termsLink. Recorded, not treated as a gate.

def _calgary_label(props: dict) -> str | None:
    num = str(props.get("ward_num") or "").strip()
    return f"Ward {num}" if num else None

# Edmonton wards — City of Edmonton open data, Socrata `nydb-6rce`.
#
# ✅ CORRECT VINTAGE ALREADY. Mean 0.55%, median 0.41%, max 1.44% across 12/12
# against the in-force 2021 wards, and all 12 councillor names match our roster.
# This load is a PROVENANCE and DATE upgrade, not a rescue.
#
# ⛔ 42 features, not 12. The file carries every generation and must be
# partitioned on `effdt_type`: 12 `Current` + 30 `Historical`. ⚠ The dataset
# title advertises "Future" wards and there are ZERO `Future` rows — the title
# is not evidence about the contents.
#
# ★ The in-force date comes from the DATA, not the title or the metadata:
# `Historical` ends 2021-10-17 and `Current` starts 2021-10-18 open-ended, with
# no break at the 2025 election. `rowsUpdatedAt` is not evidence of currency.
#
# ⓘ Edmonton publishes NO numeric ward id — `name_1` is the ward's
# Indigenous-language name and is the only identifier. The casing is deliberate
# Cree and Blackfoot orthography (`papastew`, `pihêsiwin`, `O-day'min`) and is
# preserved verbatim as the display name; only the slug folds it.
#
# ⚠ Licence unread — "See Terms of Use", no termsLink.

# Winnipeg electoral wards — City of Winnipeg open data, Socrata `t4cg-yaxs`.
#
# ✅ CORRECT VINTAGE. Mean 0.34%, median 0.35%, max 0.55% across the 14 wards we
# hold, and 14/14 councillor names match.
#
# ★ WE ARE MISSING EXACTLY ONE WARD: `Elmwood – East Kildonan` (ward 14,
# Councillor Emma Durand-Wood), identified two independent ways. 15 -> 15 here.
#
# ★ The in-force date was previously recorded as BLOCKED on "no dossier has a
# Manitoba municipal election date", with a guess of late October 2026. That was
# the wrong question: these boundaries are the 2018 redraw, and the dataset's own
# description says so — "updated in November of 2018 to reflect the new council
# wards". Ruling A10.4 then gives 2018-10-24, the election they first governed.
# Nothing was blocked on a future election.
#
# ⚠ Name normalisation is handled by `slugify`, not by a fixup: the city writes
# spaced hyphens (`Charleswood - Tuxedo - Westwood`) where we use em-dashes, and
# both collapse to the same slug.
#
# ⛔ Licence field is FLATLY WRONG — the dataset declares "Open Government
# Licence - Prince Edward Island" on a Manitoba dataset, a misconfigured picker.
# Recorded as unresolved rather than as OGL-PEI, which would be a false
# provenance claim.


# Toronto wards — City of Toronto open data (CKAN), dataset `city-wards`.
#
# ⓘ The only Ontario municipality in the corpus with a recorded source URL, and
# it is CKAN rather than the ArcGIS FeatureServer archetype the other ~47 use.
#
# ★ SOURCE_SET RE-KEY. We hold these as `toronto-wards-2018`, which puts the
# generation in the SET NAME — the thing rule 5 exists to prevent, and the same
# defect the NB and BC provincial cutovers had to unpick. The generation belongs
# in `boundaries_version`, where a future ward-model change (Toronto's has been
# litigated before) is a new version rather than a new set and a new public URL.
# Migration 0095 re-keys the held rows and the roster.
#
# ⛔ THE IN-FORCE DATE IS NOT THE FILE'S. Every feature carries
# `DATE_EFFECTIVE = 2018-08-07T14:11:06`, which is when the record was created in
# Toronto's GIS — and it PRECEDES the Royal Assent of the statute that created
# the 25-ward model (the Better Local Government Act, 2018, S.O. 2018 c. 11,
# assented 2018-08-14). A metadata date that predates the law it supposedly
# reflects is a clean illustration of why A2 exists.
#
# Per A10.4 the municipal in-force date is the election these wards first
# governed: 2018-10-22.
#
# ⚠ `DATE_EXPIRY = 3000-01-01` is a sentinel, not a date. Left as
# `effective_to = None`.
#
# ⚠ Licence: CKAN reports `license_title: None` / "License not specified".
# Recorded, not treated as a gate.


# Regina wards — City of Regina, "NEW 2024 Ward Boundaries".
#
# ★ THE 403 DOES NOT REPRODUCE. The dossier recorded `www.regina.ca` as returning
# HTTP 403 to automated clients, with the browser-UA retry never attempted. It
# returns **200 to a plain curl** today. The block, whatever it was, is gone.
#
# ★ AND THE PUBLISHER IS FOUND. The city runs its own ArcGIS Server at
# `opengis.regina.ca`, and the layer is reachable from the AGOL item "2024 Ward
# Boundary Map" in the org `32Z5vyJw5sI48UUM` ("City of Regina"):
#
#   https://opengis.regina.ca/arcgis/rest/services/CGISViewer/WardsBoundaryReview2023/MapServer/0
#
# ⛔ How NOT to search for these: `/sharing/rest/search` on a city's OWN AGOL
# host is NOT scoped to that city — it queries the global index. Searching
# `regina.maps.arcgis.com` for "ward" returns Baltimore, Montana and Washington
# D.C., and the top "City of Regina" publisher guess (`DCGISopendata`) is
# Washington. Scope with `orgid:` from `/sharing/rest/portals/self`, or the
# results are worthless. This is the same failure the Ontario dossier recorded as
# "returns Nigeria, South Africa and Ohio ahead of Ontario" — it is not specific
# to keyword search, it is how the endpoint works.
#
# ⚠ `copyrightText` is empty, as it was for Saskatoon. The difference is
# categorical and worth stating: attribution here rests on the HOST — a
# city-owned domain under an AGOL org named "City of Regina" — not on a metadata
# field. Saskatoon's candidate is an anonymous item on a shared
# `services6.arcgis.com` tenant with `orgName: None`, which nothing identifies.
#
# ⛔ CRS TRAP. The staged GeoJSON is EPSG:26913 (NAD83 / UTM 13N) in PROJECTED
# METRES, carrying a legacy `crs` member; first coordinate is
# [535248.19, 5591196.13]. Declaring 4326 puts Regina in the Gulf of Guinea. The
# accompanying `.prj` has no AUTHORITY clause, so the code cannot be sniffed from
# it either — this is exactly why `src_epsg` is declared and never inferred.
#
# ⓘ The file carries no ward NAME — fields are OBJECTID, ID, POPULATION and two
# shape measures. `ID` is the ward number.

def _regina_label(props: dict) -> str | None:
    wid = props.get("ID")
    return f"Ward {int(wid)}" if wid is not None else None


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


# Niagara Region lower-tier ward boundaries — 44 wards across 12 municipalities,
# from the Region's own AGOL service.
#
# ★ FOUND VIA `orgid:`, which is the technique that makes Ontario tractable.
# A keyword search on a city's own AGOL host returns the GLOBAL index; scoping
# with the org id from `/sharing/rest/portals/self` returns two results instead
# of ten thousand.
#
#   org  WxiLK82TWf8W3O3f  "Niagara Region"
#   svc  services1.arcgis.com/WxiLK82TWf8W3O3f/.../VoterTool_data/FeatureServer/1
#
# ⓘ This is the FIRST ONTARIO AGGREGATOR, and it matters beyond Niagara: Ontario
# has no provincial ward layer because wards are created by local by-law, but an
# upper-tier REGION publishing a voter tool covers its lower-tier municipalities
# in one service. The same shape is worth probing for Peel, York, Durham,
# Halton and Waterloo before treating those as individual discoveries.
#
# ⛔ VINTAGE IS THE OPEN QUESTION AND IS DELIBERATELY MEASURED, NOT ASSUMED. The
# AGOL item's `modified` is 2018-10-17 — the 2018 municipal election — and
# Ontario has voted since (2022, and again on 2026-10-26). Grimsby in particular
# is on the list of Niagara municipalities with a recent ward review. Run
# `--compare` against the held sets before promoting this beyond Fort Erie.
#
# ⚠ Licence: the item carries a real `licenseInfo` (a Niagara Region reference-
# use disclaimer), unlike most of the municipal corpus. Recorded as such.

_NIAGARA_SETS = {
    # Our existing set names, where they differ from a plain slug.
    "Niagara-on-the-Lake": "niagara-on-the-lake-wards",
}

# ⛔ ST. CATHARINES IS EXCLUDED, and for the same reason Halifax and Cape Breton
# are excluded from the Nova Scotia aggregator: the aggregator is WORSE than what
# we already hold.
#
# St. Catharines' six wards have NAMES — Grantham, Merritton, Port Dalhousie,
# St. Andrew's, St. George's, St. Patrick's, two councillors each — and that is
# the form the city uses and residents recognise. The Region's voter tool numbers
# them 1..6.
#
# Loading it would mint six parallel numbered rows beside the six named ones and
# orphan all twelve St. Catharines councillors, to replace a name with an
# ordinal. Mapping number to name would need a crosswalk we do not have, and
# guessing it from geometry is not a thing to do quietly.
_EXCLUDED = {"St. Catharines"}


def _niagara_set(props: dict) -> str | None:
    mun = (props.get("MUNICIPALITY") or "").strip()
    if not mun:
        return None
    return _NIAGARA_SETS.get(mun, slugify(mun) + "-wards")


def _niagara_keep(props: dict) -> bool:
    return (props.get("MUNICIPALITY") or "").strip() not in _EXCLUDED


def _niagara_label(props: dict) -> str | None:
    """
    `WARD` -> display name.

    ⚠ `WARD` is not always a number. Niagara Falls elects its council at large
    and its single feature carries `WARD = "Councillor at Large"`, which a naive
    f-string turns into the district "Ward Councillor at Large" — and, since the
    slug follows the name, into the id `.../ward-councillor-at-large`. Anything
    non-numeric is the at-large case.
    """
    w = str(props.get("WARD") or "").strip()
    if not w:
        return None
    return f"Ward {w}" if w.isdigit() else "At Large"


# ── Ontario large-city ward labels ──────────────────────────────────────
# ⚠ Most Ontario publishers ship a bare ward NUMBER and no name at all, so the
# display name has to be built. Held rows already use the "Ward N" form, and the
# roster joins on the slug of that name, so a divergence here silently detaches
# a whole council.
def _on_ward_label(props: dict) -> str | None:
    """`WARD` as a bare number -> "Ward N"."""
    w = str(props.get("WARD") or "").strip()
    return f"Ward {w}" if w else None


def _on_ward_label_mixed(props: dict) -> str | None:
    """London ships `Ward`, mixed case — the only Ontario city that does."""
    w = str(props.get("Ward") or "").strip()
    return f"Ward {w}" if w else None


def _on_ward_titlecase(props: dict) -> str | None:
    """Brampton and Windsor ship `WARD` already prefixed but SHOUTING:
    "WARD 5" -> "Ward 5". Held rows are title case."""
    w = str(props.get("WARD") or "").strip()
    if not w:
        return None
    m = re.match(r"^\s*WARD\s+(\S+)\s*$", w, re.I)
    return f"Ward {m.group(1)}" if m else w


SPECS: dict[str, BoundarySpec] = {
    # ⚠ INTERNAL VALIDATION ONLY — not cleared for the public API.
    #
    # Two Ontario routes exist and the licences differ sharply:
    #
    #   Route A — Elections Ontario shapefiles under the *Open Use Data Product
    #     Licence Agreement*: commercial use and redistribution both explicit,
    #     no attribution clause. This is the one we want. It sits behind an
    #     "I Agree" button, which no agent may click, so it is NOT staged.
    #
    #   Route B — this MTO Authoritative AGOL feature service: gate-free, all
    #     124 districts, contiguous ED_ID 1-124, but licensed only as bare Crown
    #     copyright with an "illustration purposes only / not suitable for
    #     site-specific use" disclaimer.
    #
    # Route B is used to build and prove the pipeline. Route A supplies the bytes
    # that go live. See docs/research/boundaries/ontario.md.
    # ✅ ROUTE A — Elections Ontario, *Open Use Data Product Licence Agreement*.
    # Commercial use and redistribution both explicit, no attribution clause.
    # Licence accepted by the operator 2026-08-18; the file is a human download,
    # not an agent fetch.
    #
    # ⚠ Do NOT confuse this with the polling-division shapefile also staged in
    # the same directory: polling divisions ship under the separate and more
    # restrictive *Limited Use* agreement, and they are not electoral districts.
    "ontario": BoundarySpec(
        jurisdiction="ontario",
        source_path=(
            "ontario/current/"
            "Electoral District Shapefile - 2022 General Election.zip"
        ),
        zip_member=(
            "Electoral District Shapefile - 2022 General Election/"
            "ELECTORAL_DISTRICT.shp"
        ),
        # ⛔ There is NO EPSG for this projection. The .prj declares a custom
        # `EO_Lambert_Conformal_Conic` with no AUTHORITY clause, transcribed
        # verbatim below. It is specifically NOT EPSG:3161 (Ontario MNR Lambert),
        # which differs in central meridian (-85 vs -84), second standard
        # parallel (53.5 vs 54.5) and false easting (930,000 vs 1,000,000).
        # Coordinates are projected metres, so a bare ST_SetSRID(…, 4326) would
        # trip the boundary_in_wgs84_bounds CHECK — which is the point of it.
        src_epsg=None,
        src_proj4=(
            "+proj=lcc +lat_1=44.5 +lat_2=54.5 +lat_0=0 +lon_0=-84 "
            "+x_0=1000000 +y_0=0 +datum=NAD83 +units=m +no_defs"
        ),
        level="provincial",
        province_territory="ON",
        source_set="ontario-electoral-districts",
        id_prefix="ontario-electoral-districts",
        authority="elections-ontario",
        boundaries_version="2018",
        # Representation Act, 2015 s. 2(2): takes effect "immediately after the
        # first dissolution of the Legislature after November 30, 2016" — the
        # 41st Parliament dissolved 2018-05-08. ⚠ NOT the dataset metadata date;
        # agency metadata dates run systematically late (Ontario's by 13.5 months,
        # federal's by 11). The file is titled "2022 General Election" because
        # that is the election it served, not the date the order took force.
        effective_from=date(2018, 5, 8),
        # ⚠ DBF truncates field names to 10 characters — the attribute table reads
        # ENGLISH_NA / FRENCH_NAM, not ENGLISH_NAME / FRENCH_NAME. A loader written
        # against the ArcGIS REST schema would KeyError here.
        name_field="ENGLISH_NA",
        name_fr_field="FRENCH_NAM",
        authority_id_field="ED_ID",
        # ⚠ Ontario was the only spec without a count guard, and it is also the
        # only one whose CRS is a bespoke proj4 string rather than an EPSG code —
        # so the jurisdiction with the most room to go wrong had the least
        # checking. A mistyped `name_field` does not KeyError (props.get returns
        # None → every feature rejected), so without this the run would print
        # `districts=0 inserted=0` in green and exit 0.
        expect_districts=124,
        licence="elections-ontario-open-use",
        notes="Route A, licensed. Open Use agreement accepted by the operator; "
              "permits commercial use and redistribution with no attribution "
              "clause. Encoding is UTF-8 per the .cpg sidecar.",
    ),
    # ⛔ SASKATCHEWAN IS THE "CONFIDENT WRONG RIDING" CASE, and the reason nothing
    # here may be treated as a backfill.
    #
    # The 2022 commission held the seat count at 61 → 61, renamed 15 districts and
    # redrew most of the rest. Every one of the 46 rows we already hold name-matches
    # a district that still exists, so neither the names nor the arithmetic give any
    # signal that anything is stale. Geometry does: our 46 match the 2012 shapes at a
    # median 0.07% and the 2022 shapes at a median 11.67%; 41 of 46 match 2012 alone
    # and ZERO match 2022 alone. Worst case `regina-wascana-plains` is a 792 km²
    # polygon standing in for a district that is now 13.8 km².
    #
    # Consequence: all 61 load as a new generation and all 46 held rows are
    # superseded by the cutover migration. Inserting only the 15 absent districts
    # would take the table to a complete-looking 61/61 while leaving 41 wrong
    # polygons underneath it.
    #
    # ⚠ A LOW `--compare` overlap is therefore the EXPECTED result here and confirms
    # the diagnosis. A high overlap would mean the spec is wrong.
    "saskatchewan": BoundarySpec(
        jurisdiction="saskatchewan",
        # ⚠ A ZIP INSIDE A ZIP. The outer archive is a macOS-created bundle carrying
        # `__MACOSX/` shadow entries and a `.DS_Store`; note it also contains a
        # `__MACOSX/ShapeFile/Constituency/._Constituency30th.zip` decoy at the same
        # basename, which the reader's `__MACOSX` filter is what excludes.
        source_path="saskatchewan/current/ESK_KML_Shape_Files_Mar2024.zip",
        # ⛔ Ignore the siblings inside the same bundle: `ShapeFile/Voting Areas/`
        # holds sub-constituency VOTING AREAS (not districts) and `KML/*.kmz` are
        # duplicates of the same two layers. Picking the wrong one yields thousands
        # of plausible polygons.
        nested_zip="ShapeFile/Constituency/Constituency30th.zip",
        zip_member="ConstituencyGE30th.shp",
        # EPSG:26913 — NAD83 / UTM zone 13N, transcribed from ConstituencyGE30th.prj
        # (Transverse Mercator, CM -105.0, k0 0.9996, FE 500000, GRS 1980, metres).
        # ⚠ The .prj carries NO AUTHORITY clause; the code is fixed by the parameters,
        # declared here, never sniffed.
        # ⛔ Coordinates are projected metres (bbox X 133,978..766,070 /
        # Y 5,427,364..6,661,937), so ST_Transform is mandatory — a bare
        # ST_SetSRID(…, 4326) is the Fort Erie bug.
        # ⛔ ZONE 13, NOT 14. Manitoba is EPSG:26914. Two adjacent prairie provinces,
        # two different codes — there is no shared "prairie EPSG".
        src_epsg=26913,
        src_proj4=None,
        level="provincial",
        province_territory="SK",
        # Generation-free per rule 5. ⚠ Our existing 46 rows carry the non-compliant
        # prefix `saskatchewan-electoral-districts-representation-act-2012`; the
        # cutover migration renames those (plus 45 `politicians` and 182
        # `politician_terms` rows) onto this prefix, which is what lets the 46
        # name-stable districts keep one `constituency_id` across the transition
        # with `boundaries_version` doing the switching.
        source_set="saskatchewan-electoral-districts",
        id_prefix="saskatchewan-electoral-districts",
        authority="elections-saskatchewan",
        boundaries_version="2022-representation-act",
        # LEGAL date, not the file's Last-Modified of 2024-03-08 (a publication
        # artifact). The Representation Act, 2022 defines the 61 constituencies and
        # the Constituency Boundaries Commission states verbatim that they "come into
        # effect at the issue of the writs for the next General Election to be held
        # October 28, 2024". The 2024 writs issued 2024-10-01, which is the campaign
        # start — that is the in-force date, not polling day.
        # ⚠ Elections Saskatchewan's own glossary paraphrases this loosely as "came
        # into effect at the time of the last provincial election, October 28, 2024";
        # the commission's statement of the mechanism is the precise one.
        effective_from=date(2024, 10, 1),
        # ⚠ DBF 10-character truncations, read from the .dbf header. `Constituen` /
        # `Constitu_1` / `Constitu_2` are visually confusable with each other and
        # differ from the SAME layer's field names on the gistest ArcGIS service
        # (`CONSTITUEN`, `CONSTITU_1`, plus a `CON_NAME`/`CON_NUM` pair). The file's
        # names are authoritative here.
        name_field="Constituen",
        # No French name is published for Saskatchewan districts.
        name_fr_field=None,
        # ⚠ `Constitu_1` is a dense integer 1–61 and is the first genuine numeric
        # Saskatchewan key in any of our pipelines — but the commission REASSIGNS
        # those integers, and the prior generation's `Con_Num` is also a dense 1–61
        # over DIFFERENT districts. It is only meaningful scoped by
        # `boundaries_version`; never join it across generations.
        authority_id_field="Constitu_1",
        # One record per district, no multipart split and no polling divisions, so
        # neither a dissolve nor a filter is needed.
        dissolve_by=None,
        row_filter=None,
        # 61 = 59 southern constituencies redrawn by the commission plus the two
        # northern seats (Athabasca, Cumberland) left untouched. Confirmed against
        # Elections Saskatchewan's own news release and boundaries glossary, and
        # 61 seats are contested at the coming 31st general election.
        expect_districts=61,
        # ⚠ No licence published anywhere on elections.sk.ca — only a bare
        # `Copyright © Elections Saskatchewan` footer; /copyright/, /terms-of-use/
        # and /privacy-policy/ all 404. Recorded as provenance only; per the operator
        # ruling of 2026-08-19 licensing does not gate the load.
        licence="none-published-crown-copyright",
        notes="Zip-inside-a-zip; encoding UTF-8 per a LOWERCASE .cpg sidecar (the "
              "prior generation ships no .cpg at all and is cp1252). Roster join is "
              "clean — legassembly.sk.ca carries all 61 names verbatim — but four "
              "of our own roster district names are misspelled relative to this "
              "file (Monmartre/Montmartre, Chief Mistawis/Chief Mistawasis, "
              "Silver Springs/Silverspring, Qu'Appelle/Qu'appelle) and all four sit "
              "among the 15 districts we hold no polygon for.",
    ),
    # ⛔ BC IS THE ACUTE CASE OF THE WHOLE WORKSTREAM. We hold 52 provincial rows
    # and they are CONFIDENTLY WRONG, not merely incomplete: they are the exact
    # name-stable intersection of the 87-district 2015 order and the 93-district
    # 2023 order, carrying 2015 GEOMETRY under 2023 NAMES (51 of the 52 match the
    # authoritative 2015 areas to <0.5%). Open North's BC roster was current at 93
    # while its boundary set was still 2015, so the 41 renamed/new districts
    # carried no `related.boundary_url`, `_constituency_id()` returned None, and
    # the guard at opennorth.py:590 skipped the fetch — silently, on both the
    # politician and the boundary side. See docs/research/boundaries/
    # british-columbia.md § Reconciliation for the four evidence lines.
    #
    # Consequences for anyone touching this entry:
    #   • A LOW --compare overlap is the EXPECTED result. High overlap would mean
    #     the spec is wrong, not that our rows are fine.
    #   • ALL 93 rows are new-generation inserts. The 52 slug matches are the
    #     WORSE half of the problem, not the already-done half. "The key is
    #     already right" must never become "the row is already right".
    "british-columbia": BoundarySpec(
        jurisdiction="british-columbia",
        # ⚠ PIN THE WFS GeoJSON. BC publishes the same generation as both WFS
        # GeoJSON and SHAPE-ZIP, and their district IDs DIFFER BY EXACTLY ONE
        # (SHP ED_ID + 1 == WFS ELECTORAL_DISTRICT_ID, verified 87/87 on the 2015
        # generation). IDs are contiguous and alphabetical, so mixing
        # distributions shifts every district onto its alphabetical neighbour
        # with no error, no orphan and no failed count check. Do not "upgrade"
        # this to the shapefile distribution.
        source_path=(
            "british-columbia/current/"
            "ebc-electoral-districts-2023-bs11-epsg3005.geojson"
        ),
        # ⚠ EPSG:3005 (NAD83 / BC Albers), NOT 3153. The two have IDENTICAL
        # projection parameters and are distinguished only by datum — the .prj
        # says D_North_American_1983 (plain NAD83) → 3005; 3153 is NAD83(CSRS).
        # Deriving the code from the parameters alone would not tell them apart.
        # Coordinates are metres (first vertex 1273122.7116, 469481.0502), so
        # ST_Transform is mandatory; ST_SetSRID alone would trip the
        # boundary_in_wgs84_bounds CHECK on all 93. Corroborated from a second
        # direction: the file's own crs member declares
        # urn:ogc:def:crs:EPSG::3005.
        src_epsg=3005,
        level="provincial",
        province_territory="BC",
        # ⛔ Generation-free per ruling A6 — the year drops. What we currently
        # hold is prefixed `british-columbia-electoral-districts-2015-
        # redistribution`, which encodes not just a generation but the WRONG one
        # (2015 geometry, 2023 names). With the year gone, the 52 existing rows
        # keep their constituency_id, take effective_to = 2024-09-21 and a
        # superseded boundaries_version, and no `politicians` UPDATE is needed
        # for them at cutover.
        source_set="british-columbia-electoral-districts",
        id_prefix="british-columbia-electoral-districts",
        authority="elections-bc",
        # ⚠ Anchored to BOUNDARY_SET_ID, which is the only durable generation key
        # Elections BC publishes and is uniform at 11 across all 93 features. A
        # bare year is ambiguous for BC in a way it was not for Ontario: the Act
        # and the dataset say 2023, the in-force date says 2024, and the prior
        # generation has the same split (Act 2015 / in force 2017). `bs11-2023`
        # / `bs10-2015` keeps the two generations labelled on one axis. Coordinator
        # may override in the cutover migration; nothing else keys off it.
        boundaries_version="bs11-2023",
        # ⛔ LEGAL in-force date, not GAZETTE_DATE. Electoral Districts Act, SBC
        # 2023 c. 15, s. 6: "This Act comes into force on the day the 42nd
        # Parliament is dissolved" — dissolution was 2024-09-21 (general election
        # 2024-10-19). Corroborated in both directions: BC Laws' point-in-time
        # record says the superseded SBC 2015 c. 39 was "repealed by 2023-15-5,
        # effective September 21, 2024", and Elections BC's own announcement says
        # the new districts "come into effect once the next election is called,
        # scheduled for September 21, 2024".
        # ⚠ GAZETTE_DATE on every feature is 2023-12-07 — ten months early. It is
        # a dataset version stamp, not the in-force date.
        effective_from=date(2024, 9, 21),
        # No French field exists in this schema, and BC has no accented district
        # names in either generation — all 93 ED_NAME values are pure ASCII.
        name_field="ED_NAME",
        name_fr_field=None,
        # ⚠ Generation-scoped, unique only within BOUNDARY_SET_ID: 0 of the 52
        # name-stable districts keep their ID across generations (Abbotsford-
        # Mission is 171 in 2015 and 258 in 2023). Correct as authority_district_id
        # per generation; NEVER join on it across generations.
        # ⚠ Do not be tempted to switch this to ED_ABBREVIATION either — 8 codes
        # are RECYCLED onto different districts between generations (BNN was
        # Burnaby North in 2015 and is Burnaby-New Westminster in 2023).
        authority_id_field="ELECTORAL_DISTRICT_ID",
        # s. 1 of the Act: "There are to be 93 electoral districts". Confirmed
        # against Elections BC 2026-08-19 and against the file: 93 features, 93
        # distinct ELECTORAL_DISTRICT_ID, 93 distinct ED_NAME. No island
        # fragmentation to dissolve — see notes.
        expect_districts=93,
        licence="elections-bc-open-data-licence",
        notes="Elections BC Open Data Licence — commercial use and "
              "redistribution both explicit (clauses 2-3), no viral flow-down. "
              "Attribution required VERBATIM, including the licence's own "
              "spelling: 'Contains information licenced under the Elections BC "
              "Open Data Licence', linking https://www.elections.bc.ca/docs/"
              "EBC-Open-Data-Licence.pdf. Clause 5 terminates rights to ALL "
              "Elections BC datasets on any breach, so the string is not "
              "cosmetic; placement is an open operator decision. "
              "Geometry: all 93 are single-ring Polygon (ST_Multi required) and "
              "are NOT land-clipped — boundaries run across water, enclosing "
              "islands in one continuous ring. area_sqkm will therefore sum to "
              "~1,039,594 km² against BC's ~944,735 km² land area. That excess "
              "is correct, not a projection error, and area_sqkm must not be "
              "presented as a land area. Upside: no offshore gaps, so coastal "
              "and island addresses always fall inside exactly one district.",
    ),
    # ⛔ DO NOT LOAD THIS ENTRY YET — it needs one loader capability that does
    # not exist (`name_split`, described below). Running it today produces 49
    # rows whose `name` is the bilingual string and whose slug is derived from
    # it, which orphans 13 of the 22 rows we already hold. `--dry-run` and
    # `--compare` are safe and were both run; see the NB agent's report.
    #
    # ⚠ New Brunswick is the "confidently wrong" case at full strength. We hold
    # 22 provincial rows and every one of them is the WRONG GENERATION: they are
    # the 2018 snapshot of the superseded N.B. Reg. 2013-46 boundaries, matching
    # that generation's areas to a mean of 1.32% and diverging from the in-force
    # geometry by a mean of 124.87% (Moncton Northwest by 996%). The 22 are
    # exactly the name intersection of the two generations, which is why they
    # match on slug and look correct. The other 27 districts have no polygon at
    # all — 47% of the province's land area, 30 sitting MLAs unreachable by
    # postcode.
    #
    # ⛔ Consequently ALL 49 are new-generation inserts. Do not "insert the
    # missing 27" — the 22 present rows are the worse half, because nothing in
    # an API response signals that they are wrong.
    #
    # ⛔ A LOW `--compare` overlap is therefore the EXPECTED result here and
    # confirms the defect. A high overlap would mean the spec is wrong.
    "new-brunswick": BoundarySpec(
        jurisdiction="new-brunswick",
        # ⚠ The archive name uses a HYPHEN (`ped-cep`) and the shapefile inside
        # it uses an UNDERSCORE (`ped_cep`). Neither can be derived from the
        # other, and the archive is not linked from the GeoNB catalogue at all
        # (the catalogue's "Electoral districts" rows point at the POLLING
        # DIVISION bundles, `geonb_2025_ppd_svp_*.zip`, which are a different
        # 12-field schema and are not districts). The URL is the only record:
        # https://geonb.snb.ca/downloads/provincial_elections/geonb_2024_ped-cep_shp.zip
        source_path="new-brunswick/current/geonb_2024_ped-cep_shp.zip",
        # Members sit at the archive root, no directory prefix.
        zip_member="geonb_2024_ped_cep.shp",
        # NAD83(CSRS) / New Brunswick Stereographic. ⛔ Declared, not sniffed:
        # ZERO of the six staged NB `.prj` files carries an AUTHORITY clause (all
        # six are byte-identical), so EPSG auto-detection fails on every NB
        # generation. Derived by matching all eight projection parameters —
        # Double_Stereographic, lat_0 46.5, lon_0 -66.5, k 0.999912, FE 2500000,
        # FN 7500000, GRS 1980, metres — and corroborated twice: the GeoNB
        # ArcGIS service reports `latestWkid 2953`, and GeoNB's own read_me.txt
        # says "EPSG code: 2953" in prose.
        # Coordinates are projected METRES (bbox 2306896,7275121 – 2713275,
        # 7677113), so ST_Transform is mandatory; ST_SetSRID(…,4326) here would
        # be the Fort Erie bug exactly.
        src_epsg=2953,
        level="provincial",
        province_territory="NB",
        # ⛔ Generation-free, per rule 5. This deliberately differs from the
        # `new-brunswick-electoral-districts-2018/` prefix on the 22 rows we
        # hold, so the cutover is an insert plus a re-key rather than an
        # in-place overwrite — 66 strings across politicians (22),
        # politician_terms (22) and constituency_boundaries (22).
        source_set="new-brunswick-electoral-districts",
        id_prefix="new-brunswick-electoral-districts",
        authority="elections-new-brunswick",
        # ⚠ The catalogue's newest provincial row is titled "current (2025)".
        # That is the 2025 POLLING-DIVISION revision; there is no 2025 district
        # generation. The districts in force are the 2024 file.
        boundaries_version="2024",
        # N.B. Reg. 2023-42 (O.C. 2023-162) s. 5: "comes into force on the first
        # dissolution of the Legislative Assembly after April 24, 2023." The
        # 60th Legislature dissolved 2024-09-19 for the 2024-10-21 election.
        # ⛔ Rejected, recorded so nobody re-litigates: 2023-06-29 (O.C. filing),
        # 2023-09-29 (GeoNB read_me DATE), 2025-03-06 (catalogue Date column),
        # 2024-08-22 (file Last-Modified), 2023-03-12 (commission report filed).
        # ⛔ And do NOT use laws.gnb.ca's "Revoked on <date>" header — it is the
        # consolidation cutoff, not a legal date (Reg. 2006-27 carries the two
        # separately with different values, which proves it).
        effective_from=date(2024, 9, 19),
        # ⚠ DBF truncates to 10 chars: the field is `PED_Names_` here and
        # `PED_Names_B` over the ArcGIS REST service. A loader written against
        # the REST schema KeyErrors on the shapefile.
        #
        # ⛔ THIS FIELD IS BILINGUAL-COMBINED, and NB ships no separate English
        # or French field — the only alternative, `LabelField`, is the same
        # string with the DIST_ID prepended ("1-Restigouche West /
        # Restigouche-Ouest"). Values are "English / Français" where the two
        # differ (20 of 49) and a single value where they do not ("Caraquet").
        # The English half is the legal short name used by Reg. 2023-42 s. 3 and
        # is the join key to our roster (49/49 exact).
        #
        # ⛔ Split on "/" and strip — NOT on the literal " / ". The 2024 layer
        # uses spaces around the slash; the prior generation's combined field
        # uses none ("Restigouche West/Restigouche-Ouest"), so a literal-" / "
        # split silently no-ops on every earlier generation. Verified on this
        # file: no value contains more than one "/", and none uses the
        # space-free form.
        #
        # ⛔ MEASURED COST OF NOT SPLITTING: the slug is derived from `name`, so
        # unsplit the 20 bilingual districts mint slugs like
        # `restigouche-west-restigouche-ouest`. Of the 22 rows we hold, only 9
        # would then match and 13 would be orphaned, while 13 duplicate-geometry
        # districts appear under wrong slugs. Split, it is exactly 22 matched /
        # 27 new / 0 orphaned. This is a correctness gate, not cosmetics.
        name_field="PED_Names_",
        # ★ Bilingual single field — see name_split on BoundarySpec. Bare "/",
        # not " / ": the 2024 layer pads, earlier generations don't.
        name_split="/",
        # ⚠ Stays None: NB has no French FIELD. The French form is recovered
        # from name_split above, which populates name_fr from the second half.
        name_fr_field=None,
        # ★ Not an arbitrary sequence — DIST_ID is the statutory map number used
        # by Reg. 2023-42 s. 3 itself ("shown on the map 1 – Restigouche West").
        # ⚠ But it is stable only WITHIN a generation: 27 of 49 DIST_IDs point at
        # a different district across the 2013-46 → 2023-42 boundary (2 was
        # Campbellton-Dalhousie, is now Restigouche East). Never join on
        # authority_district_id unscoped by boundaries_version.
        authority_id_field="DIST_ID",
        # 49 records, 49 distinct DIST_ID, 49 distinct names — strictly one row
        # per district. Worth asserting anyway: NB has Grand Manan, Campobello,
        # Deer Island, Miscou and Lamèque, and exactly one record is multipart
        # (2 parts), so an island-fragment source was plausible. Independently
        # confirmed at 49 by the Legislative Library of New Brunswick's results
        # for the 2024-10-21 general election, and by Reg. 2023-42 s. 3
        # enumerating paragraphs (a)–(ww).
        expect_districts=49,
        licence="geonb-open-data-licence-v1.0",
        notes="Elections New Brunswick via GeoNB (Service New Brunswick). "
              "✅ The flow-down clause Open North reproduces is § 4.5 of the "
              "GeoNB License Agreement dated 2012-07-04, superseded in 2015 by "
              "the GeoNB Open Data Licence v1.0 — which ships inside this "
              "archive as license_licence.txt and has NO flow-down, no "
              "sublicensing restriction and no term. Corroborated by "
              "open.canada.ca tagging every NB electoral dataset "
              "`license_id: nb-oglnb`. Attribution is the only live obligation, "
              "and the catalogue page and the in-bundle licence name different "
              "strings, so cite both: \"Contains information licenced under the "
              "GeoNB Open Data Licence\" (note the British spelling) and "
              "\"Contains information licensed under the Open Government "
              "Licence – New Brunswick\". "
              "Encoding is UTF-8 per the lowercase .cpg sidecar — but only for "
              "this generation: the staged 2014 and 2010 files ship no .cpg and "
              "are cp1252. "
              "⚠ Cross-check available: geonb_2024_ped-cep_kmz.zip is the same "
              "49 districts WGS84-native, so it can verify ST_Transform "
              "independently. Its attributes are unusable (zero ExtendedData; "
              "everything lives in an HTML table inside a CDATA blob), so it is "
              "a geometry check only.",
    ),
    # ⛔⛔ THE FILENAME LIES, AND IT LIES IN THE MOST DANGEROUS DIRECTION.
    # `EN_FUTURE_…` is the generation **currently in force**; the file in
    # `prior/` named `EN_PRESENT_2013_Present_…` is the **superseded** one. Both
    # were released together on 2024-10-28 and named relative to *that* moment,
    # then never revised — when the 6th Assembly dissolved on 2025-09-21 the
    # labels silently swapped meaning.
    #
    # Confirmed from CONTENT, not the filename — the ArcGIS `idPurp` block in
    # each archive's own `.shp.xml` self-identifies:
    #   EN_FUTURE_…  "…as approved by the sixth Legislative Assembly of Nunavut
    #                 in May of 2024. These constituencies and boundaries will
    #                 become official the day after the day that the sixth
    #                 Legislative Assembly of Nunavut dissolves."   → Bill 48
    #   EN_PRESENT_… "They became the official constituencies … on September 23,
    #                 2013. These boundaries **will be replaced** … the day after
    #                 the day that the sixth Legislative Assembly dissolves."
    # That replacement happened 11 months ago, and the 7th general election
    # (2025-10-27) was already run on the geometry in THIS file.
    #
    # ⚠ Do NOT read the FGDC `<abstract>` in the same `.shp.xml`. It is inherited
    # boilerplate reading "These boundaries were updated in 2011 … They are the
    # current constituency boundaries" — twelve years stale. `idPurp` is the
    # authoritative block; the abstract was never rewritten.
    "nunavut": BoundarySpec(
        jurisdiction="nunavut",
        source_path="nunavut/current/EN_FUTURE_NU_Constituencies.zip",
        # Members sit at the archive root with no directory prefix.
        zip_member="EN_FUTURE_NU_Constituencies.shp",
        # ⛔ EPSG:4617, NAD83(CSRS) GEOGRAPHIC — degrees, not a polar projection,
        # despite the Arctic extent (bbox lat 51.16 .. 90.00, lon -120.68 ..
        # -57.53). The `.prj` ends at its UNIT clause with no AUTHORITY, so
        # auto-detection yields nothing (rule 2). The code is recovered from the
        # `.shp.xml`, which carries it twice: an escaped WKT with
        # `AUTHORITY["EPSG",4617]` and `<identCode code="4617">`.
        # ⚠ The same file ALSO carries `<WKID>4140</WKID>`. 4140 is the
        # deprecated NAD83(CSRS98) code — use 4617, the LatestWKID.
        # The datum shift to WGS84 is sub-metre, so the transform is nearly a
        # no-op, but it is still declared and transformed, never relabelled
        # (rule 1).
        src_epsg=4617,
        level="provincial",
        province_territory="NU",
        # ⛔ Generation-free, per rule 5. The dossier originally recommended a
        # `-2024` suffix; that was struck by coordinator ruling A6. Nunavut holds
        # ZERO rows today, so unlike the 12 jurisdictions already carrying a
        # generation in their prefix, this is the one place the correct scheme
        # costs nothing — following the old recommendation would mint 22
        # brand-new violating keys into a clean table.
        source_set="nunavut-electoral-districts",
        id_prefix="nunavut-electoral-districts",
        authority="elections-nunavut",
        # In-force year, matching the `ontario` entry's convention. (The legacy
        # Open-North-derived rows all carry the literal 'current', which cannot
        # distinguish generations.) Leaves '2013' free for the prior generation,
        # whose 22 keys are identical — only the geometry differs.
        boundaries_version="2025",
        # ⛔ LEGAL in-force date, not the agency's metadata date. Bill 48, *An Act
        # Respecting the Constituencies of Nunavut*, assented May 2024; *Nunavut
        # Elections Act* s.29(2) commences any boundaries Act "on the 1st day
        # following the day the Legislative Assembly dissolves". The 6th Assembly
        # dissolved 2025-09-21, so the order took force 2025-09-22 — stated
        # outright by the CEO's 2024-2025 annual report, "(Effective September 22,
        # 2025)", and corroborated by the 2025-09-22 writ issuance.
        # ⚠ EVERY metadata date on this file is wrong for this purpose, and they
        # disagree with each other: readme "released October 28, 2024",
        # `.shp.xml` CreaDate 20241110, `.dbf` last-update 2024-09-21, HTTP
        # Last-Modified 2024-11-20. The nearest of them leads the legal date by
        # ~10 months; taking any would have placed every Nunavut address in the
        # new riding throughout the 7th Assembly's pre-election period, including
        # the 2025 campaign.
        effective_from=date(2025, 9, 22),
        effective_to=None,
        # ⚠ DBF field names, read from the header. `Name_E` is C(56) and is
        # UPPERCASE in the data ("HUDSON BAY", not "Hudson Bay") — see the note
        # on casing below.
        name_field="Name_E",
        # Populated for only 6 of 22; the loader's `or None` turns the blank
        # fixed-width padding into NULL for the other 16.
        name_fr_field="Name_Fr",
        # ⛔ THE EXCEPTION TO CONVENTION #1: there is no district ID field at all.
        # The only other candidate, `Loc` C(2), is the constant 'NU' on all 22
        # rows. `Name_E` is the de-facto key — unique across all 22, unchanged
        # across both generations (the 2024 order redrew geometry without
        # creating, retiring or renaming a single district), and a clean 22/22
        # case-insensitive match to our roster. So `authority_district_id` stays
        # NULL for Nunavut, deliberately, rather than being synthesised.
        authority_id_field=None,
        # 22 seats, one MLA each — *Nunavut Elections Act* s.31(1), and confirmed
        # against Elections Nunavut's own /en/constituencies index. The file has
        # 22 records, 22 distinct `Name_E`, and exactly ONE ring each.
        # ⚠ No multipart geometry despite the archipelago, and none should be
        # added: s.30(a) requires that "no part of Nunavut lies outside a
        # constituency", so the polygons include marine area and tile the
        # territory wall-to-wall — Baffin, Victoria and Ellesmere are *enclosed*
        # by their district rather than stored as island fragments. This is the
        # one source in the corpus where rule 3 does not bite. If a future
        # re-issue ever exceeds 22 records, the format changed.
        expect_districts=22,
        licence="ogl-elections-nunavut-1.0",
        notes="Open Government Licence – Elections Nunavut v1.0, shipped as "
              "`readme EN_FUTURE_NU_Constituencies.pdf` inside the zip. Plain "
              "GET, no click-through, no registration. Commercial use and "
              "redistribution both explicit; attribution is a HARD CONDITION "
              "(the licence terminates automatically on non-compliance) — "
              "\"Contains information licensed under the Open Government Licence "
              "– Elections Nunavut.\" "
              "⚠ The encoding sidecar is `.CPG` UPPERCASE and declares UTF-8; a "
              "case-sensitive glob returns empty here and `Name_I` (Inuktitut "
              "syllabics, all 22) would mojibake as cp1252. "
              "`_open_shapefile_reader` already matches case-insensitively. "
              "⚠ `name` will load UPPERCASE because that is how Elections Nunavut "
              "stores it, unlike every other jurisdiction in SPECS. Slugs are "
              "unaffected (slugify lowercases), but the public API surfaces "
              "`name` verbatim. A title-case transform is a loader change and is "
              "deliberately NOT made here — flagged for the coordinator. "
              "⚠ Fidelity loss to revisit: s.31(1) makes all four language "
              "versions of a district name EQUALLY authoritative, but `name` and "
              "`name_fr` are the only columns we have, so `Name_I` (syllabics, "
              "22/22) and `Name_Inu` (Inuinnaqtun, 11/22) are dropped on load. "
              "Both are C(50) and BYTE-truncated: the syllabics for RANKIN INLET "
              "NORTH-CHESTERFIELD INLET and ARVIAT NORTH-WHALE COVE hit the "
              "50-byte limit and are silently incomplete in the source (the cut "
              "lands on a character boundary, so there is no mojibake to spot).",
    ),
    # ⛔ QUEBEC IS THE FIRST FUTURE-DATED GENERATION, and the first time the
    # temporal model from migration 0021 has ever been used for its purpose.
    # Every other cutover in this file DELETED its predecessor on the day.
    #
    # `Loi visant à assurer la représentation effective des électeurs`, 2026
    # c. 15 art. 2: the new list takes effect when the 43rd legislature ENDS —
    # that day, not the day after (⚠ Nunavut's rule is "the 1st day following
    # dissolution"; do not carry it across). `Loi sur l'Assemblée nationale`
    # art. 6 fixes when: the legislature expires on 29 August of the fourth
    # calendar year after the last general election. Last GE 2022-10-03, so
    # 2026-08-29. The LG may dissolve earlier; it cannot run later.
    #
    # ★ The error is therefore ONE-SIDED and that is the safety argument.
    # 2026-08-29 is the LATEST lawful date, so this value can only make us late
    # — serving the still-lawful 2017 map a few extra days if dissolution comes
    # early. It can never activate a map that is not yet law. A date taken from
    # the polling day (2026-10-05) would have failed the other way and served a
    # REPEALED map for the whole five-week writ period.
    #
    # ⚠ Loading this is only half the cutover. Migration 0070 sets
    # effective_to = 2026-08-28 on the 2017 generation; without it BOTH satisfy
    # the current-date predicate on the 29th and every Quebec address returns
    # two districts.
    "quebec": BoundarySpec(
        jurisdiction="quebec",
        # ⚠ FILENAME TRAP: the enclosing directory is plural and accented
        # (`circonscriptions_électorales_2026_shapefile/`) while the member
        # basename inside it is SINGULAR and UNACCENTED. Neither matches the
        # outer archive name. Naming the member explicitly is what makes the
        # mismatch visible to the next reader.
        source_path="quebec/pending/circonscriptions_electorales_2026_shapefile.zip",
        zip_member=(
            "circonscriptions_électorales_2026_shapefile/"
            "Circonscription_electorales_2026_shapefile.shp"
        ),
        # EPSG:3798 — NAD83 / Quebec Lambert. The .prj has no AUTHORITY clause
        # and names itself `NAD_1983_MTQ_Lambert`, so the code is asserted from
        # the parameters: LCC, CM -70, SP 46/50, FE 800000, lat0 44, GRS80.
        #
        # ⓘ The 2017 file declares the SAME projection under a different PROJCS
        # name (`LambertAQ`), the two standard parallels in the opposite order,
        # and an explicit Scale_Factor 1.0. LCC is symmetric in its parallels
        # and 1.0 is the default, so they are mathematically identical —
        # verified against both files rather than assumed, because rule 2
        # forbids sharing a CRS across generations on faith.
        src_epsg=3798,
        level="provincial",
        province_territory="QC",
        source_set="quebec-electoral-districts",
        id_prefix="quebec-electoral-districts",
        authority="elections-quebec",
        boundaries_version="2026",
        effective_from=date(2026, 8, 29),
        effective_to=None,
        # ⚠ FIELD DRIFT is why Quebec needs a separate spec per generation
        # rather than one parameterised by year:
        #     2017: NM_CEP C(30), NM_TRI_CEP C(30)
        #     2026: NM_CEP C(50), NMTRI_CEP  C(50)   <- underscore dropped
        # NMTRI_CEP is a sort key (accent-folded, article moved), not a French
        # name; Quebec publishes no second language form because the file is
        # already French.
        name_field="NM_CEP",
        name_fr_field=None,
        # ⛔ CO_CEP is an excellent key WITHIN a generation and useless across
        # one. Measured: all 125 values EVEN in 2017, all 127 ODD in 2026, zero
        # overlap — while 108 district NAMES carry through. Never join the two
        # generations on it.
        authority_id_field="CO_CEP",
        expect_districts=127,
        licence="elections-quebec-non-commercial",
        notes="Élections Québec 2026 map, Gazette officielle 2026-01-14; 125 "
              "-> 127 divisions (Bellefeuille and Marie-Lacoste-Gérin-Lajoie "
              "added). ⛔ Do NOT substitute "
              "circonscriptions_electorales_sans_eau_2026.json: measured, it "
              "keeps 9.6% of vertices (57,535 vs 600,046), water-clipping "
              "shatters coastal districts into 36 disconnected fragments, and "
              "it is already reprojected — a different EXTENT, not a "
              "generalisation. ⚠ The 2017 generation spells CO_CEP 370 "
              "`Bourget`; it was renamed `Camille-Laurin` in 2021 mid-"
              "generation and our rows carry the new name, so a name-keyed "
              "reload of 2017 would orphan the roster link.",
    ),
    # ⛔ FEDERAL — 2023 Representation Order, 343 districts, and the FIRST
    # spec to key its slug on something other than the district name. See
    # `slug_field` below.
    "federal": BoundarySpec(

        jurisdiction="federal",
        source_path="federal/current/FED_CA_2023_EN-SHP.zip",
        zip_member="FED_CA_2023_EN.shp",
        # EPSG:3347 — NAD83 / Statistics Canada Lambert. ⚠ The .prj names itself only
        # `PCS_Lambert_Conformal_Conic` and carries NO AUTHORITY clause, so the code
        # is asserted from the parameters: CM -91.866666…, SP 49/77, FE 6,200,000,
        # FN 3,000,000, lat0 63.390675.
        src_epsg=3347,
        level="federal",
        # ⚠ Scalar fallback only. The real value comes from province_resolver below,
        # because one national file spans thirteen provinces and territories and
        # `constituency_boundaries.province_territory` is per row.
        province_territory=None,
        province_resolver=_province_from_fed_num,
        # Generation-free, replacing
        # `federal-electoral-districts-2023-representation-order`.
        source_set="federal-electoral-districts",
        id_prefix="federal-electoral-districts",
        authority="elections-canada",
        boundaries_version="2023-representation-order",
        # ⛔ THE LEGAL DATE, and it is a genuine judgement call. SI/2023-57 (issued
        # 2023-09-22, registered 2023-09-27) provides that the order comes into force
        # "on the first dissolution of Parliament that occurs at least seven months
        # after" registration. Seven months lands on 2024-04-22; the first
        # dissolution after that was 2025-03-23, the writs for the 45th general
        # election. So 2025-03-23.
        #
        # ⚠ Elections Canada's own dataset metadata records
        # `time_period_coverage_start = 2024-04-23` — the ADMINISTRATIVE date, the day
        # the order became capable of coming into force. Between those two dates the
        # 2013 order was still the law and the 44th Parliament still sat its 338
        # seats, so the administrative date would assert a map that governed nothing
        # for eleven months. The statutory reading wins.
        effective_from=date(2025, 3, 23),
        effective_to=None,
        name_field="ED_NAMEE",
        # ★ The file ships official French names and we currently store none for any
        # federal district — 343 free `name_fr` values in an officially bilingual
        # jurisdiction.
        name_fr_field="ED_NAMEF",
        authority_id_field="FED_NUM",
        # ⛔ The slug IS the FED_NUM. See the header.
        slug_field="FED_NUM",
        expect_districts=343,
        licence="ogl-canada-2.0",
        notes="Elections Canada, Electoral Geography Division. OGL–Canada 2.0, no "
              "click-through; attribution required: \"Contains information licensed "
              "under the Open Government Licence – Canada.\" "
              "⚠ .CPG is UPPERCASE on this file and lowercase on the 2021/2025 ones; "
              "the reader matches case-insensitively, but a case-sensitive glob would "
              "mojibake every accented Quebec name. "
              "⛔ FED_NUM values are REUSED across representation orders with "
              "different meanings — (FED_NUM, REP_ORDER) is the cross-generation key, "
              "which is why boundaries_version names the order.",

    ),
    # Alberta — 87 divisions. A pure provenance upgrade plus one live API bug.
    #
    # ✅ Our geometry is CURRENT and it was measured, not assumed: 87/87 exact, 0
    # gaps, 0 extras, 0 name drift; 99.887% mean overlap against the 2019 set
    # (min 99.583%, none below 95%) versus 81.275% against the 2010 set with 29
    # unmatched. A Saskatchewan-style silent redraw is ruled out.
    #
    # ⛔ AND YET THE DETAIL ENDPOINT 404s FOR EVERY ALBERTA DISTRICT
    # --------------------------------------------------------------
    # `source_set` is `alberta-electoral-districts` while the `constituency_id`
    # prefix is `alberta-electoral-districts-2017`. The public detail route is
    # `/boundaries/:source_set/:slug`, so it builds
    # `/boundaries/alberta-electoral-districts/calgary-bow` and finds nothing,
    # because the stored id is `alberta-electoral-districts-2017/calgary-bow`.
    # Alberta is the only jurisdiction where the two disagree. The cutover migration
    # aligns them onto the generation-free form.
    #
    # ⚠⚠ ALBERTA IS THE INVERSE CRS TRAP — DO NOT "FIX" THIS TO 3400
    # ---------------------------------------------------------------
    # The ArcGIS service's native SR is EPSG:3400 (NAD83 / Alberta 10-TM Forest,
    # metres) and the service path even says `10tm_nad83`. But the staged file was
    # fetched with `f=geojson` and ArcGIS REPROJECTED ON EXPORT: the first coordinate
    # is [-112.883445, 49.628507] — decimal degrees — and there is no `crs` member.
    # Declaring 3400 would treat degrees as metres and land the whole province a few
    # hundred metres from the origin off West Africa.
    #
    # ★ The rule this illustrates: CRS is a property of the STAGED ARTIFACT, not of
    # the service it came from. ⚠ A re-fetch with `f=json` WOULD return 10TM metres
    # and would need 3400. Nova Scotia is the same shape (declared 3857, exported in
    # degrees).
    "alberta": BoundarySpec(

        jurisdiction="alberta",
        source_path="alberta/current/goa-provincial-electoral-division-current-2019.geojson",
        # See the header. Degrees on disk, whatever the service advertises.
        src_epsg=4326,
        level="provincial",
        province_territory="AB",
        source_set="alberta-electoral-districts",
        # Generation-free, and here that also repairs the source_set/prefix
        # divergence that 404s the detail endpoint.
        id_prefix="alberta-electoral-districts",
        authority="elections-alberta",
        boundaries_version="2017-commission",
        # ⚠ `needs confirmation`. Three candidate dates span two years: the 2017
        # commission's report, the "Alberta Election Act, Chapter E-1, 2018" chapter
        # the GoA metadata cites, and first use at the 30th general election on
        # 2019-04-16. Taking first use, because it is the one date on which these
        # divisions demonstrably governed something — the same reasoning that picks
        # dissolution over assent for Yukon and Quebec.
        # ⛔ Not the King's Printer "current as of" consolidation date; that is a
        # publishing artefact, not a commencement.
        effective_from=date(2019, 4, 16),
        effective_to=None,
        name_field="EDNAME",
        # Alberta publishes no French district names.
        name_fr_field=None,
        # ⚠ String '1'–'87', NOT zero-padded — unlike `politicians.ab_assembly_mid`,
        # which is. Do not join the two without padding.
        # ⛔ And EDNUMBER is NOT stable across generations: 2010's #12 is a different
        # division from 2019's #12, while 58 of 87 NAMES are unchanged between the
        # two even though the boundaries moved. Either key alone is a trap across
        # generations; (EDNUMBER, boundaries_version) is the safe one.
        authority_id_field="EDNUMBER",
        expect_districts=87,
        licence="ogl-alberta",
        notes="Open Government Licence – Alberta. Commercial use and redistribution "
              "permitted; attribution is MANDATORY and the licence terminates "
              "automatically on non-compliance — \"Contains information licensed "
              "under the Open Government Licence – Alberta.\" "
              "⚠ The staged extract was queried with outFields=EDNUMBER,EDNAME only. "
              "Do NOT add the service's MLA_TITLE / MLA_FNAME / MLA_LNAME fields: "
              "they are a stale roster snapshot, and OGL-Alberta's Exemptions clause "
              "carves out Personal Information. "
              "⚠ Known expiry: the 2025-26 commission reported 2026-03-23 proposing "
              "89 divisions. Not enacted, and no 89-division layer exists yet.",

    ),
    # Prince Edward Island — 27 districts published as 270 POLLING DIVISIONS.
    #
    # ⚠⚠ TWO transformations are needed before a single row can be written, and
    # skipping either produces a plausible-looking wrong answer:
    #
    #   1. FILTER. 26 of the 270 features are junk: DIST_NO = 0, blank DISTRICT,
    #      blank POLL_NAME, electorcou = 0. Unfiltered they group under one empty
    #      key and mint a phantom 28th district.
    #   2. DISSOLVE. The remaining 244 are polling divisions, 2-15 per district.
    #      Inserted naively that is 244 rows for 27 districts — a 9x duplication.
    #
    # `expect_districts=27` is what turns "the filter or the key is wrong" into an
    # abort instead of a silent 28 or 244.
    #
    # ⓘ PEI and Nova Scotia are the only two `dissolve_by` users, and the mechanism
    # was a NO-OP until 2026-08-19: `group_features` read the dissolve key, checked
    # it for non-emptiness, and then discarded it, grouping by slugified name in both
    # branches. It happened to give the right answer here because PEI's district
    # names are byte-consistent across their polling divisions — correct by luck, not
    # by construction.
    #
    # ⛔ THE GAP IS CORRELATED ON BOTH SIDES, WHICH IS WHY NO INTERNAL CHECK FOUND IT
    # ------------------------------------------------------------------------------
    # We hold 26 boundaries AND 26 politicians AND 26 distinct district names, with
    # zero unattached members. Every internal consistency check passes. The province
    # has 27 seats. Both halves were mirrored from the same Open North source, so
    # they are wrong together and agree with each other — the exact failure mode that
    # makes "confirm the count against the elections agency" a mandatory step rather
    # than a formality.
    #
    # The missing 27th is `Georgetown - Pownal`, DIST_NO 2.
    "prince-edward-island": BoundarySpec(

        jurisdiction="prince-edward-island",
        # ⚠ RAW ESRI JSON, not GeoJSON. The service advertises
        # `supportedQueryFormats: JSON` only — `f=geojson` is unavailable — so the
        # staged artifact uses Esri's `rings` geometry encoding and the loader's
        # `_read_esrijson` path rather than `_read_geojson`.
        source_path=(
            "prince-edward-island/current/"
            "Provincial_Electoral_Wards_and_Polls_esrijson_native2954.json"
        ),
        # EPSG:2954 — NAD83(CSRS) / PEI Stereographic, metres. ⚠ The service reports
        # {"wkid": 2291, "latestWkid": 2954}; use 2954. 2291 is the deprecated CSRS98
        # variant. There is NO .prj anywhere in the artifact, so unlike every other
        # jurisdiction this SRID cannot be checked against a file — it is asserted
        # from the service metadata alone.
        # ⚠ False easting 400000 / false northing 800000 distinguish this from the
        # other Maritime stereographic grids.
        src_epsg=2954,
        level="provincial",
        province_territory="PE",
        source_set="prince-edward-island-electoral-districts",
        id_prefix="prince-edward-island-electoral-districts",
        authority="elections-pei",
        boundaries_version="2017",
        # ⚠ `needs confirmation`. The instrument is the Schedule to the Electoral
        # Boundaries Act R.S.P.E.I. 1988 Cap. E-2.1, replaced by SPEI 2017 c. 63 s. 1;
        # the assent/proclamation date is unobtainable because PEI's Table of Public
        # Acts is WAF-blocked. Bounded after the 2017 fall sitting and before
        # 2019-03-26. Using first use at the 2019-04-23 general election, consistent
        # with the reasoning applied to Yukon, Quebec and Alberta.
        effective_from=date(2019, 4, 23),
        effective_to=None,
        # Spaced hyphen in the GIS data (`Souris - Elmira`); the statutory Schedule
        # writes them unspaced. The GIS spelling matches our roster, and slugify
        # folds the difference anyway.
        # ⓘ The Schedule also contains its own typo — entry 20 reads
        # `Kensingston-Malpeque`. The GIS `Kensington - Malpeque` is correct.
        name_field="DISTRICT",
        name_fr_field=None,
        authority_id_field="DIST_NO",
        # ⛔ Group polling divisions by their district number, not by name.
        dissolve_by="DIST_NO",
        # ⛔ Drop the 26 junk rows. DIST_NO is an Integer here, so guard the None case
        # before comparing.
        row_filter=lambda p: (p.get("DIST_NO") or 0) > 0,
        expect_districts=27,
        licence="none-published",
        notes="⛔ No licence is stated anywhere: `copyrightText` is empty on both the "
              "service and the layer. Staged and loaded as public electoral data per "
              "operator decision; recorded as provenance, not as a grant. "
              "⚠ Districts are legally defined by CIVIC ADDRESS (Schedule s. 1(3)), "
              "not by geometry — the polygons are a rendering of that rule, so a "
              "point-in-polygon answer is an approximation of the statute in a way "
              "it is not elsewhere. "
              "⚠ electionspei.ca and assembly.pe.ca are Radware-blocked, and "
              "www.princeedwardisland.ca returns HTTP 200 with a challenge-stub body "
              "— status-code checks lie there; the static /sites/default/files/ path "
              "is the unchallenged carve-out. "
              "⚠ boundary_simple erodes 2.10% of area here versus <0.5% elsewhere; "
              "regenerating it at a feature-size-aware tolerance is a known follow-up.",

    ),
    # Northwest Territories — 19 districts, and the only jurisdiction in this wave
    # where the DIAGNOSIS was contested before the fix could be chosen.
    #
    # ⛔ THE DEFECT: right names, wrong shapes, for 5 of 19
    # ----------------------------------------------------
    # Our 19 rows name-match the authoritative set exactly — 19/19 slug match, no
    # re-key needed — so every count-based check passes. The geometry does not:
    #
    #     Hay River South   26.0% valid      Great Slave      30.6% valid
    #     Frame Lake        48.0% valid      Nunakput         49.1% valid
    #     Hay River North   70.2% valid
    #
    # Two adjacent pairs with complementary over- and under-coverage, which is the
    # signature of misplaced SHARED boundaries — and it means live wrong-riding
    # answers in Yellowknife and Hay River, the two places in the territory where
    # enough people live for it to matter.
    #
    # ⓘ The held rows also total 2,192,291 km² against a territory of ~1,346,000 —
    # 63% oversized, consistent with marine extent bleeding into Nunakput.
    #
    # ★ REDRAW OR BAD MIRROR? THE ANSWER SELECTS A DIFFERENT MIGRATION
    # -----------------------------------------------------------------
    # Two research dossiers disagreed: `impact.md` read the divergence as a real
    # 2013→2023 redraw (⇒ load as a NEW generation, end-dating the old rows), while
    # the NT dossier read it as a corrupt Open North mirror (⇒ correct the geometry
    # IN PLACE under the existing rows, keeping the 2015 in-force date).
    #
    # Operator ruling: treat it as an unmaintained mirror and correct in place. That
    # is also the reversible choice — if it later proves to be a real redraw, a
    # generation can be split out; whereas fabricating a 2023 generation that never
    # existed in law would have to be unpicked.
    #
    # ⚠ The statute supports the ruling. LAECA s. 2(1) still reads "There are 19
    # electoral districts", and S.N.W.T. 2014 c. 21 came into force "on dissolution
    # of the 17th Legislative Assembly" — 2015-10-25. No instrument since has
    # redrawn them, so there IS no 2023 generation to load. The `ElectoralYear = 2023`
    # attribute on every feature is a file-refresh stamp, not a legal vintage.
    "northwest-territories": BoundarySpec(

        jurisdiction="northwest-territories",
        # ★ The GeoJSON rather than the shapefile, for one decisive reason: it is the
        # ONLY publication carrying `EDFrench`. The .dbf has just five fields and no
        # French name at all, and NWT district names are official in both languages
        # (`Hay River Nord`, `Delta du Mackenzie`, `Yellowknife Sud`).
        # The .zip remains staged as the native-CRS artifact of record.
        source_path="northwest-territories/current/NWT_ElectoralDistricts.geojson",
        # ⚠ 4326 — and this is NOT the Alberta/Nova Scotia "already in degrees"
        # situation, it is simply a GeoJSON export: first coordinate
        # [-114.516689, 62.250007], no `crs` member.
        # ⛔ The staged SHAPEFILE is a different CRS entirely: ESRI:102002
        # (Canada_Lambert_Conformal_Conic), which has NO EPSG equivalent and is
        # already present in our spatial_ref_sys under auth_name 'ESRI'. If the .zip
        # is ever used instead, declare that — and never substitute EPSG:3347 or
        # 3978, which are also NAD83 Lambert but with different standard parallels
        # and origin, and would shift the territory by kilometres.
        src_epsg=4326,
        level="provincial",
        province_territory="NT",
        # ⚠ In-place correction, so the id_prefix must stay EXACTLY what we already
        # hold, generation suffix and all. Moving to the generation-free form here
        # would be a re-key, and a re-key is the thing an in-place correction is
        # defined by not doing. Normalising the prefix is deferred to its own change
        # so that if the geometry correction has to be reverted, it reverts alone.
        source_set="northwest-territories-electoral-districts-2013",
        id_prefix="northwest-territories-electoral-districts-2013",
        authority="elections-nwt",
        boundaries_version="current",
        # S.N.W.T. 2014 c. 21 (Bill 18, 17th Assembly), in force "on dissolution of
        # the 17th Legislative Assembly"; Elections NWT records that dissolution as
        # 2015-10-25 (writs 10-26, poll 11-23).
        # ⛔ NOT `ElectoralYear = 2023` and not the 2023-07-28 file stamp — those are
        # ~7 years 9 months late. And not the 2023-01-01 the mirror carried, which
        # opennorth.py hardcoded for every row in the table.
        effective_from=date(2015, 10, 25),
        # Still law. Left open.
        effective_to=None,
        name_field="ED",
        name_fr_field="EDFrench",
        # ⛔ No district ID field exists in any NWT publication. OBJECTID is a row
        # ordinal — observed values start at 420 — so identity is the slugified name.
        authority_id_field=None,
        expect_districts=19,
        licence="none-published",
        notes="Elections NWT / GNWT. No licence published; loaded as public "
              "electoral data per operator decision. "
              "⚠ 4 districts are multi-part within a single record — Tu Nedhé - "
              "Wiilideh 20 parts, Yellowknife North 20, Sahtu 14, Dehcho 2 — so they "
              "arrive as MultiPolygon and need no dissolve. "
              "⚠ Two display-name normalisations where the authority and our rows "
              "differ but the slug does not: authoritative `Mackenzie-Delta` / "
              "`Tu Nedhé - Wiilideh` vs held `Mackenzie Delta` / `Tu Nedhé-Wiilideh`. "
              "The held spellings read better and the cutover keeps them. "
              "⚠ Known expiry: a 2025-26 commission tabled a 22-district "
              "recommendation on 2026-02-27. Not enacted; expect this to lapse before "
              "the 2027-10-05 general election.",

    ),
    # Nova Scotia — Elections NS electoral geography, 56-district (2026) generation.
    #
    # Dossier: docs/research/boundaries/nova-scotia.md
    # Provenance: data/boundaries/nova-scotia/PROVENANCE.md
    #
    # ⛔ LICENCE UNRESOLVED — see `licence` / `notes` at the bottom. This spec is
    # cleared to PARSE and to `--compare`; it is NOT cleared to serve from
    # /api/public/v1/boundaries/*. The load decision is the operator's, not this
    # file's.
    "nova-scotia": BoundarySpec(

        jurisdiction="nova-scotia",

        # 1,817 polling divisions assembled from 5 paged ArcGIS `f=geojson` requests
        # (400/page). Concatenation of a paginated retrieval only — no geometry,
        # attribute or CRS was altered on the way in.
        source_path="nova-scotia/current/elections-ns-ed-pd-2026-04-09.geojson",

        # ⛔ 4326, NOT 3857 — and the service will tell you otherwise.
        #
        # The ENS_PD_ED FeatureServer DECLARES `spatialReference.wkid 102100 /
        # latestWkid 3857` (Web Mercator). That is the layer's storage/display SR.
        # ArcGIS reprojects on `f=geojson` export, and the STAGED BYTES are decimal
        # degrees: the first coordinate in the file is
        # [-65.5861868356846, 44.7576376853275], which is a lat/lon pair in Nova
        # Scotia. In 3857 the same point would be ~[-7.30e6, 5.57e6] metres.
        #
        # There is no `crs` member to arbitrate (verified: `doc["crs"] is None`), so
        # the only evidence is the coordinate magnitudes, and they are unambiguous.
        # Rule 2 says declare, never sniff — this declaration is of the ARTEFACT's
        # CRS, which is what ST_Transform consumes. Setting 3857 here is the inverse
        # of the Fort Erie bug: instead of relabelling projected metres as degrees,
        # it would treat degrees as metres and transform every district to a
        # sub-millimetre speck within ~600 m of Null Island.
        src_epsg=4326,

        level="provincial",
        province_territory="NS",

        # ⛔ Generation-free, per rule 5. Deliberately differs from the
        # `nova-scotia-electoral-districts-2019` prefix on the 55 rows we hold, so
        # the cutover is an insert plus a re-key rather than an in-place overwrite.
        # NS is one of the few jurisdictions where source_set and id_prefix already
        # agree on the held rows, so the re-key is a clean string swap on both.
        source_set="nova-scotia-electoral-districts",
        id_prefix="nova-scotia-electoral-districts",

        authority="elections-nova-scotia",

        # The generation label. 2019 stays free for the outgoing 55-district set,
        # whose held rows currently carry the uninformative literal 'current' and
        # will be re-labelled by the cutover migration.
        boundaries_version="2026",

        # ⛔ LEGAL in-force date. Royal Assent of Bill 203, *An Act to Amend Chapter 1
        # (1992 Supplement) of the Revised Statutes, 1989, the House of Assembly Act*
        # — CHAPTER 10 OF THE ACTS OF 2026, 1st Session, 65th General Assembly.
        #
        # ⚠ THE DOSSIER CREDITS BILL 205; THAT IS THE WRONG BILL. Both bills got
        # Royal Assent on 2026-04-09, so the DATE is right, but the instrument is
        # not: Bill 205 is *Elections Act (amended) and House of Assembly Act
        # (amended)* — election-administration modernisation, with no district list
        # in it — while Bill 203 is the one that carries the boundary change:
        #   s.2(1)(a) "striking out 'fifty-five' both times it appears and
        #             substituting 'fifty-six' in each case"
        #   s.2(1)(b) 'adding "Chéticamp–Margarees–Pleasant Bay" in its alphabetical
        #             place'
        #
        # ⛔ COMMENCEMENT IS ON ASSENT, not on proclamation and not at dissolution —
        # this is the NB / Nunavut / Yukon trap and Nova Scotia does NOT fall into
        # it. Bill 203 has NO commencement section at all, so the Interpretation Act
        # default (in force on Royal Assent) applies, and the Act's own transitional
        # section proves that reading rather than merely permitting it:
        #   s.4(2) "The electoral district of Chéticamp–Margarees–Pleasant Bay is
        #          deemed, ON THE COMING INTO FORCE OF THIS ACT, to have become
        #          vacant within the meaning of Section 10 of Chapter 1."
        # A seat cannot be deemed vacant at assent unless it legally exists at
        # assent. Corroborated by events: the resulting by-election was held
        # 2026-06-23 and seated Claude Bourgeois (PC) — a general election has not
        # intervened, so a dissolution-triggered commencement is factually excluded.
        #
        # ⚠ Bill 205 DOES carry delayed commencement, on two sections only (s.21 by
        # proclamation, s.40 "on and after the dissolution or the determination by
        # the effluxion of time of the present House of Assembly"). Neither touches
        # boundaries. Anyone re-reading 205 and finding those clauses should not
        # conclude the map is deferred — 203 is the boundary instrument.
        #
        # ⚠ Metadata corroborates for once: Elections NS stamped RELEASE_DATE
        # "April 9, 2026" on exactly the changed features, same day as assent.
        effective_from=date(2026, 4, 9),
        effective_to=None,

        name_field="ED_NAME",

        # ⚠ Stays None deliberately — Elections NS ships NO French field, despite
        # `Chéticamp-Margarees-Pleasant Bay`, `Argyle`, `Clare` and `Richmond` being
        # the protected Acadian districts. And do NOT set `name_split`: the accented
        # names here are single bilingual-neutral forms, not "English / Français"
        # pairs like New Brunswick's `PED_Names_`.
        name_fr_field=None,

        # ★ `ED_NO` is the authority key AND the dissolve key — zero-padded '01'..'56'.
        # Distinct from `politicians.nslegislature_slug`, which is a MEMBER slug, not
        # a district id (same distinction as Alberta's `ab_assembly_mid`).
        authority_id_field="ED_NO",

        # ⛔ POLLING DIVISIONS, NOT DISTRICTS — 1,817 features for 56 districts, the
        # most extreme instance of the one-row-per-district trap in the corpus.
        # `ED_NO` alone is not unique; `(ED_NO, PD_NO)` is (1,817 distinct pairs,
        # verified). Dissolving on `ED_NO` unions ~32 polls per district.
        #
        # ⚠ Do NOT reach for `ED_NAME` as the dissolve key instead. It happens to be
        # 1:1 with ED_NO in this file, but the name is a label carried redundantly on
        # every division, and polling-division files routinely blank it on some rows;
        # ED_NO is the field the agency actually keys on.
        dissolve_by="ED_NO",

        # ⚠ No row_filter. Unlike PEI — which carries 26 junk rows at DIST_NO = 0
        # that would mint a phantom district — every one of NS's 1,817 features is a
        # real polling division with a populated ED_NO. Verified: 0 empty ED_NO, 0
        # empty ED_NAME, 56 distinct ED_NO, contiguous '01'..'56'.
        #
        # ⚠ In particular do NOT filter on `RELEASE_DATE`. It partitions the file
        # into "September 1, 2020" (1,781 features, 54 unchanged districts) and
        # "April 9, 2026" (36 features — 26 polls in reshaped ED_NO 34 Inverness, 10
        # polls in new ED_NO 56). That is a per-feature CHANGE STAMP, not a validity
        # window: all 1,817 features are the geography in force today, and keeping
        # only the 2026 rows would load 2 districts and drop 54.
        row_filter=None,

        # 56 seats. Statutory: House of Assembly Act s.4(1) as amended by Bill 203
        # s.2(1)(a) ("fifty-five" -> "fifty-six"). Independently confirmed against
        # the Assembly's own member roster at nslegislature.ca/members/profiles,
        # which lists 56 profiles for Assembly 65 including Claude Bourgeois for
        # Chéticamp-Margarees-Pleasant Bay. The file has 56 distinct ED_NO.
        #
        # ⚠ 55 is the number to be suspicious of: it is the 2019 commission's count,
        # it is what we still hold, and it is what a stale secondary source reports.
        expect_districts=56,

        # ⛔ NO LICENCE. Not "permissive", not "unclear" — none stated anywhere.
        # AGOL item d9e8704a97f94dd9b517383c1e4e2c07: `licenseInfo: null`,
        # `accessInformation: null`; FeatureServer `copyrightText` is the empty
        # string; item description reads "DO NOT DELETE Electoral Geography for
        # refence in applications" — an internal service that happens to be publicly
        # readable, not a data publication. `access: public` is an ArcGIS SHARING
        # setting, not a copyright grant.
        licence=None,

        notes="⛔ REDISTRIBUTION BLOCKED. Elections NS states no licence on the "
              "authoritative service, the NS Open Data portal carries no provincial "
              "electoral boundary product (only MUNICIPAL polling districts — wrong "
              "level), and the Open North mirror we currently serve is the "
              "non-transferable 'Distributed with permission from the Government of "
              "Nova Scotia' class, which is Open North's permission and not ours. "
              "Our 55 held rows are therefore ALREADY being redistributed through "
              "/api/public/v1/boundaries/* without a grant — a live compliance gap "
              "that this generation inherits rather than creates. Unlike Ontario "
              "(click-through hiding a genuinely open licence) there is no route "
              "research can unlock; it needs a direct request to Elections NS. "
              "⚠ Chéticamp-Margarees-Pleasant Bay is the only accented ED_NAME; the "
              "file is UTF-8 JSON so there is no .cpg/cp1252 hazard here, unlike the "
              "shapefile jurisdictions. "
              "⚠ Statute vs data spell the new district DIFFERENTLY: Bill 203 uses "
              "EN DASHES ('Chéticamp–Margarees–Pleasant Bay'), ED_NAME uses ASCII "
              "hyphens ('Chéticamp-Margarees-Pleasant Bay'). slugify() collapses "
              "both to 'cheticamp-margarees-pleasant-bay', so the constituency_id is "
              "identical either way — but `name` will load the hyphen form, and any "
              "future statute-text join must normalise. "
              "⛔ INVERNESS WAS NOT RENAMED. The 2025 commission proposed "
              "'Inverness-We'koqma'q' and secondary reporting (incl. Wikipedia-fed "
              "search summaries) still repeats it, but the enacted Bill 203 s.2(3) "
              "adds subsection (2B) speaking of 'the electoral district of "
              "Inverness ... the remaining part', with no rename anywhere in the "
              "Act; ED_NAME 34 is 'Inverness' and the Assembly roster lists Kyle "
              "MacQuarrie for 'Inverness'. A rename would have looked like a second "
              "delta and broken a name-keyed load. "
              "★ ROSTER GAP THIS LOAD EXPOSES: the seat count moved to 56 but we "
              "hold 55 active NS politicians and no row for Claude Bourgeois, so "
              "cheticamp-margarees-pleasant-bay will load with no member attached "
              "until ingest-ns-mlas re-runs.",

    ),
    # Draft BoundarySpec — Newfoundland and Labrador, 2015 commission (40 districts).
    #
    # Executed by `load-boundaries --spec-file` with boundary_loader's namespace
    # pre-populated: BoundarySpec, date, SPECS and slugify are already in scope.
    #
    # Dossier: docs/research/boundaries/newfoundland-labrador.md
    #
    # ⛔⛔ THE AUTHORITY'S ONLY KEY FIELD CARRIES A TYPO, and there is no ID field to
    # fall back on. See `_normalise_dist_name` below — that helper is load-bearing,
    # not cosmetic, and deleting it silently mints a 41st slug nobody holds.
    "newfoundland-labrador": BoundarySpec(

        jurisdiction="newfoundland-labrador",
        source_path="newfoundland-labrador/current/NL_EB_Poly_50k.zip",
        # Flat members, no directory prefix. Named explicitly rather than left to the
        # single-.shp scan so a future re-issue that bundles a second layer fails
        # loudly instead of picking one.
        zip_member="NL_EB_Poly_50k_Upload.shp",

        # ⛔ THERE IS NO EPSG FOR THIS PROJECTION. The .prj declares a custom
        # `SESA-TM` with no AUTHORITY clause, transcribed verbatim below. Three
        # parameters each rule out the plausible guesses:
        #   • Scale factor 0.998, NOT UTM's 0.9996.
        #   • False easting 1,000,000, NOT UTM's 500,000.
        #   • Datum WGS84, NOT NAD83 — so it is also not any NAD83 MTM zone.
        # Central meridian -59.5 sits between MTM zones and matches nothing standard.
        # `+k` is the WKT's Scale_Factor; +lat_0 is Latitude_Of_Origin (0.0).
        #
        # ⛔⛔ SRID IS PER-FILE, NEVER PER-JURISDICTION. NL's PRIOR (2011, 48-district)
        # generation is EPSG:2961 — NAD83(CSRS) / UTM 21N, a completely different CRS
        # from the same agency. Anything that hardcodes one SRID for "NL" corrupts the
        # other generation.
        #
        # ⚠ The dossier's build note suggested registering this in `spatial_ref_sys`
        # under a private 900000+ SRID. Don't — `src_proj4` reaches ST_Transform's
        # (geom, from_proj text, to_srid int) overload directly and leaves the DB
        # schema untouched. Ontario is the precedent.
        src_epsg=None,
        src_proj4=(
            "+proj=tmerc +lat_0=0 +lon_0=-59.5 +k=0.998 "
            "+x_0=1000000 +y_0=0 +datum=WGS84 +units=m +no_defs"
        ),

        level="provincial",
        province_territory="NL",

        # ★ A6: NL is the one jurisdiction whose held prefix is ALREADY generation-
        # free, so unlike SK/ON there is no prefix rename in the cutover — the 36 rows
        # we hold sit on exactly this string today.
        source_set="newfoundland-and-labrador-electoral-districts",
        id_prefix="newfoundland-and-labrador-electoral-districts",
        authority="elections-newfoundland-and-labrador",
        boundaries_version="2015-commission",

        # First date on which these boundaries determined anyone's representation:
        # the 2015 general election. ⚠ NOT firmly established as a LEGAL commencement
        # — the Electoral Boundaries Act (RSNL1990 c. E-4) sets 40 districts at
        # s. 13(1) and requires the report be tabled at s. 14(2), but names no
        # proclamation, order-in-council or automatic in-force trigger. Unlike BC's
        # Electoral Districts Act s. 6, there is nothing to cite.
        # ⛔ NOT the dataset metadata date of 2015-09-10 — a publication artifact that
        # precedes first use by three months.
        effective_from=date(2015, 11, 30),
        # Still in force. s. 13(2) requires the next commission "in the calendar year
        # beginning in 2026 … as soon as is convenient after March 31" — that
        # commission had not reported as of 2026-08-19, and its map could not bind
        # before a subsequent general election in any case (the 40 districts below are
        # the ones contested on 2025-10-14).
        effective_to=None,

        # ⛔ THE ENTIRE ATTRIBUTE SCHEMA IS ONE FIELD. dBase III, 40 records, one
        # C(50) column. No OBJECTID, no code, no population — nothing. The name is the
        # only candidate key, which is what makes the typo above a total key failure
        # rather than a cosmetic blemish.
        name_field="DIST_NAME",
        name_fr_field=None,   # no French forms published
        name_split=None,      # single-language field, no separator to split on
        # ⛔ None because the field does not exist, not because we chose not to use
        # one. `authority_district_id` stays NULL for all 40 rows.
        authority_id_field=None,
        # ⛔ slug_field cannot express the name correction below. Since the Stage-0
        # changes it DOES drive the constituency_id (`slug_src` :420, `cid` :494), so
        # the obstacle is not mechanical — it is that slug_field names a FIELD, and
        # DIST_NAME is the entire schema. Pointing it at the only column there is
        # re-reads the same typo. slug_field solves "key on a different column"
        # (federal FED_NUM); `name_fixups` below solves "the one column is wrong for
        # one row".
        slug_field=None,

        # One record per district, already — NL is heavily islanded but the file
        # stores each district's fragments as one multipart shape, so there is
        # nothing to dissolve and every part accumulates under one key anyway.
        dissolve_by=None,
        row_filter=None,
        # ⛔ THE AUTHORITY IS WRONG HERE, which inverts the usual direction of
        # deference — the one such case in the corpus.
        #
        # `DIST_NAME` is Newfoundland's ENTIRE attribute schema: no OBJECTID that
        # means anything, no district number, nothing. So a misspelling in it is not
        # a cosmetic defect, it is total key failure for that district — the row
        # would mint `…/cartwright-lanse-aux-clair`, match nothing we hold, and leave
        # the real district both duplicated and unattached.
        #
        # "L'Anse aux Clair" is ungrammatical and names no place. Three independent
        # confirmations that "au" is right, one of them the publisher's own website:
        #   • Elections NL serves the poll map at
        #     `…/pollmaps/Cartwright%20-%20L'Anse%20au%20Clair.pdf`
        #   • the agency's own 2011 file spells it `Cartwright-L'Anse au Clair`
        #   • our rows carry `Cartwright—L'Anse au Clair`
        #
        # ⚠ Exact-string keyed, so a corrected re-issue of the file makes this a
        # no-op rather than re-breaking the name. The CLI prints `name_fixups=` so
        # the day it stops matching is visible.
        name_fixups={
            "Cartwright - L'Anse aux Clair": "Cartwright - L'Anse au Clair",
        },

        # 40 = s. 13(1) of the Act, the 40 returning offices used at the 2025-10-14
        # general election, and the file's own record count. A mistyped name_field
        # does not KeyError (props.get returns None → every feature rejected), so
        # without this guard a broken run prints districts=0 and exits 0.
        expect_districts=40,

        licence="ogl-nl-1.0",
        notes=(
            "Elections NL / NL Open Data portal dataset 361, file 3323. Open "
            "Government Licence – Newfoundland and Labrador v1.0: commercial use and "
            "redistribution permitted with attribution. Gate-free direct download, no "
            "agreement to accept. Encoding UTF-8 per the lowercase .cpg sidecar — "
            "load-bearing for the four apostrophe districts. "
            "⚠ The portal labels this 'the final version of the PROPOSED electoral "
            "boundaries'; the agency published no separate post-enactment file. Names "
            "and count match the enacted House exactly, so it is almost certainly "
            "identical, but 'proposed' is the publisher's own word. "
            "⚠ Name separator is a SPACED hyphen ('Baie Verte - Green Bay') where our "
            "rows use an unspaced em dash; slugify() folds both to '-', so this costs "
            "nothing on the slug and everything on a raw string join."
        ),

    ),
    # Yukon — draft BoundarySpec. 21 districts, Electoral District Boundaries Act,
    # S.Y. 2024, c. 14, in force on the 2025-10-03 dissolution of the 35th Assembly.
    #
    # Executed by `load-boundaries --spec-file` with boundary_loader's namespace
    # pre-populated: BoundarySpec, date, SPECS and slugify are already in scope.
    #
    # Research: docs/research/boundaries/yukon.md
    "yukon": BoundarySpec(

        jurisdiction="yukon",
        # ⚠ THREE publications of the same 21 polygons exist and their FIELD NAMES
        # DIFFER. This spec is written against the Elections Yukon AGOL GeoJSON only:
        #   • this file (AGOL FeatureServer)         → ELECTORAL_ / FR_ELECTOR
        #   • GeoYukon Yukon_Electoral_Districts.shp → ELECT_NAME / FR_ELECNAM
        #   • GeoYukon MapServer/75 REST             → ELECTORAL_DISTRICT_NAME /
        #                                              FR_ELECTORAL_DISTRICT_NAME
        # Swapping source_path without also swapping name_field/name_fr_field yields
        # 21 features with an empty name field — which group_features rejects, so the
        # run fails loudly rather than loading blanks. Verified on the staged file:
        # properties are exactly FID, ELECTORAL_, FR_ELECTOR, Shape_Leng, Shape_Area,
        # Shape__Area, Shape__Length.
        source_path=(
            "yukon/current/Approved_Yukon_Electoral_Districts_2024.geojson"
        ),
        # ⛔ 4326 because THIS distribution is already geographic — the file's own
        # crs member declares {"type":"name","properties":{"name":"EPSG:4326"}} and
        # it was pulled with outSR=4326. The transform is then a no-op, but it is
        # still declared and still routed through ST_Transform (rule 1); nothing
        # here relies on ST_SetSRID alone.
        # ⚠ If anyone switches source_path to Yukon_Electoral_Districts.shp.zip, this
        # MUST become 3578 — NAD83 / Yukon Albers, projected metres. The .prj carries
        # no AUTHORITY node so the code is assigned by parameter match, and it is NOT
        # 3579 (NAD83(CSRS) / Yukon Albers): the .prj datum is plain
        # D_North_American_1983. Both SRIDs already exist in spatial_ref_sys.
        src_epsg=4326,
        level="provincial",
        province_territory="YT",
        # ⛔ Generation-free per rule 5. What we hold today is prefixed
        # `yukon-electoral-districts-2015/…`; dropping the year lets the 15
        # name-stable districts keep their constituency_id across the cutover, so
        # only the 6 genuinely new districts need new keys and no `politicians`
        # UPDATE is needed for the survivors.
        source_set="yukon-electoral-districts",
        id_prefix="yukon-electoral-districts",
        authority="elections-yukon",
        # In-force year, matching the `nunavut` entry's convention (the closest
        # analogue: territory, no district-ID field, Act in force on dissolution).
        # ⚠ Yukon has the same year ambiguity BC does — the Act, the commission
        # report and the CEO's map issue all say 2024; the map only governed from
        # 2025. The in-force year is chosen so the label agrees with effective_from.
        # It leaves "2016" free for the prior generation (in force 2016-10-07), whose
        # 19 rows currently carry the useless literal 'current'. Coordinator may
        # override in the cutover migration; nothing else keys off this value.
        boundaries_version="2025",
        # ⛔ LEGAL in-force date — the DISSOLUTION of the 35th Legislative Assembly,
        # 2025-10-03 — NOT the 2024-11-21 assent and NOT the 2025-11-03 polling day.
        # Electoral District Boundaries Act, S.Y. 2024, c. 14 comes into force on
        # dissolution, and Elections Yukon said so outright: "Until the next
        # territorial election is called, and the Legislative Assembly dissolved, the
        # current 19 electoral districts, and the 19 Members of the Legislative
        # Assembly remain unchanged." Using assent would assert the 21-district map
        # governed for the ~11 months in which Yukon demonstrably had 19 districts
        # and 19 sitting members.
        # ⚠ Competing dates recorded so nobody re-derives them: 2024-11-21 (assent,
        # and the date stamped on the CEO's official map issue), 2024-10-09 (final
        # commission report tabled), 2025-11-03 (polling day). None is the in-force
        # date.
        effective_from=date(2025, 10, 3),
        effective_to=None,
        # ⚠ Truncated field names, an ArcGIS artefact — the underlying columns are
        # ELECTORAL_DISTRICT_NAME / FR_ELECTORAL_DISTRICT_NAME. Do not "fix" them.
        name_field="ELECTORAL_",
        # ★ Yukon is one of the few jurisdictions publishing official French district
        # names, and they are populated on all 21 features — none blank, so the
        # loader's `or None` never fires here. Measured on the staged file: 11 differ
        # from the English form ("Copperbelt Nord", "Lac Laberge", "Lacs du Sud",
        # "Whitehorse Ouest", the four Nord/Sud pairs, "Whistle Bend Nord/Sud") and 10
        # are byte-identical because the name is a proper noun or already French
        # ("Klondike", "Kluane", "Takhini", "Vuntut Gwitchin", "Mountainview",
        # "Porter Creek Centre", "Whitehorse Centre", and the three spaced compounds).
        # ⓘ No accented characters occur in either language on this generation, so
        # the .cpg / encoding trap that bit NWT does not arise here. The lowercase
        # .cpg on the shapefile distribution declares UTF-8 regardless.
        name_fr_field="FR_ELECTOR",
        # ⛔ THERE IS NO DISTRICT ID FIELD in any of the three publications — no code,
        # no number, no stable key. `FID` here (and `OBJECTID` on the GeoYukon REST
        # layer) is an ArcGIS row ordinal that is not stable across republication;
        # persisting it would look like an authority key and silently rot. Identity is
        # the slugified name, which is also how our existing 19 rows are keyed, so the
        # cutover join is exact. Same deliberate exception as Nunavut.
        authority_id_field=None,
        # 21 districts — 13 Whitehorse, 8 rural — per the Electoral District
        # Boundaries Commission's final report (tabled 2024-10-09) as enacted, and
        # confirmed against the 2025 general election, which returned 21 members.
        # The file has 21 features → 21 distinct ELECTORAL_ → 21 distinct slugs, and
        # ⓘ max parts = 1: every district is a single simple Polygon (ST_Multi
        # required on insert). No islands, no holes, nothing to dissolve — rule 3
        # does not bite here. If a future re-issue exceeds 21 records, the format
        # changed.
        expect_districts=21,
        licence="ogl-yukon-2.0",
        notes="Open Government Licence – Yukon 2.0 (CKAN license_id 'OGL-Yukon-2.0' "
              "on both electoral datasets). Plain GET, no click-through, no account, "
              "no registration anywhere in the path. "
              "⚠ The licence BODY was never read — both licence URLs sit on "
              "yukon.ca / open.yukon.ca/data/* which are Cloudflare-403 to every "
              "server-side fetch, so redistribution and attribution clauses are "
              "UNVERIFIED and are deliberately not quoted. The licence identity is "
              "machine-confirmed from the CKAN API; a human with a browser closes "
              "this in one page load. "
              "Attribution asserted by the data itself, verbatim and safe to carry "
              "regardless: AGOL licenseInfo 'Open Government Licence - Yukon "
              "(https://open.yukon.ca/data/open-government-licence-yukon)' and "
              "GeoYukon copyrightText 'Government of Yukon on behalf of Elections "
              "Yukon'. Provenance string from the AGOL item: 'Official Electoral "
              "Districts of the Yukon, dated November 21, 2024, issued under the "
              "authority of the Chief Electoral Officer.' "
              "⚠ NAME SPELLING DIFFERS FROM OUR ROSTER. This file spaces its "
              "compound names ('Mayo - Tatchun', 'Marsh Lake - Mount Lorne - Golden "
              "Horn'); politicians.constituency_name uses the unspaced form "
              "('Mayo-Tatchun'). slugify() collapses both to the same slug, so the "
              "cutover join on constituency_id is exact — but any join written "
              "against `name` as text will miss. Do not normalise the spelling in "
              "the loader; the agency's spelling is what `name` should carry. "
              "ⓘ Area sanity check: the 21 polygons sum to 485,298 km² geodesic "
              "against Yukon's 482,443 km² total (474,391 land + 8,052 fresh water), "
              "a +0.59% excess. The 21 do not overlap each other — ST_Union of all "
              "21 equals the plain sum to full float precision (485297.904234485 "
              "both ways) — and they are not clipped to lake edges, so a small "
              "positive excess from generalised linework along the BC / NWT / Alaska "
              "borders is the expected shape. Contrast BC, whose unclipped marine "
              "boundaries overshoot by ~10%. "
              "⛔ PRESERVATION: the 19 rows we hold under "
              "`yukon-electoral-districts-2015/*` are, as far as the research pass "
              "could determine, the ONLY machine-readable copy of the 2015 Yukon map "
              "in public circulation — GeoYukon republished the layer IN PLACE and "
              "the open.canada.ca mirrors were delisted. RETIRE them with "
              "effective_to = 2025-10-03; never delete or overwrite. Their "
              "effective_from is 2016-10-07 (Commissioner's Order 2016/01 dissolving "
              "the 33rd Assembly), currently recorded wrongly as 2023-01-01. The "
              "same overwrite-in-place risk applies to this 2024 layer going forward "
              "— the staged file is our own archive copy.",

    ),
    # Manitoba — 57 electoral divisions, 2018 Electoral Divisions Boundaries Commission.
    #
    # ★ THE FIRST MULTI-FILE SPEC. `source_path` and `zip_member` are parallel LISTS.
    # Manitoba is the only jurisdiction researched so far whose province arrives as two
    # shapefiles, NEITHER of which is complete: 25 Rural + 32 Urban = 57. A loader that
    # reads one archive gets a silently partial province that still looks plausible —
    # 25 rural divisions is not obviously wrong, and 32 Winnipeg divisions is a number
    # someone could mistake for "the urban file is the whole thing".
    #
    # ⚠⚠ BOTH OUTER ARCHIVES ARE NAMED `…_Public_Urban.zip`, AND THE FIRST ONE HOLDS
    # THE *RURAL* FEATURE CLASS. Verified with `unzip -Z1`:
    #
    # 2018_Final_ED_Manitoba_Public_Urban.zip  -> EDBC2018_FinalBoundaries_Rural.*    (25, Type=Rural)
    # 2018_Final_ED_Winnipeg_Public_Urban.zip  -> EDBC2018_FinalBoundaries_Winnipeg.* (32, Type=Urban)
    #
    # Never infer the layer from the archive name. `zip_member` is stated explicitly
    # below for exactly this reason — leaving it None would still work today (each
    # archive holds one .shp) but would silently follow the archive if Elections
    # Manitoba ever bundles both layers together.
    #
    # ⛔ `zip_member` MUST be a list here. A scalar `zip_member` is BROADCAST to every
    # path by `read_features()` (boundary_loader.py:291-294), so a single member name
    # would be looked up in both archives — one of which does not contain it — and the
    # run would die in `_open_shapefile_reader` with "missing .shp or .dbf". Loud, but
    # for the wrong reason.
    #
    # ⛔ DO NOT POINT THIS SPEC AT THE 2008 GENERATION IN `manitoba/prior/`. Same field
    # NAMES, different meanings: there `Area` is an area measurement in km² (St. Paul
    # 460, Riel 11), not the division number it is here, and `ED_French` does not
    # exist. A cross-generation copy-paste of this spec produces garbage
    # `authority_district_id` values with no error.
    "manitoba": BoundarySpec(

        jurisdiction="manitoba",
        # ★ LIST. Order is Rural then Winnipeg; `read_features()` concatenates in this
        # order and grouping is by name, so the order carries no meaning beyond the
        # per-file log lines it produces.
        source_path=[
            "manitoba/current/2018_Final_ED_Manitoba_Public_Urban.zip",
            "manitoba/current/2018_Final_ED_Winnipeg_Public_Urban.zip",
        ],
        # ★ PARALLEL LIST, positionally aligned with source_path above. Note the
        # inner names contradict the outer archive names — that is the trap, not a
        # transcription error.
        zip_member=[
            "EDBC2018_FinalBoundaries_Rural.shp",
            "EDBC2018_FinalBoundaries_Winnipeg.shp",
        ],
        # Not nested — `nested_zip` is Saskatchewan's zip-inside-a-zip case and is a
        # SCALAR shared by every path, so it could not express "nested in one file
        # only" anyway. Both MB archives are flat.
        nested_zip=None,
        # EPSG:26914 — NAD83 / UTM zone 14N. ⚠ The .prj carries NO AUTHORITY clause,
        # so the code is fixed by the parameters, which are byte-identical in both
        # files (verified): Transverse_Mercator, Central_Meridian -99.0,
        # False_Easting 500000.0, False_Northing 0.0, Scale_Factor 0.9996,
        # Latitude_Of_Origin 0.0, GRS 1980, metres.
        # ⛔ ZONE 14, NOT 13. Saskatchewan is EPSG:26913. Two adjacent prairie
        # provinces, two different codes — there is no shared "prairie EPSG".
        # ⛔ Coordinates are projected metres (Rural bbox X 311,759..1,109,222 /
        # Y 5,427,444..6,658,760), so ST_Transform is mandatory — a bare
        # ST_SetSRID(…, 4326) is the Fort Erie bug (rule 1).
        src_epsg=26914,
        src_proj4=None,
        level="provincial",
        province_territory="MB",
        # Generation-free per rule 5. ⚠ Our 56 existing rows carry the non-compliant
        # `manitoba-electoral-districts-2018` prefix; the cutover migration renames
        # those plus 56 `politicians` and 56 `politician_terms` rows onto this prefix
        # (168 mechanical updates), which is what lets every name-stable division keep
        # one constituency_id while `boundaries_version` does the switching.
        source_set="manitoba-electoral-districts",
        id_prefix="manitoba-electoral-districts",
        authority="elections-manitoba",
        # ⛔ ORDERING CONSTRAINT FOR THE CUTOVER MIGRATION. All 56 held rows currently
        # carry `boundaries_version = 'current'` (the opennorth.py default), and the
        # upsert key is (constituency_id, boundaries_version). If the migration
        # renames only the id prefix and leaves the version alone, this load inserts
        # 57 fresh rows ALONGSIDE the 56 old ones and every Manitoba district returns
        # two polygons. The migration must set BOTH — prefix and
        # `boundaries_version = '2018-commission'` — before the load runs; then the
        # load updates 56 in place and inserts only The Pas-Kameesak.
        boundaries_version="2018-commission",
        # LEGAL date, not the files' Last-Modified of 2021-03-25 (a re-upload of
        # 2018-commission data, not a 2021 redistribution).
        #
        # ⚠ Two candidate dates exist and they differ by 29 days:
        #   • 2019-08-12 — Manitoba Laws' consolidated-statute versioning of The
        #     Electoral Divisions Act, C.C.S.M. c. E40 states verbatim "This version
        #     was current from August 12, 2019 to February 25, 2022", and that
        #     version's Schedule carries the 2018-commission division names. The
        #     immediately preceding archived version runs to 2019-08-11. It is also
        #     the 42nd general election's writ-issue date.
        #   • 2019-09-10 — Elections Manitoba's own prose says the boundaries "went
        #     into effect for the 42nd provincial general election, held September
        #     10, 2019", i.e. polling day.
        # Ruling A2 takes the legal date, and the statute-version boundary is the
        # stronger legal evidence: the divisions were the law of the province on
        # 2019-08-12 whether or not anyone had yet voted in them. Elections Manitoba's
        # sentence describes the first election the map served, not its coming into
        # force — the same distinction Ontario's spec makes about "2022 General
        # Election" in its filename. Matches Saskatchewan, which is likewise pinned
        # to writ issue (2024-10-01) rather than polling day (2024-10-28).
        effective_from=date(2019, 8, 12),
        effective_to=None,
        name_field="ED",
        # ★ Manitoba publishes an OFFICIAL French name for every division and
        # `constituency_boundaries` has a `name_fr` column, so it is captured. 57/57
        # populated, none blank. Not derivable from the English name — 'The
        # Pas-Kameesak' → 'Le Pas-Kameesak', 'St. Boniface' → 'Saint-Boniface',
        # 'Red River North' → 'Rivière-Rouge-Nord'.
        name_fr_field="ED_French",
        # Two separate fields, not one bilingual field — this is NOT New Brunswick's
        # `name_split` case.
        name_split=None,
        # ★ `Area` is the DIVISION NUMBER, 1–57, dense, no gaps, no duplicates
        # (verified across the union). The name is a misnomer: its ratio to actual
        # area spans 0.000–13.577, i.e. no correlation with geography. `OBJECTID` is
        # also unique across the union but is an ArcGIS row id regenerated on export,
        # so it stays untrusted.
        # ⛔ Only true for the 2018 generation — see the module docstring.
        authority_id_field="Area",
        slug_field=None,
        # One record per division; the two multipart divisions (lake islands) arrive
        # as single MultiPolygon records rather than as separate rows, so nothing to
        # dissolve and `parts_merged` is 0. These are electoral divisions, not the
        # `VA_*` voting-area files — those are sub-division geography and out of scope.
        dissolve_by=None,
        # No junk rows: 57 features, 57 non-empty `ED`, 57 distinct `Area`.
        row_filter=None,
        # 57 = s.7(1) of The Electoral Divisions Act, quoted verbatim: "The province
        # is hereby divided into 57 electoral divisions." Also 57 seats contested at
        # the 2019 and 2023 general elections. ★ THE GUARD THAT CATCHES A PARTIAL
        # MULTI-FILE READ: if either archive silently dropped out, this fires at 25
        # or 32 before anything is written.
        expect_districts=57,
        # ⚠ No open licence. Elections Manitoba's footer reads "© 2026. All rights
        # reserved." and the maps page carries an informational-purposes-only
        # disclaimer. No click-through, no registration — the files are plain HTTPS
        # downloads — but no affirmative grant either. Recorded as provenance; per the
        # operator ruling of 2026-08-19 licensing does not gate the load, but this is
        # a more assertive posture than Saskatchewan's silence and redistribution
        # through /api/public/v1/boundaries/* is a separate operator decision.
        licence="none-published-all-rights-reserved",
        notes="Two shapefiles, neither complete (25 Rural + 32 Urban = 57); both "
              "outer archives are named …_Public_Urban.zip and the first holds the "
              "Rural feature class. Encoding UTF-8 per an UPPERCASE .CPG sidecar in "
              "each archive (the loader's lookup is case-insensitive; 'Lagimodière', "
              "'La Vérendrye' and every ED_French value verified intact). Our held "
              "vintage is already CORRECT and now measured on both sides: all 56 held "
              "rows match this generation at 99.8317% mean / 99.1905% min / 0 below "
              "95%, and against the staged 2008 prior generation the same 56 rows "
              "match only 42 names at 60.93% mean with 41 below 95% — so unlike BC/SK "
              "a HIGH --compare overlap is the expected result here. Manitoba is a "
              "provenance upgrade plus exactly one missing division, "
              "'The Pas-Kameesak'. Roster join is clean: the Legislative Assembly's "
              "constituency listing carries all 57 ED values verbatim.",

    ),
    "nova-scotia-municipal": BoundarySpec(
        jurisdiction="nova-scotia-municipal",
        source_path="municipal-atlantic/current/ns-municipal-polling-districts.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="NS",
        # ⚠ Scalars, unused: `set_resolver` supersedes both for every row. Kept
        # non-empty because BoundarySpec requires them and an empty string would
        # read as "no set" rather than "resolved per row".
        source_set="nova-scotia-municipal-districts",
        id_prefix="nova-scotia-municipal-districts",
        set_resolver=_ns_set_for,
        authority="nova-scotia-municipal-affairs",
        boundaries_version="2023",
        # Ruling A10.4 — the municipal election the boundaries first governed. Every
        # `reg_num` in the file is a 2023 N.S. Reg., and NS voted 2024-10-19.
        effective_from=date(2024, 10, 19),
        name_field="poll_dist",
        name_builder=_ns_label,
        authority_id_field="poll_dist",
        boundary_kind="district",
        row_filter=lambda p: (p.get("mu_code") or "").strip().upper() not in ("HX", "CB"),
        expect_districts=210,
        expect_sets=47,
        # Independently known: Truro numbers 3 wards, Wolfville is at large, New
        # Glasgow 3, Kings County 9. A set at 0 means _slugify_mun produced a slug
        # nobody expected.
        expect_per_set={
            "truro-town-districts": 3,
            "wolfville-town-districts": 1,
            "new-glasgow-town-districts": 3,
            "kings-districts": 9,
            "west-hants-districts": 11,
            # ★ The town/county pair, asserted explicitly: 10 districts for the
            # County of Antigonish and 1 for the Town of Antigonish. Merged, they
            # would have read as a plausible 11.
            "antigonish-districts": 10,
            "antigonish-town-districts": 1,
        },
        authority_id_unique_across_sets=True,
        licence="ns-ogl",
        notes="data.novascotia.ca gcep-xeci; Halifax + Cape Breton excluded by row_filter"
    ),
    "new-brunswick-municipal": BoundarySpec(
        jurisdiction="new-brunswick-municipal",
        source_path="municipal-atlantic/current/nb-lg-wards-quartiers.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="NB",
        # Unused — `set_resolver` supersedes both per row.
        source_set="new-brunswick-municipal-wards",
        id_prefix="new-brunswick-municipal-wards",
        set_resolver=_nb_set_for,
        authority="service-new-brunswick-geonb",
        boundaries_version="2023",
        # Ruling A10.4 — the municipal election these boundaries first governed. The
        # 2023 Local Governance Reform restructured every local government in the
        # province, and the first election under the new structure was 2022-11-28.
        # ⚠ The file carries no in-force date of its own; this is the reform's, and
        # `4-Lincoln` (Lincoln annexed into Fredericton by the reform) is the
        # evidence that this generation is the post-reform one.
        effective_from=date(2022, 11, 28),
        # ⛔ NOT `name_e` — see trap 1. `name_builder` supplies the label.
        name_field="ward",
        name_builder=_nb_label,
        authority_id_field="ward",
        boundary_kind="district",
        # ⚠ 312, not the 330 features in the file. 18 features merge into 7 wards,
        # and every one of those is a RURAL DISTRICT — which is exactly right: a
        # rural district is the unincorporated remainder between local governments,
        # so one of its wards is genuinely several disconnected pieces (Southeast
        # RD's at-large "ward" is 7 of them). Multi-part merging is the loader doing
        # its job, and `parts_merged` reports it.
        expect_districts=312,
        # 78 local governments + 15 rural districts. ⚠ Not 94: a naive count of
        # distinct `elect_comm` values gives 16 rural districts because the null row
        # counts as its own, when it is in fact Restigouche's second ward.
        expect_sets=93,
        expect_per_set={
            # ★ 13, not 12 — the assertion that proves we picked up the reform.
            "fredericton-wards": 13,
            "moncton-wards": 4,
            "saint-john-wards": 4,
            # The four LG/RD name collisions, asserted on both sides so a merge
            # cannot pass as a plausible total.
            "restigouche-rural-district-wards": 2,
        },
        licence="ogl-nb",
        notes="gnb.socrata.com 7zs3-pcvk; publisher of record GeoNB"
    ),
    "calgary-wards": BoundarySpec(
        jurisdiction="calgary-wards",
        source_path="municipal-alberta/current/calgary-wards_tz8z-hyaz.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="AB",
        source_set="calgary-wards",
        id_prefix="calgary-wards",
        authority="city-of-calgary",
        boundaries_version="2021",
        # Ruling A10.4 — the municipal election these wards first governed.
        effective_from=date(2021, 10, 18),
        # `label` is "WARD 1" in caps; name_builder gives the display form our other
        # numbered sets use, and the slug follows it to `ward-1` — which is what the
        # 14 sitting councillors are already attached to.
        name_field="label",
        name_builder=_calgary_label,
        authority_id_field="ward_num",
        boundary_kind="district",
        expect_districts=14,
        licence="see-terms-of-use-unread",
        notes="data.calgary.ca tz8z-hyaz; prior generation au4g-xjwh staged for comparison"
    ),
    "edmonton-wards": BoundarySpec(
        jurisdiction="edmonton-wards",
        source_path="municipal-alberta/current/edmonton-wards_nydb-6rce.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="AB",
        source_set="edmonton-wards",
        id_prefix="edmonton-wards",
        authority="city-of-edmonton",
        boundaries_version="2021",
        effective_from=date(2021, 10, 18),
        name_field="name_1",
        boundary_kind="district",
        row_filter=lambda p: (p.get("effdt_type") or "").strip() == "Current",
        expect_districts=12,
        licence="see-terms-of-use-unread",
        notes="data.edmonton.ca nydb-6rce; partitioned on effdt_type=Current"
    ),
    "winnipeg-wards": BoundarySpec(
        jurisdiction="winnipeg-wards",
        source_path="municipal-west/current/winnipeg-electoral-wards.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="MB",
        source_set="winnipeg-wards",
        id_prefix="winnipeg-wards",
        authority="city-of-winnipeg",
        boundaries_version="2018",
        effective_from=date(2018, 10, 24),
        name_field="name",
        authority_id_field="number",
        boundary_kind="district",
        expect_districts=15,
        licence="declared-ogl-pei-on-a-manitoba-dataset-unresolved",
        notes="data.winnipeg.ca t4cg-yaxs; prior generation mp2r-jeav"
    ),
    "toronto-wards": BoundarySpec(
        jurisdiction="toronto-wards",
        source_path="municipal-ontario/current/toronto-city-wards-4326.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="toronto-wards",
        id_prefix="toronto-wards",
        authority="city-of-toronto",
        boundaries_version="2018",
        effective_from=date(2018, 10, 22),
        name_field="AREA_NAME",
        authority_id_field="AREA_SHORT_CODE",
        boundary_kind="district",
        expect_districts=25,
        compare_held_source_set="toronto-wards-2018",
        licence="unspecified-on-ckan",
        notes="open.toronto.ca dataset city-wards, resource city-wards-data-4326.geojson"
    ),
    "regina-wards": BoundarySpec(
        jurisdiction="regina-wards",
        source_path="municipal-west/current/regina-wards-2024.geojson",
        src_epsg=26913,
        level="municipal",
        province_territory="SK",
        source_set="regina-wards",
        id_prefix="regina-wards",
        authority="city-of-regina",
        boundaries_version="2024",
        # Ruling A10.4 — Saskatchewan's fixed municipal election date, the one these
        # wards first governed.
        effective_from=date(2024, 11, 13),
        name_field="ID",
        name_builder=_regina_label,
        authority_id_field="ID",
        boundary_kind="district",
        expect_districts=10,
        licence="unstated-on-layer-city-owned-host",
        notes="opengis.regina.ca CGISViewer/WardsBoundaryReview2023/MapServer/0"
    ),
    "montreal-districts": BoundarySpec(
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
              "constituency_boundaries grows a parent column."
    ),
    "niagara-region-wards": BoundarySpec(
        jurisdiction="niagara-region-wards",
        source_path="municipal-ontario/current/niagara-region-ward-boundaries.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="niagara-region-wards",
        id_prefix="niagara-region-wards",
        set_resolver=_niagara_set,
        authority="niagara-region",
        boundaries_version="2018",
        # Ruling A10.4 — the municipal election these wards first governed.
        effective_from=date(2018, 10, 22),
        name_field="WARD",
        name_builder=_niagara_label,
        authority_id_field="WARD",
        boundary_kind="district",
        row_filter=_niagara_keep,
        expect_districts=38,
        expect_sets=11,
        expect_per_set={
            # ★ Six, and we hold four — this is the fix for the last two orphaned
            # constituency_ids in the table (fort-erie-wards/ward-2 and /ward-4).
            "fort-erie-wards": 6,
            "welland-wards": 6,
            "grimsby-wards": 4,
            "lincoln-wards": 4,
        },
        licence="niagara-region-reference-use-disclaimer",
        notes="AGOL org WxiLK82TWf8W3O3f, VoterTool_data/FeatureServer/1"
    ),
    "laval-districts": BoundarySpec(
        jurisdiction="laval-districts",
        source_path="municipal-quebec/current/laval-districts-2025.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="QC",
        source_set="laval-districts",
        id_prefix="laval-districts",
        authority="ville-de-laval",
        boundaries_version="2025",
        effective_from=date(2025, 11, 2),
        name_field="NOM",
        authority_id_field="NUMERO",
        boundary_kind="district",
        expect_districts=22,
        licence="cc-by-4.0",
        notes="donneesquebec.ca limites-des-districts-electoraux-des-dernieres-elections-municipales"
    ),
    "quebec-city-districts": BoundarySpec(
        jurisdiction="quebec-city-districts",
        source_path="municipal-quebec/current/quebec-city-districts-2025.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="QC",
        # ⚠ The existing set holds Québec's 5 BOROUGH polygons too, under
        # `quebec-boroughs/` ids. This spec loads districts only; the boroughs are
        # untouched and keep their own generation.
        source_set="quebec-districts",
        id_prefix="quebec-districts",
        authority="ville-de-quebec",
        boundaries_version="2025",
        effective_from=date(2025, 11, 2),
        name_field="NOM",
        authority_id_field="ID",
        boundary_kind="district",
        expect_districts=21,
        licence="cc-by-4.0",
        notes="donneesquebec.ca vque_43, resource vdq-districtelectoral.geojson"
    ),

    # ═══ Ontario large cities ═══════════════════════════════════════════
    # ⛔ IN-FORCE DATES SPAN TWENTY YEARS. The mirror stamped every one of these
    # `2023-01-01`, which is wrong by between 1 and 20 years in every case.
    # Ruling A10.4 dates a municipal map by the election it first governed:
    #   2006-11-13  Mississauga, Greater Sudbury
    #   2010-10-25  Windsor
    #   2014-10-27  Brampton, Kingston
    #   2018-10-22  Hamilton, London
    #   2022-10-24  Ottawa
    #   2026-10-26  Ottawa (new), London (new)
    # ⚠ 2006-11-13 is a MONDAY IN NOVEMBER. Ontario's fixed fourth-Monday-of-
    # October rule begins with 2010, so a date generated by that rule is wrong
    # for anything earlier.
    #
    # ⚠ Layer index is almost never 0 on these services — Hamilton 7, Windsor 5,
    # Brampton 3, Mississauga 2, London 8/9, Ottawa-2026 277. A harvester that
    # assumes /FeatureServer/0 gets HTTP 200 with empty metadata and then a 400
    # on /query, which reads as a working fetch until you count features.

    "ottawa-wards": BoundarySpec(
        jurisdiction="ottawa-wards",
        source_path="municipal-ontario/current/ottawa-wards-2022.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="ottawa-wards",
        id_prefix="ottawa-wards",
        authority="city-of-ottawa",
        boundaries_version="2022",
        effective_from=date(2022, 10, 24),
        # ★ Ottawa is the only city in the tranche that states its own end date:
        # "the ward boundaries in effect until November 14, 2026".
        effective_to=date(2026, 11, 14),
        name_field="NAME",
        name_fr_field="NAME_FR",
        authority_id_field="WARD",
        boundary_kind="district",
        expect_districts=24,
        licence="city-of-ottawa-open-data-licence-2.0",
        notes="open.ottawa.ca item 8973061e1b0c4cd09b4495088c04c310, "
              "Wards_2022_2026/FeatureServer/0. By-law 2021-3."
    ),

    # ⛔ FUTURE GENERATION — not live until the 2026-10-26 election. Loading it
    # as current would put the wrong councillor against every Ottawa address for
    # two months. By-law 2025-5 amends only wards 6, 9, 11, 13, 21 and 24; a
    # per-ward area comparison found exactly those six moving (24 +15.1%,
    # 9 -5.2%, 6 +3.1%, and slivers on 11/13/21) with the other 18 identical to
    # 0.00% — the by-law's own scope, confirmed from the geometry.
    # ⚠ Ward NAMES and numbers are unchanged across the redraw, so a name or
    # count check cannot tell these two generations apart. Ruling A7.
    "ottawa-wards-2026": BoundarySpec(
        jurisdiction="ottawa-wards-2026",
        source_path="municipal-ontario/current/ottawa-wards-2026.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="ottawa-wards",
        id_prefix="ottawa-wards",
        authority="city-of-ottawa",
        boundaries_version="2026",
        effective_from=date(2026, 10, 26),
        # ⚠ WARD_NAME_EN, not NAME — NAME on this layer is the generic "Ward 1".
        name_field="WARD_NAME_EN",
        name_fr_field="WARD_NAME_FR",
        authority_id_field="WARD_NUM",
        boundary_kind="district",
        expect_districts=24,
        licence="city-of-ottawa-open-data-licence-2.0",
        notes="maps.ottawa.ca Planning/MapServer/277, item "
              "925dfae1c59a45f6b1f643366ce74b37. By-law 2025-5 (2025-01-22). "
              "⚠ Pin by item id — layer index 277 sits in a shared MapServer "
              "and can shift on republish."
    ),

    "hamilton-wards": BoundarySpec(
        jurisdiction="hamilton-wards",
        source_path="municipal-ontario/current/hamilton-wards-2018.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="hamilton-wards",
        id_prefix="hamilton-wards",
        authority="city-of-hamilton",
        boundaries_version="2018",
        # ★ Dated from the publisher's own PRIOR layer, which is the strongest
        # evidence in the tranche: Ward_Boundaries_from_2001_2018 describes
        # itself as "in place from January 2001 to October 22, 2018".
        effective_from=date(2018, 10, 22),
        name_field="WARD",
        name_builder=_on_ward_label,
        authority_id_field="WARD",
        boundary_kind="district",
        expect_districts=15,
        licence="city-of-hamilton-open-data-terms",
        notes="open.hamilton.ca item c2c6e4fbf4ca4dbca39446bf8892df38, "
              "Ward_Boundaries/FeatureServer/7 (NOT /0). Carries "
              "COUNCILLOR_NAME/EMAIL/PHONE — richest roster payload in Ontario."
    ),

    "mississauga-wards": BoundarySpec(
        jurisdiction="mississauga-wards",
        source_path="municipal-ontario/current/mississauga-wards-2006.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="mississauga-wards",
        id_prefix="mississauga-wards",
        authority="city-of-mississauga",
        boundaries_version="2006",
        # By-laws 0212-2005 / 0211-2005 (council 2005-06-08) re-divided the city
        # into eleven wards; 2006-11-13 was the first election fought on them.
        # ⚠ Stability only PROVEN from 2013 forward (area-identical to the city's
        # own GF_2013 ward shapes across all 11). An amendment between 2006 and
        # 2013 cannot be ruled out; none is documented.
        effective_from=date(2006, 11, 13),
        name_field="WARD",
        name_builder=_on_ward_label,
        authority_id_field="WARD",
        boundary_kind="district",
        expect_districts=11,
        licence="city-of-mississauga-terms-of-use",
        notes="data.mississauga.ca item f1cad02b3a40422dac2ea99b59cc36a5, "
              "Ward_Boundaries/FeatureServer/2 (NOT /0). Carries COUNCILLOR."
    ),

    "brampton-wards": BoundarySpec(
        jurisdiction="brampton-wards",
        source_path="municipal-ontario/current/brampton-wards-2014.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="brampton-wards",
        id_prefix="brampton-wards",
        authority="city-of-brampton",
        boundaries_version="2014",
        # "City of Brampton Ward Boundaries as of December 1, 2014" — the start
        # of the 2014-2018 term. ★ Positively confirmed unchanged for 2026: the
        # city's ward-review page (updated 2025-03-26) says the review is paused
        # and "the current ward boundaries will remain in effect for the 2026
        # municipal election" — evidence of no-change, not merely its absence.
        effective_from=date(2014, 10, 27),
        name_field="WARD",
        name_builder=_on_ward_titlecase,
        authority_id_field="WARD",
        boundary_kind="district",
        expect_districts=10,
        # ⚠ "CC BY" with no version and no URL is not a resolved licence.
        licence="unresolved-bare-cc-by-string",
        notes="geohub.brampton.ca item 61b3e12fb4d74d078a15512dc3baf568, "
              "Planning_Local_Government/FeatureServer/3. ELECTORAL_AREA gives "
              "the paired-ward model as text: 1&5, 2&6, 3&4, 7&8, 9&10."
    ),

    "london-wards": BoundarySpec(
        jurisdiction="london-wards",
        source_path="municipal-ontario/current/london-wards-2018.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="london-wards",
        id_prefix="london-wards",
        authority="city-of-london",
        boundaries_version="2018",
        # ⛔ THE SOURCE LAYER IS TITLED "Election 2022 Wards" AND THE ANSWER IS
        # 2018. It is geometrically identical to London's own "Election 2018 and
        # 2022" layer (0 of 14 wards differ by >0.5%) and differs from the 2014
        # layer in 8 of 14. London redrew for 2018 and kept that map for 2022,
        # so under A10.4 the in-force date is the 2018 election. All four London
        # vintages have 14 wards numbered 1-14, so count, name and number are
        # useless as discriminators — only geometry settles it.
        effective_from=date(2018, 10, 22),
        name_field="Ward",
        name_builder=_on_ward_label_mixed,
        authority_id_field="Ward",
        boundary_kind="district",
        expect_districts=14,
        # ⚠ licenseInfo empty on the item and the Hub's Terms of Use link is
        # unfilled boilerplate (href="#"). Nothing machine-readable exists.
        licence="none-stated",
        notes="maps.london.ca OpenData_Elections/MapServer/8, item "
              "e22482d6693f4dcda4d423fbd7e6e77f, titled 'Election 2022 Wards'."
    ),

    # ⛔ FUTURE GENERATION — live only from the 2026-10-26 election. A genuine
    # redraw, not a re-digitisation: 13 of 14 wards move by more than 0.5% and
    # several drastically (ward 12 -50.7%, ward 7 -29.9%, ward 14 +28.0%).
    "london-wards-2026": BoundarySpec(
        jurisdiction="london-wards-2026",
        source_path="municipal-ontario/current/london-wards-2026.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="london-wards",
        id_prefix="london-wards",
        authority="city-of-london",
        boundaries_version="2026",
        effective_from=date(2026, 10, 26),
        name_field="Ward",
        name_builder=_on_ward_label_mixed,
        authority_id_field="Ward",
        boundary_kind="district",
        expect_districts=14,
        licence="none-stated",
        notes="maps.london.ca OpenData_Elections/MapServer/9, item "
              "b9f64459c2ae4b18895fdfd4560163ca, '2026 Electoral Wards'."
    ),

    "windsor-wards": BoundarySpec(
        jurisdiction="windsor-wards",
        source_path="municipal-ontario/current/windsor-wards-2010.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="windsor-wards",
        id_prefix="windsor-wards",
        authority="city-of-windsor",
        boundaries_version="2010",
        # By-law 133-2009 (council 2009-08-24) re-divided five two-member wards
        # into ten single-member wards, taking effect when the council elected
        # in 2010 was organised. ⚠ The city page carrying that text now 404s;
        # it was recovered from a 2024-03-09 Wayback snapshot, and the by-law
        # PDF itself has no snapshot at all.
        effective_from=date(2010, 10, 25),
        name_field="WARD",
        name_builder=_on_ward_titlecase,
        # ★ Windsor is the only Ontario city that splits name and number.
        authority_id_field="NUMBER",
        boundary_kind="district",
        expect_districts=10,
        licence="city-of-windsor-open-data-terms-of-use",
        notes="mappmycity.ca OpenDataServices/Boundaries/MapServer/5, item "
              "1647e48e0be748e2ba7d023cb9872ca4. ★ Fixes a partial ingest — we "
              "held 9 of 10 wards; Ward 2 was missing. Carries COUNCILLOR."
    ),

    "kingston-wards": BoundarySpec(
        jurisdiction="kingston-wards",
        source_path="municipal-ontario/current/kingston-districts-2014.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="kingston-wards",
        id_prefix="kingston-wards",
        authority="city-of-kingston",
        boundaries_version="2014",
        # Publisher's own description: "the realignment of the Electoral
        # Districts for the Municipal Election in 2014".
        #
        # ⛔ DO NOT MAP `ELECTION_YEAR` TO effective_from. Every row carries
        # ELECTION_YEAR='2022' and CURRENT_='Y' with 2022-2026 councillors
        # attached — that is a ROSTER currency stamp, not a boundary date. Using
        # it would date Kingston 2022-10-24, wrong by two full election cycles.
        # Kingston is the one source here whose data actively misstates its own
        # vintage; the boundary date exists only in the prose description.
        effective_from=date(2014, 10, 27),
        # Kingston calls them districts, not wards, and names them.
        name_field="DISTRICT_NAME",
        authority_id_field="DISTRICT_NUMBER",
        boundary_kind="district",
        expect_districts=12,
        licence="city-of-kingston-open-data-licence",
        notes="opendatakingston.cityofkingston.ca item "
              "00010f7cac69424d9157074a687e3d1b, "
              "Electoral_District_Boundary/FeatureServer/0. Carries "
              "COUNCILLOR_NAME, POPULATION, ELECTORS."
    ),

    "greater-sudbury-wards": BoundarySpec(
        jurisdiction="greater-sudbury-wards",
        source_path="municipal-ontario/current/sudbury-wards-2006.geojson",
        src_epsg=4326,
        level="municipal",
        province_territory="ON",
        source_set="greater-sudbury-wards",
        id_prefix="greater-sudbury-wards",
        authority="city-of-greater-sudbury",
        boundaries_version="2006",
        # Council adopted twelve single-member wards in 2005, replacing the six
        # two-member wards created at the 2001 amalgamation. Twenty years old,
        # and the mirror stamped it 2023-01-01. Council declined a review in
        # 2015 and again after 2019; the published layer is byte-identical to
        # the city's own Wards_2018 layer (same sha256).
        effective_from=date(2006, 11, 13),
        name_field="WARD",
        name_builder=_on_ward_label,
        authority_id_field="WARD",
        boundary_kind="district",
        expect_districts=12,
        licence="city-of-greater-sudbury-open-data-licence-ogl-on-1.0",
        notes="opendata.greatersudbury.ca item "
              "30b05ebcb3784d73a05744bc4935c9ef, "
              "Ward_Boundaries/FeatureServer/0. Geometry only, no roster."
    ),

}
