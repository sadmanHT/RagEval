export type Domain = "financial" | "legal" | "research";

export type Citation = {
  chunk_id: string;
  claim: string;
};

export type QueryResponse = {
  schema_version: string;
  request_id: string;
  answer: string;
  citations: Citation[];
  cited_chunk_ids: string[];
  insufficient_context: boolean;
  refusal_reason: string | null;
  provider: string;
  model: string;
  cache_hit: boolean;
  latency: {
    retrieval_ms: number;
    generation_ms: number;
    total_pipeline_ms: number;
    api_ms: number;
  };
  retrieval: {
    service_config_fingerprint: string;
    rerank_config_fingerprint: string;
    final_chunk_ids: string[];
    hop_count: number;
    multi_hop_triggered: boolean;
  } | null;
};

export type HealthResponse = {
  schema_version: string;
  status: "ok" | "degraded";
  components: Record<string, "ok" | "degraded">;
};

export type EvaluationMetricSummary = {
  config_id: string;
  metric: string;
  domain: Domain | null;
  count: number;
  mean_score: number;
};

export type EvaluationSummary = {
  schema_version: string;
  job_id: string;
  completed_at: string;
  dataset_fingerprint: string;
  matrix_fingerprint: string;
  evidence_label: string;
  configuration_count: number;
  metrics: EvaluationMetricSummary[];
};

export type EvaluationJobStatus = {
  schema_version: string;
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  submitted_at: string;
  started_at: string | null;
  completed_at: string | null;
  summary: EvaluationSummary | null;
  error_code: string | null;
};
