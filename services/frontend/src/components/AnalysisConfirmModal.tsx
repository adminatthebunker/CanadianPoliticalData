import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { AnalysisEstimate, AnalysisKind } from "../api";

interface Props {
  kind: AnalysisKind;
  estimate: AnalysisEstimate;
  model: string | null;
  loading: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Generic confirm-cost modal for any paid analysis kind. Replaces the
 * kind-locked FullReportConfirmModal; that component still exists as a
 * thin shim that hard-codes kind="full_report".
 *
 * The kind drives three pieces of copy:
 *   - Heading ("Generate full report?" / "Synthesize this search?" / etc.)
 *   - Body intro (what the model will do)
 *   - Confirm button label ("Generate report (–N credits)")
 *
 * Cost-table layout (Quotes analysed / Cost / Balance / After) is
 * kind-agnostic. So is the "Buy credits" branch when balance is short.
 */
export function AnalysisConfirmModal({
  kind,
  estimate,
  model,
  loading,
  error,
  onConfirm,
  onCancel,
}: Props) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  const copy = COPY_BY_KIND[kind] ?? COPY_BY_KIND.full_report;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    confirmRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const sufficient = estimate.sufficient;

  return (
    <div
      className="ai-consent-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="analysis-confirm-heading"
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

        <h2 id="analysis-confirm-heading" className="ai-consent-modal__title">
          {copy.heading}
        </h2>

        <div className="ai-consent-modal__body">
          {copy.intro(estimate)}

          <div className="full-report-modal__cost">
            <div className="full-report-modal__cost-row">
              <span>{copy.inputLabel}</span>
              <strong>
                {estimate.estimated_chunks}
                {estimate.capped && (
                  <span className="full-report-modal__capped"> (capped)</span>
                )}
              </strong>
            </div>
            <div className="full-report-modal__cost-row">
              <span>Cost</span>
              <strong>{estimate.estimated_credits} credits</strong>
            </div>
            <div className="full-report-modal__cost-row">
              <span>Your balance</span>
              <strong>{estimate.balance} credits</strong>
            </div>
            <div className="full-report-modal__cost-row">
              <span>After</span>
              <strong>
                {sufficient
                  ? `${estimate.balance - estimate.estimated_credits} credits`
                  : "—"}
              </strong>
            </div>
          </div>

          {model && (
            <div className="ai-consent-modal__model-row">
              <div className="ai-consent-modal__model-label">Model</div>
              <code className="ai-consent-modal__model-id">{model}</code>
              <div className="ai-consent-modal__model-sub">via OpenRouter</div>
            </div>
          )}

          {error && (
            <p className="full-report-modal__error" role="alert">
              {error}
            </p>
          )}

          <p className="full-report-modal__disclaimer">
            Canadian Political Data is not responsible for conclusions drawn from
            this analysis.
          </p>
        </div>

        <div className="ai-consent-modal__footer">
          <button
            type="button"
            className="ai-consent-modal__cancel"
            onClick={onCancel}
            disabled={loading}
          >
            Cancel
          </button>
          {sufficient ? (
            <button
              ref={confirmRef}
              type="button"
              className="ai-consent-modal__continue"
              onClick={onConfirm}
              disabled={loading}
            >
              {loading
                ? "Submitting…"
                : copy.confirmLabel(estimate.estimated_credits)}
            </button>
          ) : (
            <Link
              to="/account/credits"
              className="ai-consent-modal__continue"
              onClick={onCancel}
            >
              Buy credits
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

interface KindCopy {
  heading: string;
  intro: (estimate: AnalysisEstimate) => ReactNode;
  inputLabel: string;
  confirmLabel: (credits: number) => string;
}

const COPY_BY_KIND: Record<AnalysisKind, KindCopy> = {
  full_report: {
    heading: "Generate full report?",
    intro: (e) => (
      <p>
        A model will read every quote we have from{" "}
        <strong>{e.politician?.name ?? "this politician"}</strong> matching{" "}
        <em>"{e.query}"</em> and synthesise a report. Every claim links back to
        its source quote — <strong>always read the quotes</strong> before
        drawing conclusions. The synthesis is generative and can omit,
        misweight, or mischaracterise.
      </p>
    ),
    inputLabel: "Quotes analysed",
    confirmLabel: (c) => `Generate report (–${c} credits)`,
  },
  search_synthesis: {
    heading: "Synthesize this search?",
    intro: (e) => (
      <p>
        A model will read up to {e.estimated_chunks} top-matching quotes for{" "}
        <em>"{e.query}"</em> and produce a one-paragraph summary plus five
        bullet findings, each citing its sources. Every claim links back to a
        source quote — <strong>always read the quotes</strong> before drawing
        conclusions. The synthesis is generative.
      </p>
    ),
    inputLabel: "Quotes analysed",
    confirmLabel: (c) => `Synthesize (–${c} credits)`,
  },
  stance_map: {
    heading: "Map stances on this search?",
    intro: (e) => (
      <p>
        A model will read up to {e.estimated_chunks} top-matching quotes for{" "}
        <em>"{e.query}"</em> and group speakers by stance (for / against /
        conditional), with one exemplar quote per group. Every speaker links
        back to a source quote — <strong>always read the quotes</strong>{" "}
        before drawing conclusions. Stance classification is generative.
      </p>
    ),
    inputLabel: "Quotes classified",
    confirmLabel: (c) => `Map stances (–${c} credits)`,
  },
  // Slot-only entries for A-tier kinds; populated when those handlers ship.
  topic_pulse: {
    heading: "Generate topic pulse?",
    intro: (e) => (
      <p>
        A model will analyse the {e.estimated_chunks} representative quotes for
        this cluster and produce a "current state of debate" brief.
      </p>
    ),
    inputLabel: "Quotes analysed",
    confirmLabel: (c) => `Generate (–${c} credits)`,
  },
  narrative_timeline: {
    heading: "Generate narrative timeline?",
    intro: (e) => (
      <p>
        A model will segment the {e.estimated_chunks} top-matching quotes into
        eras and describe how framing shifted over time.
      </p>
    ),
    inputLabel: "Quotes analysed",
    confirmLabel: (c) => `Generate (–${c} credits)`,
  },
  voting_audit: {
    heading: "Audit voting consistency?",
    intro: (e) => (
      <p>
        A model will cross-reference up to {e.estimated_chunks} votes against
        what this politician has said about <em>"{e.query}"</em>.
      </p>
    ),
    inputLabel: "Votes analysed",
    confirmLabel: (c) => `Audit (–${c} credits)`,
  },
  compare_politicians: {
    heading: "Compare two politicians?",
    intro: (e) => (
      <p>
        A model will compare the two politicians on <em>"{e.query}"</em> using
        up to {e.estimated_chunks} of their most-relevant quotes each.
      </p>
    ),
    inputLabel: "Quotes analysed",
    confirmLabel: (c) => `Compare (–${c} credits)`,
  },
};
