import { useEffect, useRef, useState } from "react";

interface Props {
  initialValue: number;
  onApply: (n: number) => void;
  onCancel: () => void;
}

/**
 * Custom-N picker for "Analyse top N" when the user wants something
 * other than the preset options (25/50/100/200/500). Bounded at the
 * server's cap of 500 — anything bigger is rejected by the API zod
 * schema, so we don't pretend it's possible. Live cost preview shows
 * what the chosen N will cost for both Synthesize and Stance map kinds
 * so the user can budget before clicking Apply.
 *
 * Reuses the .ai-consent-modal shell so it visually matches the cost-
 * preview modal that opens after the user clicks a CTA.
 */
const MIN_N = 5;
const MAX_N = 500;
const SYNTH_BASE = 5;
const STANCE_BASE = 10;
const PER_BUCKET = 1;
const BUCKET_SIZE = 10;

function priceFor(base: number, n: number): number {
  const used = Math.min(Math.max(n, 0), MAX_N);
  return base + Math.ceil(used / BUCKET_SIZE) * PER_BUCKET;
}

export function AnalysisLimitDialog({ initialValue, onApply, onCancel }: Props) {
  const [value, setValue] = useState<number>(() => clamp(initialValue));
  const applyRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      if (e.key === "Enter" && isValid(value)) {
        e.preventDefault();
        onApply(value);
      }
    };
    window.addEventListener("keydown", onKey);
    applyRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, onApply, value]);

  const synthCost = priceFor(SYNTH_BASE, value);
  const stanceCost = priceFor(STANCE_BASE, value);

  return (
    <div
      className="ai-consent-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="analysis-limit-heading"
      onClick={onCancel}
    >
      <div className="ai-consent-modal__card" onClick={(e) => e.stopPropagation()}>
        <button
          className="ai-consent-modal__close"
          onClick={onCancel}
          aria-label="Cancel"
          type="button"
        >
          ×
        </button>

        <h2 id="analysis-limit-heading" className="ai-consent-modal__title">
          Set custom analysis size
        </h2>

        <div className="ai-consent-modal__body">
          <p>
            Choose how many top-ranked results to feed the model. Larger sets
            give richer synthesis but cost more credits. The maximum is{" "}
            <strong>{MAX_N}</strong> — the API rejects bigger payloads to keep
            generation under the model's context limit.
          </p>

          <div className="analysis-limit-dialog__inputs">
            <input
              type="range"
              min={MIN_N}
              max={MAX_N}
              step={1}
              value={value}
              onChange={(e) => setValue(clamp(Number(e.target.value)))}
              aria-label="Analysis size slider"
              className="analysis-limit-dialog__slider"
            />
            <input
              type="number"
              min={MIN_N}
              max={MAX_N}
              step={1}
              value={value}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (Number.isFinite(n)) setValue(clamp(n));
              }}
              aria-label="Analysis size"
              className="analysis-limit-dialog__number"
            />
          </div>

          <div className="full-report-modal__cost">
            <div className="full-report-modal__cost-row">
              <span>Synthesize cost</span>
              <strong>{synthCost} credits</strong>
            </div>
            <div className="full-report-modal__cost-row">
              <span>Stance map cost</span>
              <strong>{stanceCost} credits</strong>
            </div>
            <div className="full-report-modal__cost-row">
              <span>Quotes analysed</span>
              <strong>{value}</strong>
            </div>
          </div>

          <p className="full-report-modal__disclaimer">
            Cost is estimated server-side at submit time and may differ slightly
            if some chunk IDs in your selected window are stale.
          </p>
        </div>

        <div className="ai-consent-modal__footer">
          <button
            type="button"
            className="ai-consent-modal__cancel"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            ref={applyRef}
            type="button"
            className="ai-consent-modal__continue"
            onClick={() => onApply(value)}
            disabled={!isValid(value)}
          >
            Apply
          </button>
        </div>
      </div>
    </div>
  );
}

function clamp(n: number): number {
  if (!Number.isFinite(n)) return MIN_N;
  return Math.max(MIN_N, Math.min(MAX_N, Math.floor(n)));
}

function isValid(n: number): boolean {
  return Number.isFinite(n) && n >= MIN_N && n <= MAX_N && Number.isInteger(n);
}
