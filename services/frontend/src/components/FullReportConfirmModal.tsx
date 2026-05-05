import type { ReportEstimate } from "../api";
import { AnalysisConfirmModal } from "./AnalysisConfirmModal";

interface Props {
  estimate: ReportEstimate;
  model: string | null;
  loading: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Back-compat shim. New code should use AnalysisConfirmModal directly.
 * This wrapper keeps existing per-politician callers (the upsell modal
 * embedded in AIContradictionAnalysis) working without modification.
 */
export function FullReportConfirmModal(props: Props) {
  return <AnalysisConfirmModal kind="full_report" {...props} />;
}
