export type Status = "PENDING" | "RUNNING" | "PASSED" | "FAILED" | "NEEDS_REVIEW" | "ERROR";
export type GateStatus = "PASS" | "FAIL" | "NEEDS_REVIEW";

export interface Artifact {
  id: string;
  run_id: string;
  step_id?: string;
  kind: string;
  label: string;
  url?: string;
  path?: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface StepResult {
  id: string;
  step_id: string;
  step_name: string;
  step_type: string;
  status: Status;
  summary: string;
  duration_ms: number;
  evidence_ids: string[];
  expected?: unknown;
  actual?: unknown;
}

export interface Gate {
  status: GateStatus;
  reason: string;
  passed_required: number;
  failed_required: number;
  review_required: number;
  policy: string;
}

export interface Diagnosis {
  status: string;
  summary: string;
  evidence_citations: string[];
  changed_files: string[];
  investigation: string[];
  confidence: string;
  provider: string;
}

export interface MemoryMatch {
  observation_id: string;
  title: string;
  narrative: string;
  created_at?: string;
  relevance: string;
}

export interface Run {
  id: string;
  deployment_id: string;
  workflow_version_id: string;
  status: Status;
  gate?: Gate;
  trace_id: string;
  baseline_run_id?: string;
  step_results: StepResult[];
  evidence: Artifact[];
  diagnosis?: Diagnosis;
  memory_matches: MemoryMatch[];
  integration_status: Record<string, string>;
  console_errors: Record<string, unknown>[];
  network_events: Record<string, unknown>[];
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface Deployment {
  id: string;
  environment: string;
  version: string;
  commit_sha: string;
  storefront_url: string;
  api_url: string;
  repository?: string;
  repository_provider: "github" | "gitlab" | "local";
  default_branch: string;
  pull_request_number?: number;
  pull_request_url?: string;
  base_sha?: string;
  head_sha?: string;
  changed_files: string[];
  created_at: string;
}

export interface WorkflowVersion {
  id: string;
  version: number;
  content_hash: string;
  approved: boolean;
  approved_by?: string;
}

export interface Overview {
  deployments: Deployment[];
  workflow_versions: WorkflowVersion[];
  runs: Run[];
  latest_run?: Run;
}
