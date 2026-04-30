import { useEffect, useMemo, useRef, useState } from "react";
import {
  SPEECH_TYPE_VALUES,
  type SpeechSearchFilter,
  type SpeechType,
} from "../hooks/useSpeechSearch";
import { useLegislativeSessions } from "../hooks/useLegislativeSessions";

// Canonical filter taxonomy. Each entry is one row in the +Filter menu
// and one chip when active. `date` collapses the from/to pair; the rest
// map 1:1 to a field on SpeechSearchFilter.
type FilterType =
  | "lang"
  | "level"
  | "province"
  | "party"
  | "date"
  | "hide_chair"
  | "min_similarity"
  | "session"
  | "speech_type";

const FILTER_LABELS: Record<FilterType, string> = {
  lang: "Language",
  level: "Level",
  province: "Province",
  party: "Party",
  date: "Date range",
  hide_chair: "Hide chair speech",
  min_similarity: "Min similarity",
  session: "Parliament & session",
  speech_type: "Speech type",
};

const ALL_FILTERS: FilterType[] = [
  "level",
  "province",
  "party",
  "date",
  "min_similarity",
  "speech_type",
  "session",
  "lang",
  "hide_chair",
];

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
const PROVINCE_LABEL: Record<string, string> = Object.fromEntries(
  PROVINCES.map((p) => [p.code, p.label]),
);

const SPEECH_TYPE_LABELS: Record<SpeechType, string> = {
  floor: "Floor debate",
  question_period: "Question Period",
  statement: "Member statements",
  committee: "Committee",
  point_of_order: "Points of order",
  group: "Group / chant",
};

const MIN_SIMILARITY_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 0.5, label: "≥ 50% (looser)" },
  { value: 0.6, label: "≥ 60%" },
  { value: 0.7, label: "≥ 70%" },
  { value: 0.8, label: "≥ 80% (strictest)" },
];

const LEVEL_OPTIONS: Array<{ value: SpeechSearchFilter["level"]; label: string }> = [
  { value: "federal", label: "Federal" },
  { value: "provincial", label: "Provincial" },
  { value: "municipal", label: "Municipal" },
];

const LANG_OPTIONS: Array<{ value: NonNullable<SpeechSearchFilter["lang"]>; label: string }> = [
  { value: "any", label: "Any" },
  { value: "en", label: "English" },
  { value: "fr", label: "Français" },
];

// Pure predicates so the +Filter menu and the chip render loop stay
// consistent. `hide_chair` is uniquely toggle-only — the menu item flips
// it to true; clearing the chip flips it back to undefined.
function isActive(t: FilterType, v: SpeechSearchFilter): boolean {
  switch (t) {
    case "lang":           return !!v.lang && v.lang !== "any";
    case "level":          return !!v.level;
    case "province":       return !!v.province_territory;
    case "party":          return !!v.party;
    case "date":           return !!v.from || !!v.to;
    case "hide_chair":     return v.exclude_presiding === true;
    case "min_similarity": return v.min_similarity != null && v.min_similarity > 0;
    case "session":        return v.parliament_number != null && v.session_number != null;
    case "speech_type":    return !!v.speech_types && v.speech_types.length > 0;
  }
}

function chipLabel(t: FilterType, v: SpeechSearchFilter): string {
  switch (t) {
    case "lang":
      return v.lang === "fr" ? "Français" : v.lang === "en" ? "English" : "Language";
    case "level":
      return v.level ? `${v.level[0].toUpperCase()}${v.level.slice(1)}` : "Level";
    case "province":
      return v.province_territory
        ? PROVINCE_LABEL[v.province_territory] ?? v.province_territory
        : "Province";
    case "party":
      return v.party ?? "Party";
    case "date": {
      const from = v.from;
      const to = v.to;
      if (from && to) return `${from} → ${to}`;
      if (from)       return `Since ${from}`;
      if (to)         return `Until ${to}`;
      return "Date range";
    }
    case "hide_chair":     return "Hide chair speech";
    case "min_similarity": return `≥ ${Math.round((v.min_similarity ?? 0) * 100)}% match`;
    case "session":
      return v.parliament_number != null && v.session_number != null
        ? `${v.parliament_number}-${v.session_number}`
        : "Session";
    case "speech_type": {
      const ts = v.speech_types ?? [];
      if (ts.length === 0) return "Speech type";
      if (ts.length === 1) return SPEECH_TYPE_LABELS[ts[0]];
      return `${ts.length} types`;
    }
  }
}

function clearPatch(t: FilterType): Partial<SpeechSearchFilter> {
  switch (t) {
    case "lang":           return { lang: "any" };
    case "level":          return { level: undefined };
    case "province":       return { province_territory: undefined };
    case "party":          return { party: undefined };
    case "date":           return { from: undefined, to: undefined };
    case "hide_chair":     return { exclude_presiding: undefined };
    case "min_similarity": return { min_similarity: undefined };
    case "session":        return { parliament_number: undefined, session_number: undefined };
    case "speech_type":    return { speech_types: undefined };
  }
}

export interface SpeechFiltersProps {
  value: SpeechSearchFilter;
  onChange: (patch: Partial<SpeechSearchFilter>) => void;
  /** Hide filter types that don't make sense in a particular context. */
  hide?: FilterType[];
}

type OpenState =
  | { kind: "menu" }
  | { kind: "picker"; type: FilterType }
  | null;

export function SpeechFilters({ value, onChange, hide = [] }: SpeechFiltersProps) {
  const [open, setOpen] = useState<OpenState>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Click-outside / escape-key dismiss. Same pattern as PoliticianPinChips.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const root = rootRef.current;
      if (!root) return;
      if (!root.contains(e.target as Node)) setOpen(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const visible = useMemo(
    () => ALL_FILTERS.filter((t) => !hide.includes(t)),
    [hide],
  );
  const activeTypes = useMemo(
    () => visible.filter((t) => isActive(t, value)),
    [visible, value],
  );
  const inactiveTypes = useMemo(
    () => visible.filter((t) => !isActive(t, value)),
    [visible, value],
  );

  const applyAndClose = (patch: Partial<SpeechSearchFilter>) => {
    onChange({ ...patch, page: 1 });
    setOpen(null);
  };

  const handleAddFromMenu = (t: FilterType) => {
    if (t === "hide_chair") {
      // No picker — toggle directly.
      applyAndClose({ exclude_presiding: true });
      return;
    }
    setOpen({ kind: "picker", type: t });
  };

  const popoverType = open?.kind === "picker" ? open.type : null;

  return (
    <div className="cpd-filter-bar" role="group" aria-label="Search filters" ref={rootRef}>
      {activeTypes.map((t) => (
        <span key={t} className="cpd-filter-chip-wrap">
          <button
            type="button"
            className={`cpd-filter-chip${popoverType === t ? " cpd-filter-chip--editing" : ""}`}
            onClick={() => setOpen({ kind: "picker", type: t })}
            aria-haspopup="dialog"
            aria-expanded={popoverType === t}
            title={`Edit ${FILTER_LABELS[t]}`}
          >
            <span className="cpd-filter-chip__type">{FILTER_LABELS[t]}:</span>
            <span className="cpd-filter-chip__value">{chipLabel(t, value)}</span>
          </button>
          <button
            type="button"
            className="cpd-filter-chip__remove"
            onClick={() => applyAndClose(clearPatch(t))}
            aria-label={`Remove ${FILTER_LABELS[t]} filter`}
          >
            ×
          </button>
          {popoverType === t && (
            <FilterPopover>
              {renderPicker(t, value, onChange, () => setOpen(null))}
            </FilterPopover>
          )}
        </span>
      ))}

      <span className="cpd-filter-menu-wrap">
        <button
          type="button"
          className="cpd-filter-menu__btn"
          onClick={() => setOpen(open?.kind === "menu" ? null : { kind: "menu" })}
          aria-haspopup="menu"
          aria-expanded={open?.kind === "menu"}
        >
          + Filter
        </button>
        {open?.kind === "menu" && (
          <FilterPopover variant="menu">
            {inactiveTypes.length === 0 ? (
              <p className="cpd-filter-menu__empty">All filters in use.</p>
            ) : (
              <ul className="cpd-filter-menu__list" role="menu">
                {inactiveTypes.map((t) => (
                  <li key={t} role="none">
                    <button
                      type="button"
                      role="menuitem"
                      className="cpd-filter-menu__item"
                      onClick={() => handleAddFromMenu(t)}
                    >
                      {FILTER_LABELS[t]}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </FilterPopover>
        )}
      </span>

      {/* Anchored picker for inactive-but-being-set filter (opened from
          menu). Active-chip pickers render inline next to their chip
          above; this one anchors to the +Filter button so the user has
          a visual handle while a brand-new filter is being configured. */}
      {popoverType && !activeTypes.includes(popoverType) && (
        <span className="cpd-filter-menu-wrap cpd-filter-menu-wrap--orphan">
          <FilterPopover>
            {renderPicker(popoverType, value, onChange, () => setOpen(null))}
          </FilterPopover>
        </span>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Popover shell — anchored absolutely below its parent wrapper.
// Click-outside dismiss is handled at the SpeechFilters root level.
// ─────────────────────────────────────────────────────────────────

interface PopoverProps {
  children: React.ReactNode;
  variant?: "default" | "menu";
}

function FilterPopover({ children, variant = "default" }: PopoverProps) {
  return (
    <div
      className={`cpd-filter-popover cpd-filter-popover--${variant}`}
      role="dialog"
    >
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Per-type pickers — small inline components rendered inside a
// FilterPopover. Each calls onChange + onClose when the user picks
// a value (or "Apply" for free-text inputs that need a confirmation
// step).
// ─────────────────────────────────────────────────────────────────

function renderPicker(
  t: FilterType,
  value: SpeechSearchFilter,
  onChange: (patch: Partial<SpeechSearchFilter>) => void,
  close: () => void,
) {
  const apply = (patch: Partial<SpeechSearchFilter>) => {
    onChange({ ...patch, page: 1 });
    close();
  };
  switch (t) {
    case "lang":           return <LangPicker value={value} apply={apply} />;
    case "level":          return <LevelPicker value={value} apply={apply} />;
    case "province":       return <ProvincePicker value={value} apply={apply} />;
    case "party":          return <PartyPicker value={value} apply={apply} />;
    case "date":           return <DateRangePicker value={value} apply={apply} />;
    case "hide_chair":     return <HideChairPicker value={value} apply={apply} />;
    case "min_similarity": return <MinSimilarityPicker value={value} apply={apply} />;
    case "session":        return <SessionPicker value={value} apply={apply} />;
    case "speech_type":    return <SpeechTypePicker value={value} apply={apply} />;
  }
}

interface PickerProps {
  value: SpeechSearchFilter;
  apply: (patch: Partial<SpeechSearchFilter>) => void;
}

function PickerHeader({ title }: { title: string }) {
  return <p className="cpd-filter-popover__title">{title}</p>;
}

function LangPicker({ value, apply }: PickerProps) {
  return (
    <>
      <PickerHeader title="Language" />
      <div className="cpd-filter-popover__radio-list">
        {LANG_OPTIONS.map((o) => (
          <label key={o.value} className="cpd-filter-popover__radio">
            <input
              type="radio"
              name="cpd-lang"
              checked={(value.lang ?? "any") === o.value}
              onChange={() => apply({ lang: o.value })}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    </>
  );
}

function LevelPicker({ value, apply }: PickerProps) {
  return (
    <>
      <PickerHeader title="Level" />
      <div className="cpd-filter-popover__radio-list">
        <label className="cpd-filter-popover__radio">
          <input
            type="radio"
            name="cpd-level"
            checked={!value.level}
            onChange={() => apply({ level: undefined })}
          />
          <span>Any</span>
        </label>
        {LEVEL_OPTIONS.map((o) => (
          <label key={o.value} className="cpd-filter-popover__radio">
            <input
              type="radio"
              name="cpd-level"
              checked={value.level === o.value}
              onChange={() => apply({ level: o.value })}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    </>
  );
}

function ProvincePicker({ value, apply }: PickerProps) {
  return (
    <>
      <PickerHeader title="Province / territory" />
      <select
        className="cpd-filter-popover__select"
        autoFocus
        value={value.province_territory ?? ""}
        onChange={(e) =>
          apply({ province_territory: e.target.value || undefined })
        }
      >
        <option value="">Any</option>
        {PROVINCES.map((p) => (
          <option key={p.code} value={p.code}>
            {p.label}
          </option>
        ))}
      </select>
    </>
  );
}

function PartyPicker({ value, apply }: PickerProps) {
  const [draft, setDraft] = useState(value.party ?? "");
  return (
    <>
      <PickerHeader title="Party" />
      <input
        type="text"
        className="cpd-filter-popover__input"
        autoFocus
        placeholder="e.g. Liberal"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") apply({ party: draft.trim() || undefined });
        }}
      />
      <div className="cpd-filter-popover__actions">
        <button
          type="button"
          className="cpd-filter-popover__btn"
          onClick={() => apply({ party: draft.trim() || undefined })}
        >
          Apply
        </button>
      </div>
    </>
  );
}

function DateRangePicker({ value, apply }: PickerProps) {
  const [from, setFrom] = useState(value.from ?? "");
  const [to, setTo] = useState(value.to ?? "");
  return (
    <>
      <PickerHeader title="Date range" />
      <label className="cpd-filter-popover__field">
        <span>From</span>
        <input
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
      </label>
      <label className="cpd-filter-popover__field">
        <span>To</span>
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </label>
      <div className="cpd-filter-popover__actions">
        <button
          type="button"
          className="cpd-filter-popover__btn"
          onClick={() =>
            apply({
              from: from || undefined,
              to: to || undefined,
            })
          }
        >
          Apply
        </button>
      </div>
    </>
  );
}

function HideChairPicker({ value, apply }: PickerProps) {
  // Reached only when the user re-opens the chip. The menu path toggles
  // straight on without rendering this picker.
  return (
    <>
      <PickerHeader title="Hide chair speech" />
      <p className="cpd-filter-popover__help">
        Hides procedural turns by Speakers, Chairs, and Présidents so substantive speeches surface.
      </p>
      <div className="cpd-filter-popover__actions">
        <button
          type="button"
          className="cpd-filter-popover__btn"
          onClick={() => apply({ exclude_presiding: !value.exclude_presiding ? true : undefined })}
        >
          {value.exclude_presiding ? "Show chair speech" : "Hide chair speech"}
        </button>
      </div>
    </>
  );
}

function MinSimilarityPicker({ value, apply }: PickerProps) {
  return (
    <>
      <PickerHeader title="Minimum similarity" />
      <p className="cpd-filter-popover__help">
        Drops weaker semantic matches. Only takes effect when a search term is set.
      </p>
      <div className="cpd-filter-popover__radio-list">
        <label className="cpd-filter-popover__radio">
          <input
            type="radio"
            name="cpd-minsim"
            checked={!value.min_similarity}
            onChange={() => apply({ min_similarity: undefined })}
          />
          <span>All matches</span>
        </label>
        {MIN_SIMILARITY_OPTIONS.map((o) => (
          <label key={o.value} className="cpd-filter-popover__radio">
            <input
              type="radio"
              name="cpd-minsim"
              checked={value.min_similarity === o.value}
              onChange={() => apply({ min_similarity: o.value })}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    </>
  );
}

function SessionPicker({ value, apply }: PickerProps) {
  const { sessions, loading } = useLegislativeSessions(
    value.level,
    value.province_territory,
  );
  if (!value.level) {
    return (
      <>
        <PickerHeader title="Parliament & session" />
        <p className="cpd-filter-popover__help">
          Pick a level (federal/provincial) first so we can show the right session list.
        </p>
      </>
    );
  }
  return (
    <>
      <PickerHeader title="Parliament &amp; session" />
      <select
        className="cpd-filter-popover__select"
        autoFocus
        value={
          value.parliament_number != null && value.session_number != null
            ? `${value.parliament_number}-${value.session_number}`
            : ""
        }
        onChange={(e) => {
          const v = e.target.value;
          if (!v) {
            apply({ parliament_number: undefined, session_number: undefined });
            return;
          }
          const [p, s] = v.split("-").map(Number);
          if (Number.isInteger(p) && Number.isInteger(s)) {
            apply({ parliament_number: p, session_number: s });
          }
        }}
        disabled={loading || sessions.length === 0}
      >
        <option value="">
          {loading
            ? "Loading…"
            : sessions.length === 0
            ? "No sessions for this jurisdiction"
            : "Any session"}
        </option>
        {sessions.map((s) => {
          const label = s.name
            ? `${s.parliament_number}-${s.session_number} · ${s.name}`
            : `${s.parliament_number}th Parl., Sess. ${s.session_number}${
                s.start_date ? ` (${s.start_date.slice(0, 4)})` : ""
              }`;
          return (
            <option
              key={`${s.parliament_number}-${s.session_number}`}
              value={`${s.parliament_number}-${s.session_number}`}
            >
              {label}
            </option>
          );
        })}
      </select>
    </>
  );
}

function SpeechTypePicker({ value, apply }: PickerProps) {
  const [draft, setDraft] = useState<Set<SpeechType>>(
    () => new Set(value.speech_types ?? []),
  );
  const toggle = (t: SpeechType) => {
    setDraft((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };
  return (
    <>
      <PickerHeader title="Speech type" />
      <div className="cpd-filter-popover__check-list">
        {SPEECH_TYPE_VALUES.map((t) => (
          <label key={t} className="cpd-filter-popover__check">
            <input
              type="checkbox"
              checked={draft.has(t)}
              onChange={() => toggle(t)}
            />
            <span>{SPEECH_TYPE_LABELS[t]}</span>
          </label>
        ))}
      </div>
      <div className="cpd-filter-popover__actions">
        <button
          type="button"
          className="cpd-filter-popover__btn"
          onClick={() =>
            apply({
              speech_types: draft.size > 0 ? Array.from(draft) : undefined,
            })
          }
        >
          Apply
        </button>
      </div>
    </>
  );
}
