# Contributing

## Local development

Use Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Run `make verify` before every commit. When a change touches infrastructure or an integration boundary, also run `make integration`, `make smoke`, and `make test` with Qdrant and Redis running.

## Test tiers

1. **Unit** — deterministic and infrastructure-free.
2. **Integration-local** — real local Qdrant/Redis or other locally composed dependencies.
3. **End-to-end-local** — multiple internal subsystems connected together.
4. **Live-provider** — external credentials required; never the only acceptance evidence.
5. **Benchmark** — performance/evaluation workloads, separated from correctness CI.

Never weaken tests to make a phase pass. Fix the implementation, then rerun the affected test and cumulative regression suite.

## Secrets

Never commit `.env`, API keys, tokens, passwords, private datasets, or provider responses containing sensitive content. Configuration values that contain secrets must use secret-aware types and log redaction.
