export interface Repository {
  id: string;
  name: string;
  url: string;
  sha: string | null;
  status: string;
  files: number;
  chunks: number;
  error: string | null;
  meta: { fixture?: boolean; embedding_model?: string; skipped?: number };
}
export interface Health {
  backend: string;
  database: string;
  pgvector: string | null;
  gemini_configured: boolean;
  gemini_model: string;
  github_configured: boolean;
  github_remote_write_enabled: boolean;
  local_test_execution_enabled: boolean;
  embedding_model: string;
  version: string;
}
export interface Evidence {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  sha: string;
  content: string;
  score: number;
  ranks: Record<string, number>;
  url: string;
}
export interface SearchResult {
  evidence: Evidence[];
  answer?: string;
  insufficient_evidence?: boolean;
  latency_ms: number;
  mode: string;
}
export interface Step {
  id: string;
  created_at: string;
  data: { stage: string; [key: string]: unknown };
}
export interface TestResult {
  id: string;
  status: string;
  data: {
    stdout: string;
    stderr: string;
    exit_code: number;
    duration_ms: number;
    command: string[];
  };
}
export interface Run {
  id: string;
  repository_id: string;
  status: string;
  created_at: string;
  steps?: Step[];
  test?: TestResult;
  data: {
    issue: string;
    issue_number?: number;
    origin?: string;
    stage?: string;
    error?: string;
    evidence?: Evidence[];
    tools?: unknown[];
    proposal?: {
      diagnosis: string;
      confidence: string;
      plan: string[];
      test_plan: string;
      limitations: string[];
    };
    patch?: {
      diff: string;
      affected_paths: string[];
      sha: string;
      validation: string;
    };
    pr_url?: string;
  };
}
export interface Metrics {
  counts: Record<string, number>;
  agent_outcomes: Record<string, number>;
  gemini_requests_today: number;
  gemini_daily_budget: number;
}
export interface Evaluation {
  id: string;
  data: {
    timestamp: string;
    cases: number;
    methodology: string;
    results: Record<
      string,
      {
        recall_at_5: number;
        mrr: number;
        cases: {
          query: string;
          hit_at_5: boolean;
          reciprocal_rank: number;
          citation_validity: boolean;
          latency_ms: number;
        }[];
      }
    >;
  };
}
export async function api<T>(path: string, data?: unknown): Promise<T> {
  const response = await fetch(
    "/api" + path,
    data === undefined
      ? { cache: "no-store" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  const body = await response
    .json()
    .catch(() => ({ detail: "Backend returned an unreadable response" }));
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail),
    );
  return body as T;
}
