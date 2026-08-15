import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { useCoverage, type CoverageJurisdiction } from "../hooks/useCoverage";
import {
  POSTAL_RE,
  canonicalizePostal,
  formatPostal,
  loadStoredPostcode,
  storePostcode,
} from "../lib/postal";

const nf = new Intl.NumberFormat("en-CA");

interface CorpusStats {
  speeches: number;
  bills: number;
  politicians: number;
  liveJurisdictions: number;
  lastUpdate: string | null;
}

function aggregateCoverage(rows: CoverageJurisdiction[]): CorpusStats {
  let speeches = 0;
  let bills = 0;
  let politicians = 0;
  let liveJurisdictions = 0;
  let maxVerified: number | null = null;
  for (const r of rows) {
    speeches += r.speeches_count || 0;
    bills += r.bills_count || 0;
    politicians += r.politicians_count || 0;
    if (r.hansard_status === "live" || r.bills_status === "live") {
      liveJurisdictions++;
    }
    if (r.last_verified_at) {
      const t = new Date(r.last_verified_at).getTime();
      if (!Number.isNaN(t) && (maxVerified === null || t > maxVerified)) {
        maxVerified = t;
      }
    }
  }
  return {
    speeches,
    bills,
    politicians,
    liveJurisdictions,
    lastUpdate: maxVerified ? new Date(maxVerified).toISOString() : null,
  };
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "recently";
  const sec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} minute${min === 1 ? "" : "s"} ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} hour${hr === 1 ? "" : "s"} ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day} day${day === 1 ? "" : "s"} ago`;
  const wk = Math.floor(day / 7);
  if (wk < 5) return `${wk} week${wk === 1 ? "" : "s"} ago`;
  const mo = Math.floor(day / 30);
  return `${mo} month${mo === 1 ? "" : "s"} ago`;
}

export default function Lander() {
  useDocumentTitle(null);
  const navigate = useNavigate();
  const [hansard, setHansard] = useState("");
  // Optional postcode on the unified search card, prefilled with the
  // last postcode used anywhere on the site (client-side only).
  const [searchPostal, setSearchPostal] = useState(() => {
    const stored = loadStoredPostcode();
    return stored ? formatPostal(stored) : "";
  });
  const [searchPostalError, setSearchPostalError] = useState<string | null>(null);

  const coverage = useCoverage();
  const stats = coverage.data ? aggregateCoverage(coverage.data.jurisdictions) : null;

  // One search bar, three behaviours:
  //   query only            → semantic speech search
  //   postal code only      → rep lookup on the map (the old "Find your
  //                           reps" flow — who represents this postcode)
  //   query + postal code   → speech search filtered to that postcode's
  //                           representatives
  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = hansard.trim();
    const trimmedPostal = searchPostal.trim();
    if (!trimmed && !trimmedPostal) return;
    if (trimmedPostal && !POSTAL_RE.test(trimmedPostal)) {
      setSearchPostalError("Enter a valid Canadian postal code (e.g. K1A 0A6)");
      return;
    }
    const canonical = trimmedPostal ? canonicalizePostal(trimmedPostal) : null;
    if (canonical) storePostcode(canonical);
    if (canonical && !trimmed) {
      navigate(`/map?postal=${canonical}`);
      return;
    }
    const p = new URLSearchParams();
    p.set("q", trimmed);
    if (canonical) p.set("postcode", canonical);
    navigate(`/search?${p.toString()}`);
  }

  const trimmedQ = hansard.trim();
  const postalValid = POSTAL_RE.test(searchPostal.trim());
  const repsOnlyMode = postalValid && !trimmedQ;

  // Explicit, state-aware hint so the two-input bar explains itself.
  const searchHint = repsOnlyMode
    ? `Finds the representatives for ${formatPostal(searchPostal.trim())}: your MP, MLA, and municipal councillors.`
    : postalValid && trimmedQ
      ? `Only shows speeches by ${formatPostal(searchPostal.trim())}'s representatives.`
      : trimmedQ
        ? (stats
            ? `Semantic search across ${nf.format(stats.speeches)} speeches.`
            : "Search what every politician has said on the record.")
        : "Enter a search term, a postal code, or both. A postal code on its own finds your representatives. Add a search term to see what they have said about it.";

  return (
    <div className="lander">
      <div className="lander__inner">
        <span className="lander__logo" aria-hidden="true">🍁</span>
        <h1 className="lander__title">Canadian Political Data</h1>

        {stats && stats.speeches > 0 && (
          <div className="lander__stats" aria-label="Corpus statistics">
            <div className="lander__stats-row">
              <span><span className="lander__stats-num">{nf.format(stats.speeches)}</span> speeches</span>
              <span className="lander__stats-sep" aria-hidden="true">·</span>
              <span><span className="lander__stats-num">{nf.format(stats.bills)}</span> bills</span>
              <span className="lander__stats-sep" aria-hidden="true">·</span>
              <span><span className="lander__stats-num">{nf.format(stats.politicians)}</span> politicians</span>
              <span className="lander__stats-sep" aria-hidden="true">·</span>
              <span><span className="lander__stats-num">{stats.liveJurisdictions}</span> jurisdictions live</span>
            </div>
            {stats.lastUpdate && (
              <div className="lander__stats-fresh">Updated {relativeTime(stats.lastUpdate)}</div>
            )}
          </div>
        )}

        <p className="lander__tagline">
          Search every speech, every bill, and every vote across Canada's federal and provincial legislatures.
        </p>
        <p className="lander__stance">
          Open data, public record &mdash; built to make democracy legible.
        </p>

        <div className="lander__forms lander__forms--single">
          <form className="lander__form-card lander__form-card--hero" onSubmit={submitSearch}>
            <h2 className="lander__form-heading">
              <span aria-hidden="true">🔎</span> Search the record
            </h2>
            <div className="lander__find-row">
              <input
                id="lander-hansard"
                type="search"
                placeholder='Try "carbon pricing" or "housing crisis"'
                value={hansard}
                onChange={e => setHansard(e.target.value)}
                aria-label="Search Canadian parliamentary speeches"
              />
              <input
                id="lander-hansard-postal"
                type="text"
                className="lander__postal-inline"
                placeholder="Postal code (K1A 0A6)"
                title="A postal code on its own finds your reps. Add a search term to see their speeches."
                value={searchPostal}
                onChange={e => { setSearchPostal(e.target.value); setSearchPostalError(null); }}
                aria-label="Postal code. On its own it finds your representatives. With a search term it limits results to their speeches."
                aria-invalid={searchPostalError ? true : undefined}
                aria-describedby={searchPostalError ? "lander-hansard-postal-error" : undefined}
                maxLength={7}
              />
              <button type="submit" className="lander__btn lander__btn--primary">
                {repsOnlyMode ? "Find my reps →" : "Search →"}
              </button>
            </div>
            {searchPostalError && (
              <div id="lander-hansard-postal-error" className="lander__find-error" role="alert">
                {searchPostalError}
              </div>
            )}
            <p className="lander__find-hint" aria-live="polite">{searchHint}</p>
            <p className="lander__find-hint">
              Search understands meaning, so you can type plain language, full
              sentences, or questions. Every result is a real speech, quoted
              word for word from the official record. Nothing is written by AI.{" "}
              <a
                className="lander__find-hint-link"
                href="https://docs.canadianpoliticaldata.org/searching/how-it-works/"
                target="_blank"
                rel="noopener noreferrer"
              >
                How search works ↗
              </a>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
