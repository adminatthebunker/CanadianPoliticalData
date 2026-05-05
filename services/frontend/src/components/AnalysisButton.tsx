import type { ReportsMeta, AnalysisKind } from "../api";
import { useUserAuth } from "../hooks/useUserAuth";
import { useAnalysisSubmit } from "../hooks/useAnalysisSubmit";
import { AnalysisConfirmModal } from "./AnalysisConfirmModal";

/**
 * Hover-tooltip text per kind. Renders via the native `title` attribute
 * — no popover library, no extra DOM, accessible by default. Shows when
 * the button is enabled; gives way to the more specific disabled-reason
 * tooltip when something gates submission.
 *
 * Keep these one sentence and end with a period — they sit in the OS
 * tooltip layer and shouldn't be paragraphs.
 */
const KIND_TOOLTIPS: Record<AnalysisKind, string> = {
  full_report:
    "Read every matching quote from this politician on this topic and synthesise a multi-section report with sourced citations.",
  search_synthesis:
    "Summarise the top results into one paragraph plus five bullet findings, each citing the source quotes.",
  stance_map:
    "Group speakers in these results by stance (for / against / conditional), with one exemplar quote per group.",
  topic_pulse:
    "Generate a 'state of debate' brief for this cluster — leading voices, contested points, temporal shift.",
  narrative_timeline:
    "Segment these results into eras and describe how the framing of this topic has shifted over time.",
  voting_audit:
    "Cross-reference this politician's votes against what they've said on this topic — speaks pro-X, voted against bill Y.",
  compare_politicians:
    "Side-by-side comparison of two politicians' positions on this topic, with sourced quotes for each.",
};

interface Props {
  kind: AnalysisKind;
  /**
   * Kind-specific request body. Discriminator (`kind`) is added by the
   * hook before POSTing. Caller is responsible for shape correctness;
   * the server's zod discriminated union is the boundary that
   * rejects malformed bodies.
   */
  inputs: Record<string, unknown>;
  /** Visible button text. */
  label: string;
  /** Premium reports / analyses meta from /reports/meta — gates the button. */
  meta: ReportsMeta | null;
  /**
   * Optional pre-flight gate. If returns false, the button is disabled
   * with the supplied message as a tooltip. Use for "no chunks
   * selected yet" or "topic field is empty" — anything kind-specific
   * that the generic disabled-reasons can't express.
   */
  guard?: () => string | null;
  /** Compact rendering for the timeline summary line; default is full button. */
  variant?: "default" | "compact";
  /** Override default success-redirect (defaults to /account/reports?new=<id>). */
  successPath?: (jobId: string) => string;
}

/**
 * Generic CTA shell for any paid analysis. Lives next to the modal +
 * hook of the same family. Adding a new kind requires (a) a server-side
 * cost formula + handler, (b) a copy entry in AnalysisConfirmModal's
 * COPY_BY_KIND, (c) one usage of this component with the right inputs.
 */
export function AnalysisButton({
  kind,
  inputs,
  label,
  meta,
  guard,
  variant = "default",
  successPath,
}: Props) {
  const { user } = useUserAuth();
  const { estimating, estimate, submitting, error, openConfirm, submit, close } =
    useAnalysisSubmit({ kind, inputs, successPath });

  let disabledReason: string | null = null;
  if (!meta) disabledReason = "Loading premium analyses status…";
  else if (!meta.enabled) disabledReason = "Premium analyses not configured on this server.";
  else if (!user) disabledReason = "Sign in to generate analyses.";
  else if (guard) disabledReason = guard();

  const className =
    variant === "compact"
      ? "ai-analysis__trigger ai-analysis__trigger--full ai-analysis__trigger--compact"
      : "ai-analysis__trigger ai-analysis__trigger--full";

  return (
    <>
      <button
        type="button"
        className={className}
        onClick={openConfirm}
        disabled={estimating || disabledReason !== null}
        title={disabledReason ?? KIND_TOOLTIPS[kind]}
        aria-label={`${label}: ${KIND_TOOLTIPS[kind]}`}
      >
        {estimating ? "Estimating…" : label}
      </button>

      {error && !estimate && (
        <p className="ai-analysis__disabled-hint" role="alert">
          {error}
        </p>
      )}

      {estimate && (
        <AnalysisConfirmModal
          kind={kind}
          estimate={estimate}
          model={meta?.model ?? null}
          loading={submitting}
          error={error}
          onConfirm={submit}
          onCancel={close}
        />
      )}
    </>
  );
}
