from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from rageval.core.errors import IndexingError
from rageval.core.protocols import Retriever
from rageval.models.contracts import Chunk, DocumentRecord, Domain, RetrievalResult, SourceType
from rageval.retrieval.sparse import (
    BM25SparseIndex,
    BM25Variant,
    DomainAwareTokenizer,
    SparseDocumentInput,
    SparseIndexConfig,
    SparseSearchFilter,
)


def _document(document_id: str, domain: Domain) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        source_uri=f"fixture://{document_id}",
        source_type=SourceType.PDF,
        domain=domain,
        checksum_sha256="0" * 64,
    )


def _chunk(document_id: str, ordinal: int, text: str, *, fingerprint: str = "f" * 64) -> Chunk:
    return Chunk(
        chunk_id=f"chk_{document_id}_{ordinal}",
        document_id=document_id,
        ordinal=ordinal,
        text=text,
        token_count=max(1, len(text.split())),
        config_fingerprint=fingerprint,
        metadata={"source_element_ids": [f"elm_{document_id}_{ordinal}"]},
    )


def _input(
    document_id: str,
    domain: Domain,
    texts: list[str],
    *,
    source_date: date | None = None,
    fingerprint: str = "f" * 64,
) -> SparseDocumentInput:
    document = _document(document_id, domain)
    return SparseDocumentInput(
        document=document,
        chunks=tuple(
            _chunk(document_id, ordinal, text, fingerprint=fingerprint)
            for ordinal, text in enumerate(texts)
        ),
        source_date=source_date,
    )


def test_financial_tokenization_golden_preserves_exact_forms() -> None:
    tokenizer = DomainAwareTokenizer()
    assert tokenizer.tokenize(
        "10-K Q3 $AAPL BRK.B 12.5% EBITDA and revenue",
        domain=Domain.FINANCIAL,
    ) == ("10-k", "q3", "$aapl", "brk.b", "12.5%", "ebitda", "revenue")


def test_legal_tokenization_golden_preserves_clause_references() -> None:
    tokenizer = DomainAwareTokenizer()
    assert tokenizer.tokenize(
        "Section 7.4 and § 12.2 govern non-compete NDA",
        domain=Domain.LEGAL,
    ) == ("section", "7.4", "§12.2", "govern", "non-compete", "nda")


def test_research_tokenization_golden_preserves_acronyms_and_hyphenated_terms() -> None:
    tokenizer = DomainAwareTokenizer()
    assert tokenizer.tokenize(
        "RRF and BM25+ feed a cross-encoder in Eq. 3",
        domain=Domain.RESEARCH,
    ) == ("rrf", "bm25+", "feed", "cross-encoder", "eq", "3")


def test_sparse_filter_rejects_reversed_dates() -> None:
    with pytest.raises(ValidationError, match="date_from must be <= date_to"):
        SparseSearchFilter(date_from=date(2026, 2, 1), date_to=date(2026, 1, 1))


@pytest.mark.asyncio
async def test_exact_lexical_identifier_retrieves_chunk_when_fake_dense_misses() -> None:
    index = BM25SparseIndex.build(
        [
            _input(
                "doc_exact_001",
                Domain.LEGAL,
                [
                    "Section 7.4 requires notice by courier reference ZX-91.",
                    "General termination obligations apply to all parties.",
                ],
            )
        ]
    )

    class FakeDenseMiss:
        name = "fake-dense-miss"

        async def retrieve(
            self,
            query: str,
            *,
            top_k: int = 20,
        ) -> tuple[RetrievalResult, ...]:
            del query, top_k
            return ()

    dense = FakeDenseMiss()
    sparse_results = await index.retrieve("ZX-91", top_k=1)
    dense_results = await dense.retrieve("ZX-91", top_k=1)
    assert not dense_results
    assert sparse_results[0].chunk.text.startswith("Section 7.4")
    assert sparse_results[0].metadata["matched_terms"] == ["zx-91"]
    assert isinstance(index, Retriever)


@pytest.mark.asyncio
async def test_term_frequency_and_document_length_affect_ranking() -> None:
    index = BM25SparseIndex.build(
        [
            _input("doc_rank_001", Domain.RESEARCH, ["signal signal concise"]),
            _input(
                "doc_rank_002",
                Domain.RESEARCH,
                ["signal " + "background " * 30],
            ),
        ],
        config=SparseIndexConfig(variant=BM25Variant.BM25),
    )
    response = await index.search("signal", top_k=2)
    assert [result.chunk.document_id for result in response.results] == [
        "doc_rank_001",
        "doc_rank_002",
    ]
    assert response.results[0].score > response.results[1].score


@pytest.mark.asyncio
async def test_filters_apply_without_rewriting_global_rank_statistics() -> None:
    first_fp = "a" * 64
    second_fp = "b" * 64
    index = BM25SparseIndex.build(
        [
            _input(
                "doc_filter_fin",
                Domain.FINANCIAL,
                ["Q3 revenue ticker ACME"],
                source_date=date(2024, 3, 31),
                fingerprint=first_fp,
            ),
            _input(
                "doc_filter_leg",
                Domain.LEGAL,
                ["Section 7.4 revenue covenant"],
                source_date=date(2023, 6, 1),
                fingerprint=second_fp,
            ),
        ]
    )
    financial = await index.search(
        "revenue",
        filters=SparseSearchFilter(domain=Domain.FINANCIAL),
    )
    assert [result.chunk.document_id for result in financial.results] == ["doc_filter_fin"]

    dated = await index.search(
        "revenue",
        filters=SparseSearchFilter(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            chunking_config_fingerprint=first_fp,
        ),
    )
    assert [result.chunk.document_id for result in dated.results] == ["doc_filter_fin"]
    assert index.count(SparseSearchFilter(document_id="doc_filter_leg")) == 1


@pytest.mark.asyncio
async def test_empty_query_returns_empty_diagnostic_response() -> None:
    index = BM25SparseIndex.build(
        [_input("doc_empty_001", Domain.RESEARCH, ["retrieval evaluation evidence"])]
    )
    response = await index.search("   ")
    assert response.query_tokens == ()
    assert response.results == ()
    assert response.diagnostics == ()


def test_rebuild_fingerprint_is_independent_of_input_order() -> None:
    first = _input("doc_rebuild_001", Domain.FINANCIAL, ["Q3 revenue 12.5%"])
    second = _input("doc_rebuild_002", Domain.LEGAL, ["Section 2.1 fees"])
    forward = BM25SparseIndex.build([first, second])
    reverse = BM25SparseIndex.build([second, first])
    assert forward.snapshot.index_fingerprint == reverse.snapshot.index_fingerprint
    assert forward.snapshot.config_fingerprint == reverse.snapshot.config_fingerprint


def test_configuration_change_changes_sparse_index_identity() -> None:
    corpus = [_input("doc_config_001", Domain.RESEARCH, ["BM25 lexical retrieval"])]
    bm25 = BM25SparseIndex.build(corpus, config=SparseIndexConfig(variant=BM25Variant.BM25))
    plus = BM25SparseIndex.build(corpus, config=SparseIndexConfig(variant=BM25Variant.BM25_PLUS))
    assert bm25.snapshot.config_fingerprint != plus.snapshot.config_fingerprint
    assert bm25.snapshot.index_fingerprint != plus.snapshot.index_fingerprint


@pytest.mark.asyncio
async def test_snapshot_round_trip_preserves_results_and_integrity(tmp_path: Path) -> None:
    index = BM25SparseIndex.build(
        [_input("doc_save_001", Domain.FINANCIAL, ["10-K revenue margin 18.2%"])]
    )
    snapshot_path = tmp_path / "sparse-index.json"
    index.save(snapshot_path)
    restored = BM25SparseIndex.load(snapshot_path)
    original = await index.search("10-K 18.2%")
    loaded = await restored.search("10-K 18.2%")
    assert restored.snapshot.index_fingerprint == index.snapshot.index_fingerprint
    assert loaded.results == original.results
    assert loaded.query_tokens == ("10-k", "18.2%")


def test_snapshot_load_rejects_tampered_index_fingerprint(tmp_path: Path) -> None:
    index = BM25SparseIndex.build(
        [_input("doc_tamper_001", Domain.RESEARCH, ["RRF BM25+ retrieval"])]
    )
    snapshot_path = tmp_path / "sparse-index.json"
    index.save(snapshot_path)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["index_fingerprint"] = "0" * 64
    snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(IndexingError, match="index fingerprint"):
        BM25SparseIndex.load(snapshot_path)
