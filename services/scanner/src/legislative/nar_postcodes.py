"""
Postal-code centroids from the StatCan National Address Register.

Replaces the last runtime dependency on represent.opennorth.ca. See
`docs/research/boundaries/geocoding.md` for the source evaluation and
`db/migrations/0062_postcode_centroids.sql` for the target schema.

Source
------
StatCan National Address Register, catalogue 46-26-0002, under the Statistics
Canada Open Licence — explicit right to reproduce, distribute and sublicence.
Staged as a single ~1.67 GB zip at `data/boundaries/_geocoding/nar/202606.zip`
(5.88 GB uncompressed across 55 members).

Method
------
Per province, two CSV families keyed on `LOC_GUID`:

    Addresses/Address_<PR>[_part_N].csv   MAIL_POSTAL_CODE
    Locations/Location_<PR>[_part_N].csv  BG_LATITUDE / BG_LONGITUDE

Build a LOC_GUID -> coordinate map from the Location members, then stream the
Address members and average the coordinates of every civic address sharing a
postal code.

⚠ Address and Location part counts do NOT match (Quebec ships 6 address parts
against 4 location parts), so the members cannot be paired positionally. The
whole province's location map is built first.

Members are read **streamed from inside the zip** — extracting would put 5.88 GB
of CSV on disk for no benefit.

Coordinate choice
-----------------
`BG_LATITUDE`/`BG_LONGITUDE` (blockface centroid) is preferred, falling back to
`BF_REPPOINT_LATITUDE`/`BF_REPPOINT_LONGITUDE` (building representative point).

★ The fallback is not cosmetic: **17.2% of Ontario location rows carry only the
representative point**, and discarding them loses 12.9% of Ontario address rows.
With the fallback that miss rate is 0.4%.

Known coverage gap
------------------
NAR registers **civic addresses**, so a postal code with no civic address is
absent by construction — PO-box-only codes, rural-route-only codes, and
large-volume-receiver / government codes. `K1A 0A6` (House of Commons) has zero
NAR rows. National coverage is an estimated 73–92% of active postal codes, which
is why the API keeps a layered lookup rather than treating this table as
complete.

Memory
------
The LOC_GUID map is the cost centre. Keys are a 64-bit integer taken from the
UUID rather than the 36-character string, which keeps Ontario — the largest
province, 3.4M locations — at roughly 1 GB peak RSS and ~40 s.

⚠ The key width is load-bearing. A 32-bit key over Ontario's 3.4M locations would
produce ~1,350 birthday collisions, each silently assigning one address the
coordinates of an unrelated one — a wrong answer with no error. At 64 bits the
expected collision count across 4M keys is ~4e-7.
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import io
import logging
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from ..db import Database

log = logging.getLogger(__name__)

# StatCan PR code -> our 2-letter province/territory code.
PR_CODE_TO_PT = {
    "10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON",
    "46": "MB", "47": "SK", "48": "AB", "59": "BC", "60": "YT", "61": "NT",
    "62": "NU",
}

POSTCODE_RE = re.compile(r"^[A-Z][0-9][A-Z][0-9][A-Z][0-9]$")

# Write in chunks: the asyncpg pool sets command_timeout=60 (services/scanner/
# src/db.py), and a single multi-hundred-thousand-row statement will exceed it.
WRITE_BATCH = 5_000


@dataclass
class NarStats:
    provinces: int = 0
    location_rows: int = 0
    reppoint_fallbacks: int = 0
    address_rows: int = 0
    no_postcode: int = 0
    no_geometry: int = 0
    postcodes: int = 0
    rural_postcodes: int = 0
    written: int = 0
    by_province: dict[str, int] = field(default_factory=dict)


def _guid_key(guid: str) -> int:
    """
    64-bit key from a UUID string — cheaper than retaining 36-char strings across
    millions of rows.

    ⚠ Take 16 hex digits AFTER stripping dashes, not the first 16 characters of
    the raw string: a UUID's 9th character is a dash, so slicing first yields only
    14 hex digits (56 bits). Width matters — see the module docstring.
    """
    return int(guid.replace("-", "")[:16], 16)


def _members(zf: zipfile.ZipFile, pr: str) -> tuple[list[str], list[str]]:
    addrs = sorted(
        n for n in zf.namelist()
        if re.match(rf"Addresses/Address_{pr}(_part_\d+)?\.csv$", n)
    )
    locs = sorted(
        n for n in zf.namelist()
        if re.match(rf"Locations/Location_{pr}(_part_\d+)?\.csv$", n)
    )
    return addrs, locs


def _reader(zf: zipfile.ZipFile, name: str):
    """Stream a zip member as CSV rows. utf-8-sig strips the BOM these files carry."""
    with zf.open(name) as fh:
        yield from csv.reader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))


def build_province(
    zf: zipfile.ZipFile, pr: str, stats: NarStats
) -> dict[str, tuple[float, float, int, Optional[str]]]:
    """postcode -> (lat, lng, address_point_count, modal_city) for one province."""
    addrs, locs = _members(zf, pr)
    if not addrs or not locs:
        log.warning("NAR: PR %s has %d address / %d location members — skipping",
                    pr, len(addrs), len(locs))
        return {}

    coord: dict[int, tuple[float, float]] = {}
    for name in locs:
        rows = _reader(zf, name)
        hdr = next(rows)
        gi = hdr.index("LOC_GUID")
        la, lo = hdr.index("BG_LATITUDE"), hdr.index("BG_LONGITUDE")
        ra, ro = hdr.index("BF_REPPOINT_LATITUDE"), hdr.index("BF_REPPOINT_LONGITUDE")
        for row in rows:
            stats.location_rows += 1
            if row[la] and row[lo]:
                coord[_guid_key(row[gi])] = (float(row[la]), float(row[lo]))
            elif row[ra] and row[ro]:
                coord[_guid_key(row[gi])] = (float(row[ra]), float(row[ro]))
                stats.reppoint_fallbacks += 1

    acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    # Municipality tallies per postcode. A code can span municipalities, so the
    # loader keeps the modal name rather than whichever row it saw first.
    muni: dict[str, Counter] = defaultdict(Counter)
    for name in addrs:
        rows = _reader(zf, name)
        hdr = next(rows)
        gi, pc = hdr.index("LOC_GUID"), hdr.index("MAIL_POSTAL_CODE")
        mn = hdr.index("MAIL_MUN_NAME")
        for row in rows:
            stats.address_rows += 1
            code = row[pc].strip().upper().replace(" ", "").replace("-", "")
            if not POSTCODE_RE.match(code):
                stats.no_postcode += 1
                continue
            c = coord.get(_guid_key(row[gi]))
            if c is None:
                stats.no_geometry += 1
                continue
            a = acc[code]
            a[0] += c[0]
            a[1] += c[1]
            a[2] += 1
            town = row[mn].strip()
            if town:
                muni[code][town] += 1

    out: dict[str, tuple[float, float, int, Optional[str]]] = {}
    for k, v in acc.items():
        top = muni.get(k)
        city = top.most_common(1)[0][0].title() if top else None
        out[k] = (v[0] / v[2], v[1] / v[2], int(v[2]), city)
    return out


async def ingest_nar_postcodes(
    db: Database,
    zip_path: str,
    provinces: Optional[list[str]] = None,
    vintage: Optional[str] = None,
    dry_run: bool = False,
) -> NarStats:
    """
    Rebuild `public.postcode_centroids` from the staged NAR archive.

    Idempotent per province: rows are upserted on `postcode`, so re-running a
    single province refreshes exactly its codes and leaves the rest alone.
    """
    path = Path(zip_path)
    if not path.exists():
        raise FileNotFoundError(f"NAR archive not found: {path}")

    stats = NarStats()
    vintage = vintage or path.stem  # '202606.zip' -> '202606'
    targets = provinces or list(PR_CODE_TO_PT)

    zf = zipfile.ZipFile(path)
    try:
        for pr in targets:
            pt = PR_CODE_TO_PT.get(pr)
            if pt is None:
                log.warning("NAR: unknown PR code %r — skipping", pr)
                continue

            # The CSV parsing is CPU-bound and synchronous; keep the event loop
            # responsive so the jobs worker can still report progress.
            built = await asyncio.to_thread(build_province, zf, pr, stats)
            if not built:
                continue

            stats.provinces += 1
            stats.postcodes += len(built)
            stats.rural_postcodes += sum(1 for k in built if k[1] == "0")
            stats.by_province[pt] = len(built)

            if dry_run:
                log.info("NAR: [dry-run] PR %s (%s) -> %d postcodes", pr, pt, len(built))
                continue

            items = list(built.items())
            for i in range(0, len(items), WRITE_BATCH):
                chunk = items[i:i + WRITE_BATCH]
                await db.execute(
                    """
                    INSERT INTO public.postcode_centroids
                      (postcode, lat, lng, address_points, province, source,
                       source_vintage, built_at, city)
                    SELECT * FROM unnest(
                        $1::text[], $2::float8[], $3::float8[], $4::int[],
                        $5::text[], $6::text[], $7::text[], $8::timestamptz[],
                        $9::text[])
                    ON CONFLICT (postcode) DO UPDATE SET
                        lat            = EXCLUDED.lat,
                        lng            = EXCLUDED.lng,
                        address_points = EXCLUDED.address_points,
                        province       = EXCLUDED.province,
                        source         = EXCLUDED.source,
                        source_vintage = EXCLUDED.source_vintage,
                        built_at       = EXCLUDED.built_at,
                        city           = EXCLUDED.city
                    """,
                    [c for c, _ in chunk],
                    [v[0] for _, v in chunk],
                    [v[1] for _, v in chunk],
                    [v[2] for _, v in chunk],
                    [pt] * len(chunk),
                    ["statcan-nar"] * len(chunk),
                    [vintage] * len(chunk),
                    [dt.datetime.now(dt.timezone.utc)] * len(chunk),
                    [v[3] for _, v in chunk],
                )
                stats.written += len(chunk)

            log.info("NAR: PR %s (%s) -> %d postcodes written", pr, pt, len(built))
    finally:
        zf.close()

    return stats
