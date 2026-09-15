# RAG-Eval Frontend Console

The frontend is a thin Next.js product surface over the existing FastAPI serving boundary. It does not implement retrieval, generation, evaluation, authentication policy, or corpus logic independently.

## What the console exposes

- **Query workspace** — question, optional domain, `top_k`, cache preference, and retrieval-diagnostic preference.
- **Grounded answer view** — answer/refusal state, citations, provider/model identity, request ID, cache state, and stage latency.
- **Evaluation view** — start the canonical evaluation job, follow queued/running/succeeded/failed state, and inspect the latest aggregate metric summaries.
- **System view** — display the backend readiness report and component health.

The visual system intentionally stays minimal: near-black and white surfaces, blue primary actions, green grounded/healthy states, and restrained amber for degraded/refusal states.

## Security boundary

Browser JavaScript never receives the FastAPI API key. The browser calls same-origin Next.js route handlers under `/api/*`; those server-side handlers attach `X-API-Key` when they call the canonical FastAPI endpoints.

Configure the frontend server with:

```bash
RAGEVAL_API_URL=http://localhost:8000
RAGEVAL_API_KEY=replace-this-local-key
```

`RAGEVAL_SERVING_API_KEY` is accepted as the server-side key fallback so Docker Compose can share the same local credential without copying it into client bundles.

## Local development

Start the backend dependencies/API separately, then run the frontend development server:

```bash
export RAGEVAL_SERVING_API_KEY=replace-this-local-key
make ops-up
make frontend-install
make frontend-dev
```

The Compose product stack exposes:

- frontend console: `http://localhost:3001`
- FastAPI / Swagger: `http://localhost:8000/docs`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

For a production-style frontend build without starting it:

```bash
make frontend-build
```

For the complete local operational smoke, including the browser-facing proxy path:

```bash
export RAGEVAL_SERVING_API_KEY=replace-this-local-key
make ops-smoke
```

The frontend smoke checks rendered HTML, readiness through the frontend proxy, a grounded cited query through the proxy, and the evaluation job lifecycle.

## Container model

The frontend builds to Next.js standalone output, runs as UID/GID `10001`, uses a read-only filesystem with a small `/tmp` tmpfs, drops Linux capabilities, and sets `no-new-privileges` in Compose. The host maps frontend port `3001` to the container's port `3000` so Grafana can retain host port `3000`.

## CI

`.github/workflows/frontend.yml` has two independent gates:

1. **frontend-quality** — install, strict TypeScript check, production Next.js build, production dependency audit, and frontend-surface secret scan.
2. **frontend-e2e** — clean Compose startup of Qdrant/Redis/API/frontend, product smoke through the Next.js proxy, non-root runtime assertion, and teardown.

The existing backend CI remains authoritative for the Python/RAG system and continues to run independently. A frontend change is accepted only when both the frontend gates and inherited backend gates are green.

## Evidence boundary

The frontend does not change the project's evaluation claims. Query/evaluation results shown by the console inherit the evidence boundary of the backend that produced them. The committed deterministic fixtures remain mechanics/grounding/traceability evidence, not representative production-quality or production-SLO evidence.
