## Summary

<!-- What changed, and why? Keep this focused on user/system impact. -->

## Validation

<!-- Check only what you actually ran. Add commands, CI links, or evidence artifacts when relevant. -->

- [ ] `make verify`
- [ ] `make integration` when infrastructure/integration behavior changed
- [ ] `make frontend-build` when frontend behavior changed
- [ ] `make ops-smoke` when serving/Compose/observability behavior changed
- [ ] GitHub CI is green on the exact PR head

## Evidence boundary

<!-- If this PR changes evaluation, benchmarks, retrieval, generation, or operational claims, state what the evidence does and does not prove. Do not convert fixture results into representative production claims. -->

## Security / privacy

- [ ] No secrets, private datasets, or sensitive provider responses are committed
- [ ] Logging/tracing changes preserve the project's redaction and raw-content boundaries
- [ ] Browser-facing changes do not expose backend API keys or duplicate RAG policy in client code

## Notes for reviewers

<!-- Call out architectural tradeoffs, migrations, follow-up work, or intentionally unchanged behavior. -->
