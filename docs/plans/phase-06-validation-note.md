# Phase 6 Live-Provider Boundary

Deterministic acceptance does not require hosted credentials. The OpenAI adapter is tested with an injected HTTP transport for request shape, input ordering, vector dimension validation, and provider-error handling. A live OpenAI request is additional evidence only and must not be reported as passed unless credentials are present and the request actually runs.
