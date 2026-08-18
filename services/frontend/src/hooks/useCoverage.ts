import { useFetch } from "./useFetch";

export interface CoverageJurisdiction {
  jurisdiction: string;
  legislature_name: string;
  seats: number | null;
  /** Municipalities (migration 0060) arrive in the same flat array as
   *  legislatures, ordered so each city directly follows its province.
   *  Indent on `parent_jurisdiction` rather than building a tree. */
  level: "federal" | "provincial" | "municipal";
  parent_jurisdiction: string | null;
  municipality_slug: string | null;
  bills_status: "live" | "partial" | "blocked" | "none";
  hansard_status: "live" | "partial" | "blocked" | "none";
  votes_status: "live" | "partial" | "blocked" | "none";
  committees_status: "live" | "partial" | "blocked" | "none";
  bills_difficulty: number | null;
  hansard_difficulty: number | null;
  votes_difficulty: number | null;
  committees_difficulty: number | null;
  blockers: string | null;
  notes: string | null;
  source_urls: Record<string, string>;
  bills_count: number;
  speeches_count: number;
  votes_count: number;
  politicians_count: number;
  last_verified_at: string | null;
  updated_at: string;
}

export interface CoverageResponse {
  jurisdictions: CoverageJurisdiction[];
  summary: {
    total: number;
    live: number;
    partial: number;
    blocked: number;
    none: number;
  };
}

export function useCoverage() {
  return useFetch<CoverageResponse>("/coverage");
}
