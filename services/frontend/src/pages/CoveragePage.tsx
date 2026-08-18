import { useState } from "react";
import { useCoverage, type CoverageJurisdiction } from "../hooks/useCoverage";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import "../styles/coverage.css";

const STATUS_LABEL: Record<CoverageJurisdiction["bills_status"], string> = {
  live: "Live",
  partial: "Partial",
  blocked: "Blocked",
  none: "Pending",
};

const STATUS_SYMBOL: Record<CoverageJurisdiction["bills_status"], string> = {
  live: "✓",
  partial: "◐",
  blocked: "⛔",
  none: "…",
};

// jurisdiction_sources.blockers stores short operator slugs (greppable,
// stable). Map them to plain-language chip labels for the public page;
// unknown slugs fall through as-is.
const BLOCKER_LABEL: Record<string, string> = {
  "pdf-only": "PDF only",
  "waf-budget": "Limited by site protections",
  "consensus-govt": "Consensus government",
  "radware-shieldsquare": "Blocked by CAPTCHA",
  "cloudflare-bot-mgmt": "Blocked by bot protection",
};

function blockerLabel(slug: string): string {
  return BLOCKER_LABEL[slug] ?? slug;
}

/** "edmonton" -> "Edmonton". Municipal rows key on `AB-edmonton`, which
 *  is a fine primary key and a poor label, so the code column shows the
 *  city instead. Hyphens become spaces for future multi-word slugs
 *  ("grande-prairie" -> "Grande Prairie"). */
function cityLabel(slug: string): string {
  return slug
    .split("-")
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/** The label shown in the code column: province/federal code for a
 *  legislature, city name for a municipality. */
function rowCode(j: CoverageJurisdiction): string {
  return j.level === "municipal" && j.municipality_slug
    ? cityLabel(j.municipality_slug)
    : j.jurisdiction;
}

interface CoverageGroup {
  parent: CoverageJurisdiction;
  children: CoverageJurisdiction[];
}

/** Fold the flat API array into parent + children so a province row can
 *  own a disclosure control for its cities.
 *
 *  The API orders each city directly after its province, so a single
 *  forward pass is enough. A city whose parent isn't present (only
 *  reachable via `?status=`, which nothing calls today) is promoted to a
 *  top-level row rather than dropped — losing a jurisdiction silently
 *  would be a worse failure than showing it un-nested. */
function groupRows(rows: CoverageJurisdiction[]): CoverageGroup[] {
  const groups: CoverageGroup[] = [];
  const byCode = new Map<string, CoverageGroup>();

  for (const row of rows) {
    if (row.parent_jurisdiction) {
      const parent = byCode.get(row.parent_jurisdiction);
      if (parent) {
        parent.children.push(row);
        continue;
      }
    }
    const group: CoverageGroup = { parent: row, children: [] };
    groups.push(group);
    byCode.set(row.jurisdiction, group);
  }
  return groups;
}

/** Disclosure control that replaces the plain code label on any row that
 *  has cities under it. Rows without children render plain text — a
 *  disabled toggle would be a focus stop that does nothing. */
function GroupToggle({
  code, count, open, controls, onToggle,
}: {
  code: string;
  count: number;
  open: boolean;
  controls: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className="coverage__toggle"
      aria-expanded={open}
      aria-controls={controls}
      onClick={onToggle}
    >
      <span className="coverage__toggle-chevron" aria-hidden="true">▸</span>
      <span className="coverage__code">{code}</span>
      <span className="coverage__toggle-count">
        {count} council{count === 1 ? "" : "s"}
      </span>
    </button>
  );
}

function StatusPill({ status }: { status: CoverageJurisdiction["bills_status"] }) {
  return (
    <span className={`coverage__pill coverage__pill--${status}`}>
      <span className="coverage__pill-symbol" aria-hidden="true">{STATUS_SYMBOL[status]}</span>
      {STATUS_LABEL[status]}
    </span>
  );
}

/** Card innards, shared by province and city cards. `head` is the only
 *  thing that differs between them — a disclosure toggle on a province
 *  with cities, a plain label otherwise — so it is injected rather than
 *  branched on inside, which kept two near-identical card blocks in
 *  sync by hand. */
function CoverageCardBody({ j, head }: { j: CoverageJurisdiction; head: React.ReactNode }) {
  return (
    <>
      <div className="coverage__card-head">
        <div className="coverage__card-title">
          {head}
          <span className="coverage__legname">{j.legislature_name}</span>
        </div>
        <span className="coverage__card-seats">
          {j.seats != null ? `${j.seats} seats` : "—"}
        </span>
      </div>
      <dl className="coverage__card-stats">
        <div>
          <dt>Bills</dt>
          <dd><StatusPill status={j.bills_status} /></dd>
        </div>
        <div>
          <dt>Hansard</dt>
          <dd><StatusPill status={j.hansard_status} /></dd>
        </div>
        <div>
          <dt>Votes</dt>
          <dd><StatusPill status={j.votes_status} /></dd>
        </div>
        <div>
          <dt>Committees</dt>
          <dd><StatusPill status={j.committees_status} /></dd>
        </div>
      </dl>
      {(j.blockers || j.notes) && (
        <div className="coverage__card-notes">
          {j.blockers && <span className="coverage__blocker">{blockerLabel(j.blockers)}</span>}
          {j.notes && <p>{j.notes}</p>}
        </div>
      )}
    </>
  );
}

function CountCell({ value, label }: { value: number; label: string }) {
  return (
    <div className="coverage__count">
      <span className="coverage__count-value">{value.toLocaleString()}</span>
      <span className="coverage__count-label">{label}</span>
    </div>
  );
}

export default function CoveragePage() {
  useDocumentTitle("Coverage");
  const { data, loading, error } = useCoverage();

  // Tracks the CLOSED set, not the open one, so groups default to
  // expanded: the cities are the point of the nesting, and hiding them
  // behind a control nobody knows to click would bury the coverage we
  // are trying to advertise. Flip to `new Set(["AB"])`-style seeding if
  // that ever inverts.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  function toggleGroup(code: string) {
    setCollapsed(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  if (error) {
    return (
      <section className="coverage">
        <div className="coverage__error">Failed to load coverage: {error.message}</div>
      </section>
    );
  }

  if (loading || !data) {
    return (
      <section className="coverage">
        <header className="coverage__header">
          <h2 className="coverage__title">Coverage</h2>
          <p className="coverage__subtitle">Loading current state of every Canadian legislature we track…</p>
        </header>
      </section>
    );
  }

  const { jurisdictions, summary } = data;
  const groups = groupRows(jurisdictions);

  return (
    <section className="coverage">
      <header className="coverage__header">
        <h2 className="coverage__title">Coverage</h2>
        <p className="coverage__subtitle">
          The current status of every Canadian legislature we track, across four kinds
          of data: bills,{" "}
          <abbr title="The official transcript of what was said in the legislature">Hansard</abbr>,{" "}
          votes, and committees. Where something is missing or blocked, the notes
          explain why. Indented rows are city councils whose proceedings we ingest,
          listed under their province.
        </p>
        <div className="coverage__summary" role="group" aria-label="Coverage summary">
          <CountCell value={summary.live} label="live" />
          <CountCell value={summary.partial} label="partial" />
          <CountCell value={summary.blocked} label="blocked" />
          <CountCell value={summary.none} label="pending" />
          <CountCell value={summary.total} label="total" />
        </div>
      </header>

      {/* Desktop: dense table. Mobile: card-stack via .coverage__cards.
          Both render the same data; CSS swaps which is visible at <= 720px. */}
      <div className="coverage__table-wrap">
        <table className="coverage__table">
          <thead>
            <tr>
              <th scope="col">Jurisdiction</th>
              <th scope="col">Seats</th>
              <th scope="col">
                <abbr title="Draft laws introduced in this legislature">Bills</abbr>
              </th>
              <th scope="col">
                <abbr title="The official transcript of what was said in the legislature">Hansard</abbr>
              </th>
              <th scope="col">
                <abbr title="How members voted on bills and motions">Votes</abbr>
              </th>
              <th scope="col">
                <abbr title="Working groups of members that review bills and hold hearings">Committees</abbr>
              </th>
              <th scope="col">Notes</th>
            </tr>
          </thead>
          <tbody>
            {groups.map(({ parent, children }) => {
              const open = !collapsed.has(parent.jurisdiction);
              // Child rows stay mounted and are hidden with [hidden] so
              // the ids in aria-controls always resolve to real elements.
              const controls = children
                .map(c => `coverage-row-${c.jurisdiction}`)
                .join(" ");

              return [
                <tr key={parent.jurisdiction}>
                  <th scope="row" className="coverage__jurisdiction">
                    <div className="coverage__jurisdiction-inner">
                      {children.length > 0 ? (
                        <GroupToggle
                          code={rowCode(parent)}
                          count={children.length}
                          open={open}
                          controls={controls}
                          onToggle={() => toggleGroup(parent.jurisdiction)}
                        />
                      ) : (
                        <span className="coverage__code">{rowCode(parent)}</span>
                      )}
                      <span className="coverage__legname">{parent.legislature_name}</span>
                    </div>
                  </th>
                  <td className="coverage__seats">{parent.seats ?? "—"}</td>
                  <td><StatusPill status={parent.bills_status} /></td>
                  <td><StatusPill status={parent.hansard_status} /></td>
                  <td><StatusPill status={parent.votes_status} /></td>
                  <td><StatusPill status={parent.committees_status} /></td>
                  <td className="coverage__notes">
                    {parent.blockers && (
                      <div className="coverage__blocker">{blockerLabel(parent.blockers)}</div>
                    )}
                    {parent.notes}
                  </td>
                </tr>,
                ...children.map(c => (
                  <tr
                    key={c.jurisdiction}
                    id={`coverage-row-${c.jurisdiction}`}
                    className="coverage__row--child"
                    hidden={!open}
                  >
                    <th scope="row" className="coverage__jurisdiction">
                      <div className="coverage__jurisdiction-inner">
                        <span className="coverage__code">
                          <span className="coverage__child-marker" aria-hidden="true">↳</span>
                          {rowCode(c)}
                        </span>
                        <span className="coverage__legname">{c.legislature_name}</span>
                      </div>
                    </th>
                    <td className="coverage__seats">{c.seats ?? "—"}</td>
                    <td><StatusPill status={c.bills_status} /></td>
                    <td><StatusPill status={c.hansard_status} /></td>
                    <td><StatusPill status={c.votes_status} /></td>
                    <td><StatusPill status={c.committees_status} /></td>
                    <td className="coverage__notes">
                      {c.blockers && (
                        <div className="coverage__blocker">{blockerLabel(c.blockers)}</div>
                      )}
                      {c.notes}
                    </td>
                  </tr>
                )),
              ];
            })}
          </tbody>
        </table>
      </div>

      <ul className="coverage__cards" aria-label="Coverage by jurisdiction (mobile view)">
        {groups.map(({ parent, children }) => {
          const open = !collapsed.has(parent.jurisdiction);
          const controls = children
            .map(c => `coverage-card-${c.jurisdiction}`)
            .join(" ");

          return [
            <li key={parent.jurisdiction} className="coverage__card">
              <CoverageCardBody
                j={parent}
                head={
                  children.length > 0 ? (
                    <GroupToggle
                      code={rowCode(parent)}
                      count={children.length}
                      open={open}
                      controls={controls}
                      onToggle={() => toggleGroup(parent.jurisdiction)}
                    />
                  ) : (
                    <span className="coverage__code">{rowCode(parent)}</span>
                  )
                }
              />
            </li>,
            ...children.map(c => (
              <li
                key={c.jurisdiction}
                id={`coverage-card-${c.jurisdiction}`}
                className="coverage__card coverage__card--child"
                hidden={!open}
              >
                <CoverageCardBody
                  j={c}
                  head={
                    <span className="coverage__code">
                      <span className="coverage__child-marker" aria-hidden="true">↳</span>
                      {rowCode(c)}
                    </span>
                  }
                />
              </li>
            )),
          ];
        })}
      </ul>

      <footer className="coverage__footer">
        {/* Matches the `refresh-coverage-stats` scanner_schedules row
            (cron `50 23 * * *`). This read "hourly" until 2026-08-17,
            which never matched the schedule. */}
        <p>Counts refresh daily.</p>
        <p>
          See <a href="https://docs.canadianpoliticaldata.org/blog/" target="_blank" rel="noopener noreferrer">the blog</a> for updates as new jurisdictions come online.
        </p>
      </footer>
    </section>
  );
}
