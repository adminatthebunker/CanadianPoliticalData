export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface CommandArg {
  name: string;
  type: "int" | "str" | "date" | "bool";
  required: boolean;
  default?: number | string | boolean;
  help?: string;
}

export interface CommandSpec {
  key: string;
  category: "hansard" | "bills" | "enrichment" | "maintenance";
  description: string;
  args: CommandArg[];
}

export interface CommandsResponse {
  commands: CommandSpec[];
}

export interface JobRow {
  id: string;
  command: string;
  args: Record<string, unknown>;
  status: JobStatus;
  priority: number;
  schedule_id: string | null;
  requested_by: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  stdout_snippet?: string;
  stderr_snippet?: string;
  stdout_tail?: string;
  stderr_tail?: string;
  error: string | null;
}

export interface JobsListResponse {
  jobs: JobRow[];
}

export interface ScheduleRow {
  id: string;
  name: string;
  command: string;
  args: Record<string, unknown>;
  cron: string;
  enabled: boolean;
  last_enqueued_at: string | null;
  next_run_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface SchedulesResponse {
  schedules: ScheduleRow[];
}

export interface AdminStats {
  speeches: number;
  chunks: { total: number; embedded: number; pending: number };
  jobs: { queued: number; running: number; succeeded_24h: number; failed_24h: number };
  jurisdictions: { live: number; total: number };
  recent_failures: Array<{
    id: string;
    command: string;
    finished_at: string;
    error: string | null;
  }>;
}

export interface UsageGpuSample {
  sampled_at: string;
  mem_used_mb: number;
  mem_total_mb: number;
  util_gpu_pct: number;
  util_mem_pct: number;
  temperature_c: number | null;
  power_w: number | null;
}

export interface UsageTeiSample {
  sampled_at: string;
  queue_size: number | null;
  request_count_total: string | null;
  request_failure_total: string | null;
  request_duration_p50_ms: string | null;
  request_duration_p95_ms: string | null;
  request_duration_p99_ms: string | null;
  batch_next_size_avg: string | null;
}

export interface UsageSearchCounts {
  searches_5m: number;
  searches_60m: number;
  searches_24h: number;
  p50_60m: number | null;
  p95_60m: number | null;
  errors_60m: number;
}

export interface UsageSnapshot {
  gpu: UsageGpuSample | null;
  tei: UsageTeiSample | null;
  search: UsageSearchCounts;
}

export type UsageMetric =
  | "vram_used_mb"
  | "vram_pct"
  | "gpu_util_pct"
  | "tei_queue"
  | "tei_p95_ms"
  | "search_p95_ms"
  | "search_count";

export interface UsageTimeseriesPoint {
  t: string;
  v: number | null;
}

export interface UsageTimeseries {
  metric: UsageMetric;
  minutes: number;
  bucket_seconds: number;
  points: UsageTimeseriesPoint[];
}

export interface SlowSearchRow {
  created_at: string;
  endpoint: string;
  total_ms: number;
  tei_ms: number | null;
  sql_ms: number | null;
  result_count: number | null;
  was_anchor_query: boolean;
  was_authenticated: boolean;
  tier: string | null;
  status_code: number;
  cached_embedding: boolean;
  has_filters: boolean;
}

export interface SlowSearchesResponse {
  rows: SlowSearchRow[];
}
