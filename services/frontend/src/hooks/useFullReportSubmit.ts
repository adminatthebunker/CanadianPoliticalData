import { useAnalysisSubmit } from "./useAnalysisSubmit";

/**
 * Back-compat shim around useAnalysisSubmit. Callers that pre-date the
 * generic analysis substrate (AIFullReportButton, the upsell in
 * AIContradictionAnalysis) keep working unchanged. New code should use
 * useAnalysisSubmit directly.
 */
export function useFullReportSubmit(politicianId: string, query: string) {
  return useAnalysisSubmit({
    kind: "full_report",
    inputs: { politician_id: politicianId, query },
    canSubmit: () => query.trim().length > 0,
  });
}
