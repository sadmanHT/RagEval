# RAG-Eval Portfolio Demo

This walkthrough is the shortest reproducible way to show the product, the serving boundary, observability, and failure recovery without overstating the evidence in the repository.

## Evidence boundary

The default Docker runtime is a deterministic operational fixture. It exercises the real FastAPI, Redis cache, readiness, metrics, evaluation-job, frontend BFF, and observability boundaries without requiring hosted-model credentials or a private corpus.

It is appropriate for demonstrating system mechanics and engineering decisions. It is **not** representative evidence for production retrieval quality, hosted-model quality, hallucination rate, latency SLOs, or corpus-scale performance.

The representative ~12,000-document corpus and target ~200-question reviewed evaluation set are not committed to this repository.

## 5-minute walkthrough

### 1. Start the stack

```bash
export RAGEVAL_SERVING_API_KEY=portfolio-demo-local-key
docker compose up -d --build qdrant redis api frontend prometheus grafana
```

Open:

- Product console: `http://localhost:3001`
- FastAPI / Swagger: `http://localhost:8000/docs`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

Wait for the stack to become healthy, then run:

```bash
make ops-smoke
```

### 2. Show a grounded query

In the product console, ask:

> What does the operational fixture verify?

The deterministic runtime should return the fixture-supported answer with a canonical citation. Use the result to point out:

- grounded-answer versus refusal state;
- source/citation identity;
- retrieval diagnostics;
- provider/model metadata;
- request ID and latency/cache information.

The important architectural point is that the browser is not implementing RAG logic. It calls same-origin Next.js route handlers, which attach the API key server-side and proxy the canonical FastAPI service.

### 3. Show evaluation as a product feature

Use the evaluation panel to submit an evaluation run and inspect the resulting status/summary.

The demo fixture keeps this deterministic and credential-free. The production-oriented implementation behind it supports resumable evaluation, metric slices, comparative configurations, regression policies, and machine-readable reports.

### 4. Show observability

Open Grafana and Prometheus after exercising the query path.

Discuss the operational signals rather than raw document text:

- request volume and latency;
- cache behavior;
- provider/dependency failures;
- evaluation queue state;
- dependency readiness.

Raw document/context text is not exported in traces, and raw query text is disabled by default.

### 5. Demonstrate dependency failure and recovery

Stop Qdrant:

```bash
docker compose stop qdrant
```

Check readiness:

```bash
curl -i http://localhost:8000/health/ready
```

Readiness should degrade while process liveness remains a separate concern. Dependency metrics should reflect the failed Qdrant check.

Restart Qdrant:

```bash
docker compose start qdrant
```

Then verify recovery:

```bash
curl -i http://localhost:8000/health/ready
```

This demonstrates that dependency health is part of the serving contract rather than hidden behind a generic process-up signal.

### 6. Tear down cleanly

```bash
make ops-down
```

## Deeper engineering validation

For a longer technical walkthrough, run:

```bash
make full-validation
make release-evaluation
make container-test
make frontend-build
```

The CI pipeline additionally validates the complete repository suite in the container tier, local Tesseract OCR, dependency/secret scanning, non-root runtimes, the 15 deterministic/adversarial connected-system scenarios, and Qdrant outage plus recovery behavior.

## Interview talking points

A concise explanation of the project is:

> RAG-Eval treats retrieval quality and evidence as first-class engineering concerns. Dense and sparse retrieval share canonical chunk identities, RRF combines ranks without mixing incompatible raw scores, reranking and bounded multi-hop preserve retrieval evidence, generation is constrained to supplied context with validated citations and refusal behavior, and the same provenance flows into evaluation, caching, observability, and the product UI.

Useful design decisions to discuss:

1. **Hybrid retrieval instead of one retriever:** dense and BM25/BM25+ cover different failure modes, while RRF avoids pretending their score scales are directly comparable.
2. **Canonical identities:** document/chunk IDs survive retrieval, reranking, context assembly, citation validation, evaluation, caching, and tracing.
3. **Grounding by construction:** unsupported context should produce an explicit refusal rather than an answer without evidence.
4. **Evaluation before optimization:** ablations and regression gates are preferred over choosing a retrieval configuration by intuition.
5. **Thin frontend boundary:** credentials and RAG logic stay server-side; the UI exposes evidence rather than reimplementing the backend.
6. **Operational failure is testable:** readiness, metrics, outage simulation, and recovery are part of acceptance rather than afterthoughts.

## What not to claim

Do not present the committed fixtures as evidence of:

- production retrieval accuracy;
- a production hallucination percentage;
- a universally superior chunking/retrieval configuration;
- hosted-provider quality without a credentialed provider run;
- production throughput, cost, or latency SLOs;
- validation over the uncommitted representative corpus.

Those require environment-specific evidence beyond the public deterministic acceptance path.
