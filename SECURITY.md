# Security Policy

RAG-Eval is a portfolio and research-oriented engineering project with production-conscious defaults. Security issues that could expose credentials, private document content, authentication boundaries, or dependency/runtime weaknesses should be reported privately rather than opened as public issues.

## Supported version

The `main` branch is the actively maintained line. The published `v0.1.0` release remains historical release evidence; security fixes are expected to land on `main` first.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this repository when available. Include:

- the affected component or path;
- a concise reproduction or proof of concept;
- expected versus observed behavior;
- potential impact;
- any suggested mitigation.

Do not include real API keys, private corpora, customer data, or other secrets in the report. If a reproduction needs credentials, use clearly fake values.

## Security boundaries worth knowing

- Browser code never receives the FastAPI API key; the Next.js server-side proxy attaches it.
- Raw document/context text is not exported in traces, and raw query tracing is off by default.
- Runtime containers execute as non-root and Compose applies reduced capabilities/read-only filesystem constraints where supported.
- `/metrics` is intentionally unauthenticated for local Prometheus scraping. A production deployment must restrict that endpoint at the network or edge layer.
- The default Compose topology and local-development credentials are not a production deployment blueprint.

## Scope

Reports about dependency vulnerabilities, authentication bypass, secret leakage, unsafe tracing/logging, container escape/configuration, request-limit bypass, and unintended document disclosure are in scope.

Questions about model quality, retrieval relevance, or evaluation methodology are better filed as ordinary issues unless they create a concrete security or privacy impact.
