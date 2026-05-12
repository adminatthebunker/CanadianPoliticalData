"""Canonicalisation + upsert helper for the polymorphic `websites` table.

Thin parallel of `socials.upsert_social`. Used by Tier-1 legislature
scrapers (which pass source='legislature_scrape', confidence=1.0) and by
the Tier-3 `websites_agent.py` (source='agent_sonnet', agent-reported
confidence). Same `flagged_low_confidence` discipline as
`politician_socials`: rows below 0.85 from `agent_sonnet` route to the
operator review queue.

Provenance columns added by migration 0047_websites_provenance.sql.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

from .db import Database

log = logging.getLogger(__name__)


ALLOWED_LABELS = frozenset({
    "personal",        # politician's own / campaign / constituency-office site
    "campaign",        # explicit campaign domain (often seasonal)
    "party_lander",    # party's MLA/MP listing page that names this politician
    "shared_official", # legislature-owned profile page (rare; usually we'd
                       # rather populate politicians.official_url instead)
})

ALLOWED_SOURCES = frozenset({
    "legacy", "wikidata", "openparliament",
    "legislature_scrape", "agent_sonnet", "admin_manual",
})

_AGENT_FLAG_THRESHOLD = 0.85


@dataclass
class CanonicalWebsite:
    url: str
    hostname: str


def canonicalize(url: str) -> Optional[CanonicalWebsite]:
    """Normalise a website URL before INSERT.

    Lowercases the host, strips obvious tracking params, drops a bare
    trailing slash on path-empty URLs, and rejects non-http(s) schemes
    (mailto:, tel:, javascript:). Returns None on parse failure.
    """
    if not url or not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw:
        return None

    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")

    try:
        p = urlparse(raw)
    except ValueError:
        return None

    if p.scheme not in ("http", "https"):
        return None
    if not p.hostname:
        return None

    host = p.hostname.lower()
    if host.startswith("www."):
        host = host[4:]

    path = p.path or ""
    if path == "/":
        path = ""

    query = p.query or ""
    if query:
        keep = [
            kv for kv in query.split("&")
            if not kv.lower().startswith(("utm_", "fbclid=", "gclid=", "mc_cid=", "mc_eid="))
        ]
        query = "&".join(keep)

    canonical = urlunparse((
        p.scheme, host + (f":{p.port}" if p.port else ""),
        path, "", query, "",
    ))
    return CanonicalWebsite(url=canonical, hostname=host)


def _should_flag(source: str, confidence: float) -> bool:
    if source == "agent_sonnet":
        return confidence < _AGENT_FLAG_THRESHOLD
    return False


async def upsert_website(
    db: Database,
    politician_id: str,
    url: str,
    *,
    label: str,
    source: str,
    confidence: float = 1.0,
    evidence_url: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[str]:
    """Canonicalise `url` and upsert a websites row for this politician.

    Returns the canonical URL on success, None on rejection (unparseable
    URL, disallowed label, disallowed source).

    Idempotent on (owner_type, owner_id, url) UNIQUE. On conflict, we
    only overwrite provenance if the incoming confidence beats the
    stored one (mirrors socials.upsert_social).
    """
    if label not in ALLOWED_LABELS:
        log.warning("upsert_website: rejected label=%r", label)
        return None
    if source not in ALLOWED_SOURCES:
        log.warning("upsert_website: rejected source=%r", source)
        return None

    canon = canonicalize(url)
    if canon is None:
        return None

    conf = max(0.0, min(1.0, float(confidence)))
    flagged = _should_flag(source, conf)

    await db.execute(
        """
        INSERT INTO websites
            (owner_type, owner_id, url, label, notes,
             source, confidence, evidence_url,
             flagged_low_confidence, discovered_at)
        VALUES ('politician', $1, $2, $3, $4, $5, $6, $7, $8, now())
        ON CONFLICT (owner_type, owner_id, url) DO UPDATE SET
            label = COALESCE(EXCLUDED.label, websites.label),
            source = CASE
                WHEN EXCLUDED.confidence > COALESCE(websites.confidence, 0)
                THEN EXCLUDED.source
                ELSE websites.source
            END,
            confidence = GREATEST(COALESCE(websites.confidence, 0), EXCLUDED.confidence),
            evidence_url = CASE
                WHEN EXCLUDED.confidence > COALESCE(websites.confidence, 0)
                THEN EXCLUDED.evidence_url
                ELSE websites.evidence_url
            END,
            flagged_low_confidence = CASE
                WHEN EXCLUDED.confidence > COALESCE(websites.confidence, 0)
                THEN EXCLUDED.flagged_low_confidence
                ELSE websites.flagged_low_confidence
            END,
            updated_at = now()
        """,
        politician_id, canon.url, label, notes,
        source, conf, evidence_url, flagged,
    )

    return canon.url
