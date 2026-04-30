import type { SemanticFilter, SpeechType } from "../../hooks/useSemanticMap";

const PROVINCES: Array<{ code: string; label: string }> = [
  { code: "AB", label: "Alberta" },
  { code: "BC", label: "British Columbia" },
  { code: "MB", label: "Manitoba" },
  { code: "NB", label: "New Brunswick" },
  { code: "NL", label: "Newfoundland & Labrador" },
  { code: "NS", label: "Nova Scotia" },
  { code: "NT", label: "Northwest Territories" },
  { code: "NU", label: "Nunavut" },
  { code: "ON", label: "Ontario" },
  { code: "PE", label: "Prince Edward Island" },
  { code: "QC", label: "Quebec" },
  { code: "SK", label: "Saskatchewan" },
  { code: "YT", label: "Yukon" },
];

const SPEECH_TYPES: Array<{ value: SpeechType; label: string }> = [
  { value: "floor", label: "Floor debate" },
  { value: "question_period", label: "Question Period" },
  { value: "statement", label: "Member statements" },
  { value: "committee", label: "Committee" },
];

interface Props {
  filter: SemanticFilter;
  onChange: (patch: Partial<SemanticFilter>) => void;
  onReset: () => void;
}

export default function SemanticMapFilters({ filter, onChange, onReset }: Props) {
  const hasAny = Boolean(
    filter.level || filter.province_territory || filter.party ||
    filter.from || filter.to || filter.lang === "en" || filter.lang === "fr" ||
    filter.exclude_presiding ||
    (filter.speech_types && filter.speech_types.length > 0),
  );
  return (
    <div className="semantic-map__filters">
      <div className="semantic-map__filter-row">
        <label className="semantic-map__filter-field">
          <span>Level</span>
          <select
            value={filter.level ?? ""}
            onChange={(e) => onChange({ level: (e.target.value || undefined) as SemanticFilter["level"] })}
          >
            <option value="">All</option>
            <option value="federal">Federal</option>
            <option value="provincial">Provincial</option>
          </select>
        </label>
        <label className="semantic-map__filter-field">
          <span>Province</span>
          <select
            value={filter.province_territory ?? ""}
            onChange={(e) => onChange({ province_territory: e.target.value || undefined })}
          >
            <option value="">All</option>
            {PROVINCES.map((p) => (
              <option key={p.code} value={p.code}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="semantic-map__filter-field">
          <span>Party</span>
          <input
            type="text"
            placeholder="e.g. Liberal"
            value={filter.party ?? ""}
            onChange={(e) => onChange({ party: e.target.value || undefined })}
          />
        </label>
        <label className="semantic-map__filter-field">
          <span>Language</span>
          <select
            value={filter.lang ?? "any"}
            onChange={(e) => onChange({ lang: e.target.value as SemanticFilter["lang"] })}
          >
            <option value="any">Any</option>
            <option value="en">English</option>
            <option value="fr">French</option>
          </select>
        </label>
      </div>
      <div className="semantic-map__filter-row">
        <label className="semantic-map__filter-field">
          <span>From</span>
          <input
            type="date"
            value={filter.from ?? ""}
            onChange={(e) => onChange({ from: e.target.value || undefined })}
          />
        </label>
        <label className="semantic-map__filter-field">
          <span>To</span>
          <input
            type="date"
            value={filter.to ?? ""}
            onChange={(e) => onChange({ to: e.target.value || undefined })}
          />
        </label>
        <label className="semantic-map__filter-field semantic-map__filter-field--checkbox">
          <input
            type="checkbox"
            checked={filter.exclude_presiding ?? false}
            onChange={(e) => onChange({ exclude_presiding: e.target.checked || undefined })}
          />
          <span>Hide chair speech</span>
        </label>
        {hasAny && (
          <button
            type="button"
            className="semantic-map__filter-reset"
            onClick={onReset}
          >
            Reset filters
          </button>
        )}
      </div>
      <div className="semantic-map__filter-row semantic-map__filter-row--types">
        {SPEECH_TYPES.map((t) => {
          const active = filter.speech_types?.includes(t.value) ?? false;
          return (
            <label
              key={t.value}
              className={`semantic-map__type-chip${active ? " is-active" : ""}`}
            >
              <input
                type="checkbox"
                checked={active}
                onChange={(e) => {
                  const cur = filter.speech_types ?? [];
                  const next = e.target.checked
                    ? [...cur, t.value]
                    : cur.filter((x) => x !== t.value);
                  onChange({ speech_types: next.length > 0 ? next : undefined });
                }}
              />
              {t.label}
            </label>
          );
        })}
      </div>
    </div>
  );
}
