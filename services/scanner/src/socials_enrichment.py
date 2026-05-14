"""Socials enrichment from external sources (Team B backfill).

Phase 5 landed `politician_socials` with only 79 rows because ourcommons.ca
and assembly.ab.ca render their contact cards via JavaScript, which the
HTML-regex discovery pass couldn't see. This module backfills handles from
three additional sources:

  * Wikidata — SPARQL for every sitting Canadian federal/provincial/
    territorial legislator + their social properties (P2002/P2013/P2003/
    P2397/P4033/P7085/P6634/P12361).
  * openparliament.ca — MP JSON detail pages surface `other_info.twitter`
    (and sometimes a personal `web_site`) for most current federal MPs.
  * canada.masto.host — best-effort Mastodon lookup by candidate handle
    variations derived from each politician's name.

Every discovered (platform, url) pair is funneled through
`socials.upsert_social()`, so canonicalisation + `social_added` change
logging stays consistent with the Phase 5 normaliser.

Public API
----------
  enrich_from_wikidata(db, *, level=None)     -> int
  enrich_from_openparl(db)                     -> int
  enrich_mastodon_candidates(db)               -> int
  enrich_all_socials(db)                       -> None  (runs all three)

All three are re-entrant and skip politicians whose name+level can't be
matched back to our `politicians` table.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import unicodedata
from collections import Counter
from typing import Any, Iterable, Optional

import httpx
import orjson
from rich.console import Console

from .db import Database
from .socials import upsert_social

log = logging.getLogger(__name__)
console = Console()


# Identify ourselves to rate-limiting intermediaries. Wikidata's SPARQL
# service in particular asks every client to provide a project URL + contact.
ENRICH_USER_AGENT = (
    "CanadianPoliticalData-SocialsEnrichment/1.0 "
    "(+https://canadianpoliticaldata.org; admin@thebunkerops.ca)"
)


# ── Wikidata ──────────────────────────────────────────────────────────────

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Position-held (P39) item IDs for every sitting Canadian legislator role.
# Verified via wbsearchentities / manual lookup on 2026-04-13.
#   federal        : member of the House of Commons of Canada
#   ontario        : member of the Ontario Provincial Parliament (MPP)
#   alberta        : member of Alberta Legislative Assembly
#   bc             : member of the Legislative Assembly of British Columbia
#   quebec         : Member of the National Assembly of Quebec
#   manitoba       : member of the Legislative Assembly of Manitoba
#   saskatchewan   : Member of the Legislative Assembly of Saskatchewan
#   nova_scotia    : member of the Nova Scotia House of Assembly
#   new_brunswick  : member of the Legislative Assembly of New Brunswick
#   pei            : member of the Legislative Assembly of Prince Edward Island
#   nl             : member of the Newfoundland and Labrador House of Assembly
#   yukon          : member of the Yukon Legislative Assembly
#   nwt            : Member of the Legislative Assembly of the Northwest Territories
#   nunavut        : Member of the Legislative Assembly of Nunavut
WIKIDATA_POSITIONS: dict[str, dict[str, Optional[str]]] = {
    "federal":        {"qid": "Q15964890", "level": "federal",    "province": None},
    "ontario":        {"qid": "Q3305347",  "level": "provincial", "province": "ON"},
    "alberta":        {"qid": "Q15964815", "level": "provincial", "province": "AB"},
    "bc":             {"qid": "Q19004821", "level": "provincial", "province": "BC"},
    "quebec":         {"qid": "Q3305338",  "level": "provincial", "province": "QC"},
    "manitoba":       {"qid": "Q19007867", "level": "provincial", "province": "MB"},
    "saskatchewan":   {"qid": "Q18675661", "level": "provincial", "province": "SK"},
    "nova_scotia":    {"qid": "Q18239264", "level": "provincial", "province": "NS"},
    "new_brunswick":  {"qid": "Q18984329", "level": "provincial", "province": "NB"},
    "pei":            {"qid": "Q21010685", "level": "provincial", "province": "PE"},
    "nl":             {"qid": "Q19403853", "level": "provincial", "province": "NL"},
    "yukon":          {"qid": "Q18608478", "level": "provincial", "province": "YT"},
    "nwt":            {"qid": "Q45308871", "level": "provincial", "province": "NT"},
    "nunavut":        {"qid": "Q45308607", "level": "provincial", "province": "NU"},
}


# Wikidata social-property -> (platform_hint, url formatter)
# The SPARQL query returns bare handles (without a leading '@'); we wrap
# each into a canonical URL so socials.upsert_social() / canonicalize() can
# normalize it the same way it does for Open North payloads.
WIKIDATA_SOCIAL_PROPS: tuple[tuple[str, str, str], ...] = (
    # (var_name, platform_hint, url_template)
    ("twitter",   "twitter",   "https://twitter.com/{value}"),
    ("facebook",  "facebook",  "https://www.facebook.com/{value}"),
    ("instagram", "instagram", "https://www.instagram.com/{value}"),
    ("youtube",   "youtube",   "https://www.youtube.com/channel/{value}"),
    ("tiktok",    "tiktok",    "https://www.tiktok.com/@{value}"),
    ("linkedin",  "linkedin",  "https://www.linkedin.com/in/{value}"),
    ("mastodon",  "mastodon",  "_mastodon_"),   # special handling
    ("bluesky",   "bluesky",   "https://bsky.app/profile/{value}"),
)


def _build_wikidata_sparql(qids: Iterable[str]) -> str:
    """Build the SPARQL pulling every current legislator with any social."""
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
SELECT DISTINCT ?person ?personLabel ?posLabel
  ?twitter ?facebook ?instagram ?youtube ?tiktok ?linkedin ?mastodon ?bluesky
WHERE {{
  VALUES ?pos {{ {values} }}
  ?person p:P39 ?ps .
  ?ps ps:P39 ?pos .
  FILTER NOT EXISTS {{ ?ps pq:P582 ?end }}
  FILTER EXISTS {{
      {{ ?person wdt:P2002 [] }} UNION {{ ?person wdt:P2013 [] }}
    UNION {{ ?person wdt:P2003 [] }} UNION {{ ?person wdt:P2397 [] }}
    UNION {{ ?person wdt:P7085 [] }} UNION {{ ?person wdt:P6634 [] }}
    UNION {{ ?person wdt:P4033 [] }} UNION {{ ?person wdt:P12361 [] }}
  }}
  OPTIONAL {{ ?person wdt:P2002 ?twitter . }}
  OPTIONAL {{ ?person wdt:P2013 ?facebook . }}
  OPTIONAL {{ ?person wdt:P2003 ?instagram . }}
  OPTIONAL {{ ?person wdt:P2397 ?youtube . }}
  OPTIONAL {{ ?person wdt:P7085 ?tiktok . }}
  OPTIONAL {{ ?person wdt:P6634 ?linkedin . }}
  OPTIONAL {{ ?person wdt:P4033 ?mastodon . }}
  OPTIONAL {{ ?person wdt:P12361 ?bluesky . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def _mastodon_url_from_address(addr: str) -> Optional[str]:
    """'user@infosec.exchange' -> 'https://infosec.exchange/@user'."""
    addr = addr.strip().lstrip("@")
    if "@" not in addr:
        return None
    user, _, host = addr.partition("@")
    user = user.strip()
    host = host.strip().lower()
    if not user or not host:
        return None
    return f"https://{host}/@{user}"


def _normalize_name(name: str) -> str:
    """Lower-cased, punctuation-stripped, accent-folded name key.

    Wikidata stores names with diacritics; our DB usually matches. But
    Wikidata may omit middle names or reorder French-preposition names,
    so we reduce both sides to ``unicode-normalized ascii lower word list``
    and key on the sorted-unique-token tuple. That lets "Joël Lightbound"
    and "Joel Lightbound" collide while still preserving distinctness
    between e.g. "Mark Carney" and "Mark Carney Jr."
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^A-Za-z\s'\-]", " ", ascii_only).lower()
    tokens = [t for t in re.split(r"[\s'\-]+", cleaned) if t]
    # We key on the whole token sequence; middle-initials are dropped.
    tokens = [t for t in tokens if len(t) > 1]
    return " ".join(tokens)


async def _load_politician_index(
    db: Database,
    *,
    level: Optional[str] = None,
    include_inactive: bool = False,
) -> dict[tuple[str, str], str]:
    """Return {(level, name_key): politician_id} for politicians.

    When two distinct politicians share a name_key within a level, we
    keep the first and skip ambiguous matches; they'll be reported during
    enrichment. With ``include_inactive=True`` also pulls former members —
    needed when backfilling Wikidata socials for historical-roster rows
    so Hansard speech_references resolution improves on pre-current
    sessions.
    """
    where = "WHERE TRUE" if include_inactive else "WHERE is_active = true"
    args: list[Any] = []
    if level is not None:
        where += f" AND level = ${len(args) + 1}"
        args.append(level)
    rows = await db.fetch(
        f"SELECT id, name, level, province_territory FROM politicians {where}",
        *args,
    )
    idx: dict[tuple[str, str], str] = {}
    dupes: set[tuple[str, str]] = set()
    for r in rows:
        key = (r["level"], _normalize_name(r["name"]))
        if not key[1]:
            continue
        if key in idx:
            dupes.add(key)
            continue
        idx[key] = str(r["id"])
    if dupes:
        log.info("ambiguous name_keys skipped during indexing: %d", len(dupes))
    return idx


# ── Wikidata SPARQL retry/backoff ──────────────────────────────────────
# WDQS aggressively rate-limits during outages (their incident 797a132
# capped to 1 req/min). The enricher only issues ONE bulk request per
# run, so retrying through the rate-limit window costs minutes, not
# hours, and removes the operator step of "re-run later when WDQS is
# back" for transient outages.
#
# Knobs (env, defaults are sensible for an interactive run):
#   ENRICH_WIKIDATA_MAX_ATTEMPTS    (5)
#   ENRICH_WIKIDATA_RETRY_FLOOR_S   (65)  default wait if no Retry-After
#   ENRICH_WIKIDATA_RETRY_CAP_S     (600) absolute upper bound per wait
#
# Why a 65s floor: Wikidata's outage rule was "1 req/min". A 60s wait
# can race the bucket refill; 65s gives a 5s margin without
# meaningfully extending operator time.

WIKIDATA_MAX_ATTEMPTS = int(os.environ.get("ENRICH_WIKIDATA_MAX_ATTEMPTS", "5"))
WIKIDATA_RETRY_FLOOR_S = float(os.environ.get("ENRICH_WIKIDATA_RETRY_FLOOR_S", "65"))
WIKIDATA_RETRY_CAP_S = float(os.environ.get("ENRICH_WIKIDATA_RETRY_CAP_S", "600"))


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse a Retry-After header (seconds or HTTP-date). Returns None
    on parse failure so the caller falls back to the floor."""
    if not value:
        return None
    value = value.strip()
    # Seconds form: a bare integer.
    if value.isdigit():
        return float(value)
    # HTTP-date form: parse + diff against now.
    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone
        when = parsedate_to_datetime(value)
        delta = (when - datetime.now(timezone.utc)).total_seconds()
        return max(delta, 0.0)
    except Exception:  # noqa: BLE001
        return None


async def _wikidata_sparql_with_retry(
    client: httpx.AsyncClient,
    sparql: str,
) -> Optional[dict[str, Any]]:
    """Issue the SPARQL request, honoring Retry-After on 429s.

    Returns the parsed JSON on success, None when the retry budget is
    exhausted (so enrich_from_wikidata exits cleanly with 0 inserts,
    same as the pre-retry behaviour did on any failure).
    """
    for attempt in range(1, WIKIDATA_MAX_ATTEMPTS + 1):
        try:
            resp = await client.get(WIKIDATA_SPARQL, params={"query": sparql})
        except httpx.HTTPError as exc:
            # Network-layer failure (DNS, connect timeout, etc.). Treat
            # as retryable with the floor wait.
            if attempt >= WIKIDATA_MAX_ATTEMPTS:
                console.print(
                    f"[red]Wikidata SPARQL network failure after "
                    f"{attempt} attempt(s): {exc}[/red]"
                )
                return None
            console.print(
                f"[yellow]Wikidata SPARQL network failure (attempt "
                f"{attempt}/{WIKIDATA_MAX_ATTEMPTS}): {exc}. "
                f"Retrying in {WIKIDATA_RETRY_FLOOR_S:.0f}s…[/yellow]"
            )
            await asyncio.sleep(WIKIDATA_RETRY_FLOOR_S)
            continue

        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            wait = max(retry_after or WIKIDATA_RETRY_FLOOR_S, WIKIDATA_RETRY_FLOOR_S)
            wait = min(wait, WIKIDATA_RETRY_CAP_S)
            if attempt >= WIKIDATA_MAX_ATTEMPTS:
                console.print(
                    f"[red]Wikidata SPARQL 429-rate-limited after "
                    f"{attempt} attempt(s); giving up. "
                    f"Re-run when their service recovers.[/red]"
                )
                return None
            # Surface the upstream's outage marker if present — useful
            # for operator situational awareness.
            note = resp.headers.get("Retry-After") or "no Retry-After header"
            console.print(
                f"[yellow]Wikidata SPARQL 429 (attempt "
                f"{attempt}/{WIKIDATA_MAX_ATTEMPTS}, {note}). "
                f"Waiting {wait:.0f}s before retry…[/yellow]"
            )
            await asyncio.sleep(wait)
            continue

        try:
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # 5xx / parse error. Retry with floor wait — Wikidata 5xx
            # tends to be transient.
            if attempt >= WIKIDATA_MAX_ATTEMPTS:
                console.print(
                    f"[red]Wikidata SPARQL failed after "
                    f"{attempt} attempt(s): {exc}[/red]"
                )
                return None
            console.print(
                f"[yellow]Wikidata SPARQL {resp.status_code} "
                f"(attempt {attempt}/{WIKIDATA_MAX_ATTEMPTS}): {exc}. "
                f"Retrying in {WIKIDATA_RETRY_FLOOR_S:.0f}s…[/yellow]"
            )
            await asyncio.sleep(WIKIDATA_RETRY_FLOOR_S)
            continue

    return None


async def enrich_from_wikidata(
    db: Database,
    *,
    level: Optional[str] = None,
    include_inactive: bool = False,
) -> int:
    """Pull social handles for every Canadian legislator on Wikidata.

    Matches Wikidata person -> local politician by level + normalised name.
    Returns the number of (politician, platform, handle) rows inserted or
    updated via upsert_social().
    """
    # Decide which positions to query based on the `level` filter.
    if level == "federal":
        active = {k: v for k, v in WIKIDATA_POSITIONS.items() if v["level"] == "federal"}
    elif level == "provincial":
        active = {k: v for k, v in WIKIDATA_POSITIONS.items() if v["level"] == "provincial"}
    else:
        active = WIKIDATA_POSITIONS

    qid_to_level = {v["qid"]: v["level"] for v in active.values()}
    qids = list(qid_to_level.keys())
    if not qids:
        return 0

    sparql = _build_wikidata_sparql(qids)

    console.print(
        f"[cyan]Querying Wikidata SPARQL for {len(qids)} position items "
        f"(level filter={level or 'all'})…[/cyan]"
    )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=10.0),
        headers={
            "User-Agent": ENRICH_USER_AGENT,
            "Accept": "application/sparql-results+json",
        },
    ) as client:
        data = await _wikidata_sparql_with_retry(client, sparql)
        if data is None:
            return 0

    bindings = data.get("results", {}).get("bindings", [])
    console.print(f"[cyan]Wikidata returned {len(bindings)} person rows[/cyan]")
    if not bindings:
        return 0

    # Build a {qid: level} we need for matching, plus load the politician
    # index scoped to the relevant levels.
    idx = await _load_politician_index(
        db, level=level, include_inactive=include_inactive
    )
    scope = "all" if include_inactive else "active"
    console.print(
        f"[cyan]Indexed {len(idx)} {scope} politicians "
        f"(level filter={level or 'all'})[/cyan]"
    )

    # Collapse multiple (person, pos) SPARQL rows into one per (person, level)
    # so we don't double-upsert the same handle.
    persons: dict[str, dict[str, Any]] = {}
    skipped_unmatched = 0
    ambiguous_handles = Counter()

    for b in bindings:
        person_uri = b.get("person", {}).get("value", "")
        name = b.get("personLabel", {}).get("value", "")
        pos_label = b.get("posLabel", {}).get("value", "")
        # Map the position label back to our level — "Legislative Assembly"
        # etc. all correspond to provincial; only the House of Commons is
        # federal. Cheaper than resolving the Q-id again.
        row_level = "federal" if "House of Commons" in pos_label else "provincial"

        name_key = _normalize_name(name)
        if not name_key:
            continue
        match_id = idx.get((row_level, name_key))
        if match_id is None:
            skipped_unmatched += 1
            continue

        slot = persons.setdefault(person_uri, {
            "politician_id": match_id,
            "name": name,
            "handles": {},   # {(platform, handle): url}
        })

        for var, platform_hint, url_tmpl in WIKIDATA_SOCIAL_PROPS:
            val = b.get(var, {}).get("value")
            if not val:
                continue
            if platform_hint == "mastodon":
                url = _mastodon_url_from_address(val)
                if url is None:
                    continue
            else:
                url = url_tmpl.format(value=val)
            slot["handles"].setdefault((platform_hint, val), url)

    # Detect persons with a suspiciously large number of distinct handles
    # (a classic Wikidata disambiguation-bug symptom).
    for uri, slot in persons.items():
        n = len(slot["handles"])
        if n >= 10:
            log.warning(
                "Wikidata %s (%s) has %d distinct handles — "
                "possible disambiguation/merge issue", uri, slot["name"], n,
            )

    # Upsert — Wikidata SPARQL replies are sent serially (we already have
    # the payload); database writes themselves are cheap. Do them one-at-a-
    # time to keep the log ordered.
    inserted = 0
    counts: Counter[str] = Counter()
    per_person_counts = Counter()
    for uri, slot in persons.items():
        pid = slot["politician_id"]
        for (platform_hint, _handle), url in slot["handles"].items():
            try:
                canon = await upsert_social(
                    db, pid, platform_hint, url,
                    source="wikidata",
                    evidence_url=uri,  # the Wikidata entity URI
                )
            except Exception as exc:
                log.warning("wikidata upsert failed for %s %s: %s", pid, url, exc)
                continue
            if canon is None:
                counts["other"] += 1
                continue
            counts[canon.platform] += 1
            per_person_counts[pid] += 1
            inserted += 1

    console.print(
        f"[green]✓ Wikidata enrichment: matched {len(persons)} persons, "
        f"upserted {inserted} rows, unmatched={skipped_unmatched}[/green]"
    )
    if counts:
        for plat, n in counts.most_common():
            console.print(f"    {plat:<10} {n}")

    # Anomaly flagging: any politician receiving >= 10 socials in a single run
    # deserves a human look (likely a Wikidata merge error or a very
    # chronically-online MP).
    big = [(pid, n) for pid, n in per_person_counts.items() if n >= 10]
    if big:
        console.print(
            f"[yellow]⚠ {len(big)} politicians got 10+ handles this run — "
            "investigate for Wikidata disambiguation bugs:[/yellow]"
        )
        for pid, n in sorted(big, key=lambda x: -x[1])[:5]:
            row = await db.fetchrow("SELECT name FROM politicians WHERE id = $1", pid)
            console.print(f"    {row['name'] if row else pid}: {n} handles")

    return inserted


# ── openparliament.ca ─────────────────────────────────────────────────────

OPENPARL_BASE = "https://openparliament.ca"
OPENPARL_CONCURRENCY = 3


async def _list_openparl_politicians(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Walk the paginated /politicians/ listing.

    Each page yields objects with `name` + `url` (the slug path). We only
    need the URL → detail lookup, but `name` helps us disambiguate.
    """
    out: list[dict[str, Any]] = []
    next_url = "/politicians/?format=json&limit=500"
    while next_url:
        resp = await client.get(OPENPARL_BASE + next_url)
        resp.raise_for_status()
        data = resp.json()
        out.extend(data.get("objects", []))
        pagination = data.get("pagination", {}) or {}
        next_url = pagination.get("next_url")
    return out


async def enrich_from_openparl(
    db: Database,
    *,
    include_inactive: bool = False,
) -> int:
    """Fetch openparliament.ca detail pages for federal MPs missing socials."""

    # Build a name -> politician_id map for federal MPs.
    where = "WHERE level = 'federal'" if include_inactive else (
        "WHERE is_active = true AND level = 'federal'"
    )
    rows = await db.fetch(
        f"""
        SELECT id, name FROM politicians
         {where}
        """
    )
    by_name: dict[str, str] = {}
    for r in rows:
        key = _normalize_name(r["name"])
        if key and key not in by_name:
            by_name[key] = str(r["id"])

    if not by_name:
        console.print("[yellow]No active federal politicians to enrich[/yellow]")
        return 0

    sem = asyncio.Semaphore(OPENPARL_CONCURRENCY)
    inserted = 0
    counts: Counter[str] = Counter()
    matched = 0
    unmatched = 0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        headers={
            "User-Agent": ENRICH_USER_AGENT,
            "Accept": "application/json",
        },
        follow_redirects=True,
    ) as client:
        console.print("[cyan]Listing openparliament.ca MPs…[/cyan]")
        try:
            listing = await _list_openparl_politicians(client)
        except httpx.HTTPError as exc:
            console.print(f"[red]openparliament listing failed: {exc}[/red]")
            return 0
        console.print(f"[cyan]  {len(listing)} MPs listed[/cyan]")

        async def handle_one(entry: dict[str, Any]) -> int:
            nonlocal matched, unmatched
            name = entry.get("name", "")
            slug_url = entry.get("url", "")
            if not name or not slug_url:
                return 0

            key = _normalize_name(name)
            pid = by_name.get(key)
            if pid is None:
                unmatched += 1
                return 0

            async with sem:
                detail_url = OPENPARL_BASE + slug_url + "?format=json"
                try:
                    resp = await client.get(detail_url)
                    if resp.status_code == 404:
                        return 0
                    resp.raise_for_status()
                    detail = resp.json()
                except httpx.HTTPError as exc:
                    log.debug("openparl detail failed for %s: %s", slug_url, exc)
                    return 0

            matched += 1
            n_inserted_here = 0

            other = detail.get("other_info", {}) or {}
            # openparliament stores list-of-values. Typical keys:
            #   twitter:   ['SomeHandle']
            #   facebook:  (rare, usually URL)
            for raw_key, platform_hint, url_tmpl in (
                ("twitter",   "twitter",   "https://twitter.com/{value}"),
                ("facebook",  "facebook",  "https://www.facebook.com/{value}"),
                ("instagram", "instagram", "https://www.instagram.com/{value}"),
                ("youtube",   "youtube",   "https://www.youtube.com/{value}"),
            ):
                values = other.get(raw_key)
                if not values:
                    continue
                if isinstance(values, str):
                    values = [values]
                for v in values:
                    if not v:
                        continue
                    # If the stored value looks like a URL, use it directly.
                    if v.startswith("http://") or v.startswith("https://") or "/" in v:
                        url = v
                    else:
                        url = url_tmpl.format(value=v)
                    try:
                        canon = await upsert_social(
                            db, pid, platform_hint, url,
                            source="openparliament",
                            evidence_url=detail_url,
                        )
                    except Exception as exc:
                        log.warning("openparl upsert failed for %s %s: %s", pid, url, exc)
                        continue
                    if canon is not None:
                        counts[canon.platform] += 1
                        n_inserted_here += 1

            # `links` sometimes includes a Twitter / Facebook / Instagram URL.
            for link in detail.get("links") or []:
                url = (link or {}).get("url") or ""
                if not url:
                    continue
                # Skip the ourcommons.ca official page — not a social.
                if "ourcommons.ca" in url:
                    continue
                try:
                    canon = await upsert_social(
                        db, pid, None, url,
                        source="openparliament",
                        evidence_url=detail_url,
                    )
                except Exception as exc:
                    log.warning("openparl link upsert failed for %s %s: %s", pid, url, exc)
                    continue
                if canon is not None:
                    counts[canon.platform] += 1
                    n_inserted_here += 1

            return n_inserted_here

        results = await asyncio.gather(*(handle_one(e) for e in listing))
        inserted = sum(results)

    console.print(
        f"[green]✓ openparliament enrichment: matched {matched} MPs, "
        f"upserted {inserted} rows (unmatched names: {unmatched})[/green]"
    )
    if counts:
        for plat, n in counts.most_common():
            console.print(f"    {plat:<10} {n}")
    return inserted


# ── canada.masto.host lookup ──────────────────────────────────────────────

MASTO_HOST = "canada.masto.host"
MASTO_DIRECTORY_URL = f"https://{MASTO_HOST}/api/v1/directory"
MASTO_DIRECTORY_PAGE = 80
# Mastodon adoption among Canadian politicians is sparse — the realistic
# yield is in the single digits across 1800+ politicians. False-positive
# inserts cost much more than missed matches (they corrupt
# politician_socials and need manual cleanup), so the matching gate is
# deliberately strict:
#   - require *all* politician name tokens (last+first, no stopwords) to
#     appear as tokens in the display_name (not the acct, which routinely
#     contains nicknames / unrelated handles like "Janet_52square");
#   - require a Canadian-political keyword in the account bio so we don't
#     attach to a same-named theatre director or activist;
#   - persist new rows with flagged_low_confidence=true so an admin
#     reviews each match in /admin/socials before it surfaces publicly.
# These three together turned a 2095-row false-positive run into the
# ~handful of correct matches the platform actually has.
MASTO_POLITICAL_KEYWORDS = (
    "mp", "m.p.", "member of parliament", "mla", "m.l.a.", "mpp", "m.p.p.",
    "mna", "m.n.a.", "mha", "m.h.a.", "senator", "senate", "sénatrice",
    "sénateur", "mayor", "councillor", "councilor", "deputy mayor",
    "liberal", "conservative", "ndp", "bloc", "green party",
    "house of commons", "parliament", "parlement",
    "legislative assembly", "assemblée nationale",
    "constituency", "riding", "caucus", "minister", "ministre",
    "parl.gc.ca", "ourcommons.ca", "sencanada.ca",
    "député", "députée",
)


async def _walk_masto_directory(
    client: httpx.AsyncClient,
    *,
    local_only: bool,
) -> list[dict[str, Any]]:
    """Page through ``/api/v1/directory`` until empty.

    The previous implementation called ``/api/v1/accounts/lookup?acct=...``
    one handle at a time, which only resolves *local* canada.masto.host
    accounts. After the platform shrunk to ~58 local users that approach
    yields ~0 matches per run regardless of candidate quality. The
    directory endpoint instead enumerates every account the instance
    knows about (locally, or federated when ``local_only=False``), giving
    us a finite candidate set we can match by display_name.
    """
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        try:
            resp = await client.get(
                MASTO_DIRECTORY_URL,
                params={
                    "limit": MASTO_DIRECTORY_PAGE,
                    "offset": offset,
                    "local": "true" if local_only else "false",
                    "order": "active",
                },
            )
        except httpx.HTTPError as exc:
            log.warning("masto directory page offset=%d failed: %s", offset, exc)
            break
        if resp.status_code != 200:
            log.warning("masto directory page offset=%d HTTP %d", offset, resp.status_code)
            break
        try:
            page = resp.json()
        except ValueError:
            break
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        if len(page) < MASTO_DIRECTORY_PAGE:
            break
        offset += MASTO_DIRECTORY_PAGE
        # safety stop: federated directory observed at ~4k accounts
        if offset > 8000:
            log.info("masto directory walk stopped at offset=%d (safety cap)", offset)
            break
        await asyncio.sleep(0.1)  # be polite
    return out


async def enrich_mastodon_candidates(
    db: Database,
    *,
    include_inactive: bool = False,
) -> int:
    """Match politicians to canada.masto.host accounts via directory walk.

    Walks the instance's directory once (one HTTP request per 80 accounts)
    and matches each account's ``display_name`` to politician names. Beats
    handle-guessing on cost (O(N+M) requests vs O(N×5)) and on coverage
    (federated accounts visible from canada.masto.host are matched too,
    not just local users).
    """
    where = "WHERE TRUE" if include_inactive else "WHERE p.is_active = true"
    rows = await db.fetch(
        f"""
        SELECT p.id, p.name
          FROM politicians p
          LEFT JOIN politician_socials ps
            ON ps.politician_id = p.id AND ps.platform = 'mastodon'
         {where} AND ps.id IS NULL
        """
    )
    if not rows:
        console.print("[yellow]No politicians missing a Mastodon handle[/yellow]")
        return 0

    # Build a list of (politician_id, name, normalized-name-variants) for
    # substring matching. We keep variants in both orders ("first last"
    # AND "last first") because Mastodon display_names commonly carry
    # the "Lastname, Firstname" form. Politicians with single-token names
    # are skipped — they would match every account that shares that one
    # token.
    pol_index: list[tuple[str, str, list[str]]] = []
    for r in rows:
        name = r["name"] or ""
        norm = _normalize_name(name)
        toks = [t for t in norm.split() if t]
        if len(toks) < 2:
            continue
        # "first last" + "last first" — handles both display orders.
        variants = [
            " ".join(toks),
            " ".join(reversed(toks)),
        ]
        pol_index.append((str(r["id"]), name, variants))

    console.print(
        f"[cyan]Walking canada.masto.host directory to match against "
        f"{len(pol_index)} politicians…[/cyan]"
    )

    inserted = 0
    accounts_walked = 0
    matches_attempted = 0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=8.0),
        headers={
            "User-Agent": ENRICH_USER_AGENT,
            "Accept": "application/json",
        },
        follow_redirects=True,
    ) as client:
        # Local first (high-signal): users who explicitly chose
        # canada.masto.host as their home server.
        local = await _walk_masto_directory(client, local_only=True)
        # Federated next: accounts the instance has interacted with —
        # noisier, but a Canadian politician on (e.g.) socialbc.ca will
        # show up here once any canada.masto.host user follows them.
        federated = await _walk_masto_directory(client, local_only=False)

        # De-dup by `acct` (acct strings include the home instance for
        # federated rows: ``user@instance``).
        seen_acct: set[str] = set()
        for acct_dict in (*local, *federated):
            key = (acct_dict.get("acct") or "").lower()
            if not key or key in seen_acct:
                continue
            seen_acct.add(key)
            accounts_walked += 1

            disp_raw = acct_dict.get("display_name") or ""
            # Normalize display the same way we normalize politician names —
            # strip diacritics, lowercase, collapse non-alphanumerics to
            # single spaces — so substring-search works across accent
            # variants and punctuation choices.
            disp_norm = " ".join(_normalize_name(disp_raw).split())
            if not disp_norm:
                continue

            # Bio gate: refuse any match whose bio doesn't carry at least
            # one Canadian-politics keyword. Stripping HTML tags first.
            bio = re.sub(r"<[^>]+>", " ", acct_dict.get("note") or "").lower()
            if not any(kw in bio for kw in MASTO_POLITICAL_KEYWORDS):
                continue

            # Strict full-name substring match: politician's normalized
            # name must appear as a contiguous substring of the
            # normalized display_name (in either word order). This is
            # much stricter than token-overlap — "michael ma" no longer
            # matches every Mastodon "Michael Mxxx" account.
            best: Optional[tuple[str, str]] = None
            for pid, pname, variants in pol_index:
                if any(
                    f" {v} " in f" {disp_norm} "
                    for v in variants
                ):
                    best = (pid, pname)
                    break
            if best is None:
                continue

            matches_attempted += 1
            pid, pname = best
            username = acct_dict.get("username") or ""
            url = acct_dict.get("url") or (
                f"https://{MASTO_HOST}/@{username}" if username else None
            )
            if not url:
                continue
            try:
                canon = await upsert_social(
                    db, pid, "mastodon", url,
                    source="masto_host",
                    # Even with the strict gate, route to the admin
                    # review queue — Mastodon display_name can be
                    # impersonated and the platform has no verification.
                    confidence=0.85,
                    evidence_url=url,
                )
            except Exception as exc:
                log.warning("mastodon upsert failed for %s: %s", pid, exc)
                continue
            if canon is not None:
                inserted += 1
                log.info(
                    "matched mastodon %s -> %s (display=%r)",
                    acct_dict.get("acct"), pname, disp_raw,
                )

    console.print(
        f"[green]✓ Mastodon enrichment: walked {accounts_walked} accounts, "
        f"attempted {matches_attempted} matches, upserted {inserted}[/green]"
    )
    return inserted


# ── Orchestrator ──────────────────────────────────────────────────────────

async def enrich_all_socials(
    db: Database,
    *,
    include_inactive: bool = False,
) -> None:
    """Run wikidata → openparl → mastodon in that order."""
    total_wiki = await enrich_from_wikidata(db, include_inactive=include_inactive)
    total_parl = await enrich_from_openparl(db, include_inactive=include_inactive)
    total_masto = await enrich_mastodon_candidates(db, include_inactive=include_inactive)
    scope = "inactive+active" if include_inactive else "active"
    console.print(
        f"[bold green]Enrichment complete ({scope}) — "
        f"wikidata={total_wiki} openparl={total_parl} mastodon={total_masto}"
        f"[/bold green]"
    )
