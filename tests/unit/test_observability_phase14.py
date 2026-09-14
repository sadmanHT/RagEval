from __future__ import annotations

import hashlib

from rageval.generation import AssembledContext, ContextChunk, GroundedGenerationResponse
from rageval.generation.models import RetrievalRouteDecision
from rageval.models import Chunk, Citation, GroundedAnswer, RerankResult, RetrievalResult
from rageval.observability import (
    DriftStatus,
    LangfuseTraceSink,
    PrometheusMetrics,
    SafeAggregateDriftMonitor,
    build_query_trace,
)
from rageval.retrieval.service.models import (
    MultiHopDecision,
    MultiHopMode,
    RetrievalHopTrace,
    RetrievalServiceResponse,
)


def _response() -> GroundedGenerationResponse:
    chunk = Chunk(
        chunk_id="chk_phase14_trace",
        document_id="doc_phase14_trace",
        ordinal=0,
        text="sensitive document content must never be traced",
        token_count=7,
        config_fingerprint="a" * 64,
    )
    retrieval = RetrievalResult(
        chunk=chunk,
        score=0.031,
        rank=2,
        retriever="hybrid-rrf",
        metadata={
            "dense_rank": 1,
            "sparse_rank": 2,
            "dense_rrf_contribution": 0.016,
            "sparse_rrf_contribution": 0.015,
        },
    )
    reranked = RerankResult(
        retrieval=retrieval,
        rerank_score=0.93,
        rank=1,
        reranker="fixture-reranker",
        metadata={"pre_rerank_rank": 2, "post_rerank_rank": 1},
    )
    retrieval_response = RetrievalServiceResponse(
        query="sensitive user query",
        normalized_query="sensitive user query",
        final_context=(reranked,),
        hop_traces=(
            RetrievalHopTrace(
                hop=1,
                query="sensitive user query",
                retrieval_query="sensitive user query",
                expansions=(),
                candidate_chunk_ids=("chk_phase14_trace", "chk_other_candidate"),
                hybrid_config_fingerprint="b" * 64,
                dense_latency_ms=1.0,
                sparse_latency_ms=1.0,
                total_latency_ms=2.0,
            ),
        ),
        multi_hop=MultiHopDecision(
            triggered=False,
            mode=MultiHopMode.OFF,
            reason="single-hop fixture",
        ),
        service_config_fingerprint="c" * 64,
        rerank_config_fingerprint="d" * 64,
        total_latency_ms=3.0,
    )
    context = AssembledContext(
        rendered="sensitive assembled context must never be traced",
        chunks=(
            ContextChunk(
                chunk_id="chk_phase14_trace",
                document_id="doc_phase14_trace",
                rank=1,
                text="sensitive document content must never be traced",
                token_count=7,
            ),
        ),
        included_chunk_ids=("chk_phase14_trace",),
        token_count=7,
        config_fingerprint="e" * 64,
    )
    answer = GroundedAnswer(
        question="sensitive user query",
        answer="Supported answer.",
        citations=[Citation(chunk_id="chk_phase14_trace", claim="Supported answer.")],
        cited_chunk_ids=["chk_phase14_trace"],
        provider="fake",
        model="fixture-model",
        input_tokens=12,
        output_tokens=3,
        latency_ms=4.0,
    )
    return GroundedGenerationResponse(
        answer=answer,
        retrieval=retrieval_response,
        context=context,
        route=RetrievalRouteDecision(
            retrieval_required=True,
            router="fixture-router",
            reason="domain query",
        ),
        generation_config_fingerprint="f" * 64,
        total_latency_ms=7.0,
    )


def test_trace_captures_rank_fusion_citations_and_redacts_raw_content() -> None:
    trace = build_query_trace(
        request_id="request-phase14",
        question="sensitive user query",
        response=_response(),
        cache_hit=False,
        api_ms=8.0,
        include_query_text=False,
    )
    assert trace.query is not None
    assert trace.query.query_text is None
    assert trace.query.query_sha256 == hashlib.sha256(b"sensitive user query").hexdigest()
    assert trace.query.hop_candidate_ids == (("chk_phase14_trace", "chk_other_candidate"),)
    result = trace.query.final_results[0]
    assert result.dense_rank == 1
    assert result.sparse_rank == 2
    assert result.pre_rerank_rank == 2
    assert result.post_rerank_rank == 1
    assert result.rrf_score == 0.031
    assert result.rerank_score == 0.93
    assert trace.query.context_chunk_ids == ("chk_phase14_trace",)
    assert trace.query.cited_chunk_ids == ("chk_phase14_trace",)
    assert trace.query.citations_valid_for_context is True
    serialized = trace.model_dump_json()
    assert "sensitive document content" not in serialized
    assert "sensitive assembled context" not in serialized
    assert "sensitive user query" not in serialized


def test_trace_can_explicitly_include_query_text_without_document_content() -> None:
    trace = build_query_trace(
        request_id="request-phase14-raw-query",
        question="sensitive user query",
        response=_response(),
        cache_hit=True,
        api_ms=1.0,
        include_query_text=True,
    )
    assert trace.query is not None
    assert trace.query.query_text == "sensitive user query"
    assert "sensitive document content" not in trace.model_dump_json()


class _FakeObservation:
    def __init__(self) -> None:
        self.output: dict[str, object] | None = None
        self.ended = False

    def update(self, **kwargs: object) -> object:
        raw = kwargs.get("output")
        self.output = raw if isinstance(raw, dict) else None
        return self

    def end(self) -> object:
        self.ended = True
        return self


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None
        self.observation = _FakeObservation()
        self.flushed = False
        self.closed = False

    def create_trace_id(self, *, seed: str | None = None) -> str:
        assert seed is not None
        return hashlib.sha256(seed.encode()).hexdigest()[:32]

    def start_observation(self, **kwargs: object) -> _FakeObservation:
        self.kwargs = kwargs
        return self.observation

    def flush(self) -> object:
        self.flushed = True
        return None

    def shutdown(self) -> object:
        self.closed = True
        return None


def test_langfuse_adapter_receives_only_sanitized_trace_payload() -> None:
    client = _FakeLangfuseClient()
    sink = LangfuseTraceSink(client=client)
    trace = build_query_trace(
        request_id="request-phase14-langfuse",
        question="sensitive user query",
        response=_response(),
        cache_hit=False,
        api_ms=2.0,
        include_query_text=False,
    )
    sink.record(trace)
    sink.flush()
    sink.close()

    assert client.kwargs is not None
    payload = str(client.kwargs)
    assert "sensitive user query" not in payload
    assert "sensitive document content" not in payload
    assert "dense_rank" in payload
    assert client.observation.ended is True
    assert client.flushed is True
    assert client.closed is True


def test_prometheus_metrics_use_bounded_labels_and_histograms() -> None:
    metrics = PrometheusMetrics()
    metrics.observe_http(
        route="/eval/jobs/unbounded-random-id",
        method="GET",
        status_code=500,
        duration_ms=125.0,
    )
    metrics.observe_stage("retrieval", 50.0)
    metrics.observe_cache("hit")
    metrics.observe_tokens(provider="fake", input_tokens=10, output_tokens=2)
    rendered = metrics.render().decode()

    assert "rageval_http_requests_total" in rendered
    assert "rageval_http_request_duration_seconds_bucket" in rendered
    assert 'route="other"' in rendered
    assert "unbounded-random-id" not in rendered
    assert 'stage="retrieval"' in rendered
    assert 'outcome="hit"' in rendered


def test_drift_hooks_keep_only_bounded_numeric_features_and_gate_small_samples() -> None:
    monitor = SafeAggregateDriftMonitor(
        min_samples=2,
        relative_shift_threshold=0.25,
        max_samples=3,
    )
    monitor.observe_query("short", baseline=True)
    monitor.observe_query("longer query", baseline=True)
    monitor.observe_query("x")
    assert monitor.compare_query_lengths().status is DriftStatus.INSUFFICIENT_DATA

    monitor.observe_query("x")
    comparison = monitor.compare_query_lengths()
    assert comparison.status is DriftStatus.POTENTIAL_SHIFT
    assert not hasattr(monitor, "queries")

    monitor.observe_embedding([3.0, 4.0], baseline=True)
    monitor.observe_embedding([0.0, 5.0], baseline=True)
    monitor.observe_embedding([6.0, 8.0])
    monitor.observe_embedding([6.0, 8.0])
    assert monitor.compare_embedding_norms().status is DriftStatus.POTENTIAL_SHIFT
