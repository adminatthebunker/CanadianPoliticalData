import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  userFetch,
  UserUnauthorizedError,
  UserAuthDisabledError,
  type AnalysisEstimate,
  type AnalysisKind,
} from "../api";

/**
 * Generic "estimate → confirm modal → submit" plumbing for any paid
 * analysis kind. Replaces the kind-locked useFullReportSubmit; that
 * hook still exists as a thin shim around this one for back-compat
 * with existing per-politician callers.
 *
 * Caller supplies:
 *   - kind: which paid analysis is being submitted.
 *   - inputs: the kind-specific request body. The server's zod
 *     discriminated union enforces shape per kind; this hook is
 *     deliberately untyped on the inputs side (Record<string,
 *     unknown>) so each new kind can extend the body without
 *     touching this hook.
 *
 * Both /reports/estimate and /reports POST receive the same body
 * shape ({kind, ...inputs}) — the API route dispatches on kind for
 * cost formula and worker handler.
 */
export function useAnalysisSubmit(args: {
  kind: AnalysisKind;
  /**
   * Stable inputs object. Re-built by the caller on each render is
   * fine — the hook only reads it inside callbacks, so identity
   * doesn't drive re-renders. Caller is responsible for ensuring
   * the inputs are valid for the kind (e.g. chunk_ids non-empty).
   */
  inputs: Record<string, unknown>;
  /**
   * If returns false, openConfirm short-circuits without firing the
   * estimate request. Use for "don't open the modal if the query is
   * empty" — that pattern was special-cased in useFullReportSubmit.
   */
  canSubmit?: () => boolean;
  /** Where to navigate after a successful submit. Defaults to /account/reports?new=<id>. */
  successPath?: (jobId: string) => string;
}) {
  const { kind, inputs, canSubmit, successPath } = args;
  const navigate = useNavigate();
  const [estimating, setEstimating] = useState(false);
  const [estimate, setEstimate] = useState<AnalysisEstimate | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildBody = useCallback(
    () => JSON.stringify({ kind, ...inputs }),
    [kind, inputs]
  );

  const openConfirm = useCallback(async () => {
    if (canSubmit && !canSubmit()) return;
    setEstimating(true);
    setError(null);
    setEstimate(null);
    try {
      const est = await userFetch<AnalysisEstimate>("/reports/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: buildBody(),
      });
      setEstimate(est);
    } catch (e) {
      if (e instanceof UserUnauthorizedError) {
        setError("Please sign in to generate analyses.");
      } else if (e instanceof UserAuthDisabledError) {
        setError("User accounts are disabled on this server.");
      } else if (e instanceof Error && /^503\b/.test(e.message)) {
        setError("Premium analyses are not configured on this server.");
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("Failed to estimate cost.");
      }
    } finally {
      setEstimating(false);
    }
  }, [buildBody, canSubmit]);

  const submit = useCallback(async () => {
    if (!estimate) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await userFetch<{
        id: string;
        kind?: AnalysisKind;
        estimated_credits: number;
        balance_after: number;
      }>("/reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: buildBody(),
      });
      setEstimate(null);
      const target = successPath ? successPath(res.id) : `/account/reports?new=${res.id}`;
      navigate(target);
    } catch (e) {
      if (e instanceof Error && /^402\b/.test(e.message)) {
        setError("Not enough credits. Buy credits and try again.");
      } else if (e instanceof Error && /^429\b/.test(e.message)) {
        setError("Daily analysis limit reached for your tier. Try again tomorrow.");
      } else if (e instanceof Error && /^409\b/.test(e.message)) {
        setError("Cost has shifted. Re-open the dialog to see the updated cost.");
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("Failed to submit analysis.");
      }
    } finally {
      setSubmitting(false);
    }
  }, [estimate, buildBody, navigate, successPath]);

  const close = useCallback(() => {
    setEstimate(null);
    setError(null);
  }, []);

  return { estimating, estimate, submitting, error, openConfirm, submit, close };
}
