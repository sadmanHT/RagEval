"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type {
  Domain,
  EvaluationJobStatus,
  EvaluationSummary,
  HealthResponse,
  QueryResponse,
} from "@/lib/types";

const EXAMPLES = [
  "What does the financial report say about revenue?",
  "Summarize the governing law in the agreement.",
  "How does the research paper describe rank fusion?",
];

const DOMAINS: Array<{ label: string; value: Domain | "" }> = [
  { label: "Auto", value: "" },
  { label: "Financial", value: "financial" },
  { label: "Legal", value: "legal" },
  { label: "Research", value: "research" },
];

function BoltIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M13.2 2 4 13.1h6.6L9.8 22 20 9.7h-6.7L13.2 2Z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 7v5h-5M4 17v-5h5" />
      <path d="M6.2 9A7 7 0 0 1 18 6l2 2M18 15a7 7 0 0 1-11.8 3L4 16" />
    </svg>
  );
}

function formatMs(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value < 1 ? `${value.toFixed(2)} ms` : `${value.toFixed(1)} ms`;
}

function formatScore(value: number): string {
  return `${Math.round(value * 100)}%`;
}

async function readJson<T>(response: Response): Promise<T> {
  const body = (await response.json()) as T & {
    message?: string;
    detail?: string;
  };
  if (!response.ok) {
    const message =
      body.message ?? body.detail ?? `Request failed (${response.status})`;
    throw new Error(message);
  }
  return body;
}

export function Dashboard() {
  const [question, setQuestion] = useState(EXAMPLES[0]);
  const [domain, setDomain] = useState<Domain | "">("");
  const [topK, setTopK] = useState(8);
  const [useCache, setUseCache] = useState(true);
  const [includeDiagnostics, setIncludeDiagnostics] = useState(true);
  const [queryResult, setQueryResult] = useState<QueryResponse | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState(false);

  const [evaluation, setEvaluation] = useState<EvaluationSummary | null>(null);
  const [evaluationStatus, setEvaluationStatus] =
    useState<EvaluationJobStatus["status"] | "idle">("idle");
  const [evaluationError, setEvaluationError] = useState<string | null>(null);

  const refreshHealth = useCallback(async () => {
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      const payload = (await response.json()) as HealthResponse;
      setHealth(payload);
      setHealthError(false);
    } catch {
      setHealthError(true);
    }
  }, []);

  const refreshLatestEvaluation = useCallback(async () => {
    try {
      const response = await fetch("/api/evaluation/latest", {
        cache: "no-store",
      });
      if (response.status === 404) {
        return;
      }
      const payload = await readJson<EvaluationSummary>(response);
      setEvaluation(payload);
    } catch {
      // A missing/latest unavailable evaluation should not make the console unusable.
    }
  }, []);

  useEffect(() => {
    void refreshHealth();
    void refreshLatestEvaluation();
    const timer = window.setInterval(() => {
      void refreshHealth();
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [refreshHealth, refreshLatestEvaluation]);

  const runQuery = async (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || queryLoading) {
      return;
    }

    setQueryLoading(true);
    setQueryError(null);
    try {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          schema_version: "1.0",
          question: trimmed,
          domain: domain || null,
          filters: {},
          top_k: topK,
          options: {
            use_cache: useCache,
            include_retrieval_diagnostics: includeDiagnostics,
            stream: false,
          },
        }),
      });
      const payload = await readJson<QueryResponse>(response);
      setQueryResult(payload);
    } catch (error) {
      setQueryError(
        error instanceof Error ? error.message : "The query could not be completed.",
      );
    } finally {
      setQueryLoading(false);
      void refreshHealth();
    }
  };

  const pollEvaluation = useCallback(async (jobId: string) => {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 750));
      const response = await fetch(`/api/evaluation/jobs/${encodeURIComponent(jobId)}`, {
        cache: "no-store",
      });
      const payload = await readJson<EvaluationJobStatus>(response);
      setEvaluationStatus(payload.status);
      if (payload.status === "succeeded") {
        if (payload.summary) {
          setEvaluation(payload.summary);
        } else {
          await refreshLatestEvaluation();
        }
        return;
      }
      if (payload.status === "failed") {
        throw new Error(payload.error_code ?? "Evaluation failed.");
      }
    }
    throw new Error("Evaluation is still running. Check back shortly.");
  }, [refreshLatestEvaluation]);

  const runEvaluation = async () => {
    if (evaluationStatus === "queued" || evaluationStatus === "running") {
      return;
    }
    setEvaluationError(null);
    setEvaluationStatus("queued");
    try {
      const response = await fetch("/api/evaluation/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          schema_version: "1.0",
          reason: "frontend-console",
        }),
      });
      const accepted = await readJson<{
        job_id: string;
        status: EvaluationJobStatus["status"];
      }>(response);
      setEvaluationStatus(accepted.status);
      await pollEvaluation(accepted.job_id);
    } catch (error) {
      setEvaluationStatus("failed");
      setEvaluationError(
        error instanceof Error
          ? error.message
          : "The evaluation could not be completed.",
      );
    }
  };

  const componentEntries = useMemo(
    () => Object.entries(health?.components ?? {}),
    [health],
  );
  const healthy = health?.status === "ok" && !healthError;
  const runningEvaluation =
    evaluationStatus === "queued" || evaluationStatus === "running";

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#query" aria-label="RAG-Eval home">
          <span className="brandMark">
            <BoltIcon />
          </span>
          <span>RAG-Eval</span>
          <span className="version">console</span>
        </a>

        <nav className="nav" aria-label="Primary">
          <a href="#query">Query</a>
          <a href="#evaluation">Evaluate</a>
          <a href="#system">System</a>
        </nav>

        <div className={`statusPill ${healthy ? "statusOk" : "statusWarn"}`}>
          <span className="statusDot" />
          {healthError ? "Unavailable" : healthy ? "System healthy" : "Degraded"}
        </div>
      </header>

      <section className="hero">
        <div className="eyebrow">
          <span />
          Evaluation-first retrieval
        </div>
        <h1>
          Grounded answers.
          <br />
          <span>Visible evidence.</span>
        </h1>
        <p>
          Query the retrieval pipeline, inspect citations and latency, run
          deterministic evaluations, and see system health from one minimal console.
        </p>
        <div className="heroMeta">
          <span>FastAPI backend</span>
          <i />
          <span>Qdrant + BM25 + RRF</span>
          <i />
          <span>Server-side API key</span>
        </div>
      </section>

      <section className="workspace" id="query">
        <div className="sectionHeading">
          <div>
            <span className="sectionIndex">01</span>
            <h2>Query workspace</h2>
          </div>
          <p>Ask a question and inspect the evidence used to answer it.</p>
        </div>

        <div className="queryGrid">
          <form className="panel queryPanel" onSubmit={runQuery}>
            <div className="panelTopline">
              <span>Question</span>
              <span>{question.length}/10,000</span>
            </div>

            <div className="questionField">
              <SearchIcon />
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask about the indexed corpus…"
                maxLength={10_000}
                rows={5}
              />
            </div>

            <div className="exampleRow">
              {EXAMPLES.map((example, index) => (
                <button
                  className="exampleChip"
                  type="button"
                  key={example}
                  onClick={() => setQuestion(example)}
                >
                  {String(index + 1).padStart(2, "0")}
                </button>
              ))}
              <span>Try an example</span>
            </div>

            <div className="formSection">
              <label className="fieldLabel">Domain</label>
              <div className="segmented" role="group" aria-label="Domain">
                {DOMAINS.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    className={domain === item.value ? "active" : ""}
                    onClick={() => setDomain(item.value)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="controlsRow">
              <label className="numericField">
                <span>Top K</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={topK}
                  onChange={(event) =>
                    setTopK(
                      Math.max(1, Math.min(100, Number(event.target.value) || 1)),
                    )
                  }
                />
              </label>

              <label className="toggle">
                <input
                  type="checkbox"
                  checked={useCache}
                  onChange={(event) => setUseCache(event.target.checked)}
                />
                <span className="toggleTrack" />
                <span>Cache</span>
              </label>

              <label className="toggle">
                <input
                  type="checkbox"
                  checked={includeDiagnostics}
                  onChange={(event) => setIncludeDiagnostics(event.target.checked)}
                />
                <span className="toggleTrack" />
                <span>Diagnostics</span>
              </label>
            </div>

            <button
              className="primaryButton"
              type="submit"
              disabled={queryLoading || !question.trim()}
            >
              <span>{queryLoading ? "Running pipeline…" : "Run query"}</span>
              <ArrowIcon />
            </button>
          </form>

          <div className="panel resultPanel">
            {!queryResult && !queryLoading ? (
              <div className="emptyState">
                <span className="emptyIcon">
                  <BoltIcon />
                </span>
                <h3>Ready for a grounded answer</h3>
                <p>
                  Results appear here with citations, provider details, cache state,
                  and stage-level latency.
                </p>
              </div>
            ) : null}

            {queryLoading ? (
              <div className="loadingState">
                <div className="scanLine" />
                <span>Retrieving and grounding</span>
                <p>Dense + sparse retrieval → fusion → rerank → generation</p>
              </div>
            ) : null}

            {queryError ? (
              <div className="errorState">
                <span>Query failed</span>
                <p>{queryError}</p>
              </div>
            ) : null}

            {queryResult && !queryLoading ? (
              <div className="answer">
                <div className="answerMeta">
                  <span
                    className={
                      queryResult.insufficient_context
                        ? "answerState refused"
                        : "answerState grounded"
                    }
                  >
                    <CheckIcon />
                    {queryResult.insufficient_context
                      ? "Insufficient context"
                      : "Grounded"}
                  </span>
                  <span>
                    {queryResult.provider} · {queryResult.model}
                  </span>
                </div>

                <h3>Answer</h3>
                <p className="answerText">{queryResult.answer}</p>

                {queryResult.refusal_reason ? (
                  <div className="refusalNote">{queryResult.refusal_reason}</div>
                ) : null}

                <div className="metricsStrip">
                  <div>
                    <span>API</span>
                    <strong>{formatMs(queryResult.latency.api_ms)}</strong>
                  </div>
                  <div>
                    <span>Retrieval</span>
                    <strong>{formatMs(queryResult.latency.retrieval_ms)}</strong>
                  </div>
                  <div>
                    <span>Generation</span>
                    <strong>{formatMs(queryResult.latency.generation_ms)}</strong>
                  </div>
                  <div>
                    <span>Cache</span>
                    <strong>{queryResult.cache_hit ? "Hit" : "Miss"}</strong>
                  </div>
                </div>

                <div className="citationHeader">
                  <div>
                    <span>Citations</span>
                    <strong>{queryResult.citations.length}</strong>
                  </div>
                  <span className="requestId">
                    request {queryResult.request_id.slice(0, 8)}
                  </span>
                </div>

                <div className="citations">
                  {queryResult.citations.length ? (
                    queryResult.citations.map((citation, index) => (
                      <article className="citation" key={`${citation.chunk_id}-${index}`}>
                        <div>
                          <span className="citationNumber">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <code>{citation.chunk_id}</code>
                        </div>
                        <p>{citation.claim}</p>
                      </article>
                    ))
                  ) : (
                    <div className="noCitations">No citations returned.</div>
                  )}
                </div>

                {queryResult.retrieval ? (
                  <details className="diagnostics">
                    <summary>Retrieval diagnostics</summary>
                    <div className="diagnosticGrid">
                      <div>
                        <span>Final chunks</span>
                        <strong>{queryResult.retrieval.final_chunk_ids.length}</strong>
                      </div>
                      <div>
                        <span>Hop count</span>
                        <strong>{queryResult.retrieval.hop_count}</strong>
                      </div>
                      <div>
                        <span>Multi-hop</span>
                        <strong>
                          {queryResult.retrieval.multi_hop_triggered ? "Yes" : "No"}
                        </strong>
                      </div>
                    </div>
                  </details>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <section className="lowerGrid">
        <div className="sectionBlock" id="evaluation">
          <div className="sectionHeading compact">
            <div>
              <span className="sectionIndex">02</span>
              <h2>Evaluation</h2>
            </div>
          </div>

          <div className="panel evaluationPanel">
            <div className="evaluationHeader">
              <div>
                <span className="kicker">Deterministic release evaluation</span>
                <h3>
                  {evaluation
                    ? `${evaluation.configuration_count} configurations`
                    : "No completed run loaded"}
                </h3>
              </div>
              <button
                className="secondaryButton"
                type="button"
                onClick={runEvaluation}
                disabled={runningEvaluation}
              >
                <RefreshIcon />
                {runningEvaluation ? evaluationStatus : "Run evaluation"}
              </button>
            </div>

            {evaluationError ? (
              <div className="inlineError">{evaluationError}</div>
            ) : null}

            {evaluation ? (
              <>
                <div className="evaluationMeta">
                  <span>{evaluation.evidence_label}</span>
                  <span>{new Date(evaluation.completed_at).toLocaleString()}</span>
                </div>
                <div className="metricTable">
                  <div className="metricRow metricHead">
                    <span>Metric</span>
                    <span>Domain</span>
                    <span>Score</span>
                  </div>
                  {evaluation.metrics.slice(0, 8).map((metric, index) => (
                    <div
                      className="metricRow"
                      key={`${metric.config_id}-${metric.metric}-${metric.domain}-${index}`}
                    >
                      <span>
                        <strong>{metric.metric.replaceAll("_", " ")}</strong>
                        <small>{metric.config_id}</small>
                      </span>
                      <span>{metric.domain ?? "all"}</span>
                      <span className="score">{formatScore(metric.mean_score)}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="muted">
                Run the canonical evaluation job or wait for an existing completed
                result to appear.
              </p>
            )}
          </div>
        </div>

        <div className="sectionBlock" id="system">
          <div className="sectionHeading compact">
            <div>
              <span className="sectionIndex">03</span>
              <h2>System</h2>
            </div>
          </div>

          <div className="panel systemPanel">
            <div className="systemOverview">
              <span className={`systemOrb ${healthy ? "orbOk" : "orbWarn"}`}>
                <span />
              </span>
              <div>
                <span className="kicker">Readiness</span>
                <h3>{healthy ? "All systems nominal" : "Attention required"}</h3>
              </div>
              <button
                type="button"
                className="iconButton"
                onClick={() => void refreshHealth()}
                aria-label="Refresh system status"
              >
                <RefreshIcon />
              </button>
            </div>

            <div className="componentList">
              {componentEntries.length ? (
                componentEntries.map(([name, status]) => (
                  <div className="componentRow" key={name}>
                    <div>
                      <span className={`miniDot ${status === "ok" ? "ok" : "warn"}`} />
                      <strong>{name.replaceAll("_", " ")}</strong>
                    </div>
                    <span>{status}</span>
                  </div>
                ))
              ) : (
                <div className="componentRow">
                  <div>
                    <span className="miniDot warn" />
                    <strong>backend</strong>
                  </div>
                  <span>{healthError ? "unavailable" : "checking"}</span>
                </div>
              )}
            </div>

            <div className="securityNote">
              <CheckIcon />
              <span>
                API credentials stay server-side. The browser talks only to the
                same-origin frontend proxy.
              </span>
            </div>
          </div>
        </div>
      </section>

      <footer>
        <span>RAG-Eval</span>
        <span>Evaluation-first retrieval system</span>
        <span>Minimal console · v0.2</span>
      </footer>
    </main>
  );
}
