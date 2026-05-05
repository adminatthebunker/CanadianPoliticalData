import type { ReportsMeta } from "../api";
import { AnalysisButton } from "./AnalysisButton";

interface Props {
  politicianId: string;
  query: string;
  meta: ReportsMeta | null;
}

/**
 * Per-politician "Full report — analyze everything" CTA. Thin wrapper
 * over AnalysisButton with kind="full_report" and the politician-card
 * input shape. Pre-existing call sites continue to use this name; new
 * paid-analysis CTAs should use AnalysisButton directly.
 */
export function AIFullReportButton({ politicianId, query, meta }: Props) {
  return (
    <AnalysisButton
      kind="full_report"
      inputs={{ politician_id: politicianId, query }}
      label="Full report — analyze everything"
      meta={meta}
      guard={() => (query.trim() ? null : "Enter a search topic to generate a report.")}
    />
  );
}
