from __future__ import annotations

from collections.abc import Sequence

import pytest

from rageval.chunking import (
    ChunkingConfig,
    ChunkingEngine,
    ChunkStrategy,
    LocalHashEmbeddingProvider,
    reference_chunking_config,
    run_chunking_ablation,
)
from rageval.cleaning.models import CleanedDocument, CleaningStats
from rageval.models import DocumentElement, DocumentRecord, Domain, ElementType, SourceType


def _cleaned(
    domain: Domain,
    elements: tuple[DocumentElement, ...],
    *,
    document_id: str = "doc_chunk_fixture",
) -> CleanedDocument:
    record = DocumentRecord(
        document_id=document_id,
        source_uri=f"fixture://chunking/{domain.value}",
        source_type=SourceType.PDF,
        domain=domain,
        checksum_sha256="a" * 64,
    )
    normalized = tuple(
        element.model_copy(update={"document_id": document_id}) for element in elements
    )
    chars = sum(len(element.text) for element in normalized)
    return CleanedDocument(
        document=record,
        source_parser_name="chunking-test",
        source_parser_version="1.0",
        source_parser_config_fingerprint="b" * 64,
        cleaning_config_fingerprint="c" * 64,
        elements=normalized,
        stats=CleaningStats(
            elements_in=len(normalized),
            elements_out=len(normalized),
            duplicates_removed=0,
            boilerplate_removed=0,
            header_footer_removed=0,
            page_numbers_removed=0,
            ocr_elements=0,
            tables_preserved=sum(element.kind is ElementType.TABLE for element in normalized),
            characters_in=chars,
            characters_out=chars,
            characters_removed=0,
        ),
    )


def _text_element(
    element_id: str,
    text: str,
    *,
    page: int = 1,
    section_hint: str | None = None,
    kind: ElementType = ElementType.TEXT,
) -> DocumentElement:
    metadata: dict[str, object] = {"source_element_id": f"src_{element_id}"}
    if section_hint is not None:
        metadata["section_hint"] = section_hint
    return DocumentElement(
        element_id=element_id,
        document_id="doc_placeholder",
        kind=kind,
        text=text,
        page_number=page,
        metadata=metadata,
    )


@pytest.mark.parametrize(
    ("strategy", "size", "overlap"),
    [
        (ChunkStrategy.FIXED_256, 256, 32),
        (ChunkStrategy.FIXED_512, 512, 64),
        (ChunkStrategy.FIXED_1024, 1024, 128),
    ],
)
@pytest.mark.asyncio
async def test_reference_fixed_boundaries_and_overlap(
    strategy: ChunkStrategy,
    size: int,
    overlap: int,
) -> None:
    tokens = [f"t{index}" for index in range(size + 25)]
    document = _cleaned(
        Domain.RESEARCH,
        (_text_element("elm_fixed_01", " ".join(tokens)),),
    )
    result = await ChunkingEngine().chunk(
        document,
        config=reference_chunking_config(strategy),
    )

    assert len(result.chunks) == 2
    first = result.chunks[0]
    second = result.chunks[1]
    assert first.token_count == size
    assert first.text.split() == tokens[:size]
    assert second.text.split() == tokens[size - overlap :]
    assert second.metadata["overlap_tokens"] == overlap


class _ForcedEmbeddingProvider:
    name = "forced-split"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        assert len(texts) == 3
        return [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]


@pytest.mark.asyncio
async def test_semantic_chunker_uses_injected_embeddings_for_known_split() -> None:
    document = _cleaned(
        Domain.RESEARCH,
        (
            _text_element(
                "elm_sem_001",
                "Alpha evidence is related. Beta evidence is related. Gamma topic changes.",
            ),
        ),
    )
    config = ChunkingConfig(
        strategy=ChunkStrategy.SEMANTIC,
        chunk_size=32,
        overlap=0,
        semantic_min_tokens=1,
        semantic_max_tokens=32,
        semantic_similarity_threshold=0.5,
    )
    result = await ChunkingEngine(
        embedding_provider=_ForcedEmbeddingProvider(),
    ).chunk(document, config=config)

    assert [chunk.text for chunk in result.chunks] == [
        "Alpha evidence is related. Beta evidence is related.",
        "Gamma topic changes.",
    ]
    assert result.metadata["embedding_provider"] == "forced-split"


@pytest.mark.asyncio
async def test_semantic_chunking_requires_embedding_provider() -> None:
    document = _cleaned(
        Domain.RESEARCH,
        (_text_element("elm_sem_002", "One sentence. Another sentence."),),
    )
    with pytest.raises(ValueError, match="requires an embedding provider"):
        await ChunkingEngine().chunk(
            document,
            config=reference_chunking_config(ChunkStrategy.SEMANTIC),
        )


@pytest.mark.asyncio
async def test_table_aware_chunking_repeats_header_and_keeps_rows_whole() -> None:
    table = DocumentElement(
        element_id="elm_table_001",
        document_id="doc_placeholder",
        kind=ElementType.TABLE,
        text="Metric\tValue\nRevenue\t100\nMargin\t20%\nCash\t50",
        page_number=4,
        metadata={
            "source_element_id": "src_table_001",
            "table_html": "<table><tr><td>Metric</td><td>Value</td></tr></table>",
            "bbox": [1.0, 2.0, 3.0, 4.0],
            "source_offset": {"page_index": 3, "table_index": 0},
        },
    )
    document = _cleaned(Domain.FINANCIAL, (table,))
    config = ChunkingConfig(
        strategy=ChunkStrategy.FIXED_256,
        chunk_size=6,
        overlap=1,
    )
    result = await ChunkingEngine().chunk(document, config=config)

    assert len(result.chunks) == 2
    assert result.chunks[0].text == "Metric\tValue\nRevenue\t100\nMargin\t20%"
    assert result.chunks[1].text == "Metric\tValue\nCash\t50"
    assert result.chunks[1].metadata["repeated_header"] is True
    assert result.chunks[0].metadata["source_pages"] == [4]
    for chunk in result.chunks:
        assert chunk.metadata["table_row_group"] is True
        assert chunk.metadata["source_table_id"] == "src_table_001"
        assert chunk.metadata["source_table_html"] == table.metadata["table_html"]
        rows = chunk.text.splitlines()
        assert rows[0] == "Metric\tValue"
        assert all("\t" in row for row in rows[1:])


@pytest.mark.asyncio
async def test_small_table_stays_together() -> None:
    table = DocumentElement(
        element_id="elm_table_002",
        document_id="doc_placeholder",
        kind=ElementType.TABLE,
        text="Metric\tValue\nRevenue\t100",
        page_number=1,
        metadata={"source_element_id": "src_table_002"},
    )
    result = await ChunkingEngine().chunk(
        _cleaned(Domain.FINANCIAL, (table,)),
        config=ChunkingConfig(
            strategy=ChunkStrategy.FIXED_256,
            chunk_size=32,
            overlap=4,
        ),
    )
    assert len(result.chunks) == 1
    assert result.chunks[0].text == table.text
    assert result.chunks[0].metadata["table_row_start"] == 0


@pytest.mark.asyncio
async def test_legal_clause_boundary_is_preserved_when_practical() -> None:
    document = _cleaned(
        Domain.LEGAL,
        (
            _text_element("elm_legal_01", "2.1 Fees. Customer shall pay within 30 days."),
            _text_element("elm_legal_02", "2.2 Term. This Agreement lasts one year."),
        ),
    )
    result = await ChunkingEngine().chunk(
        document,
        config=ChunkingConfig(
            strategy=ChunkStrategy.FIXED_256,
            chunk_size=256,
            overlap=32,
        ),
    )
    assert len(result.chunks) == 2
    assert result.chunks[0].text.startswith("2.1 Fees.")
    assert result.chunks[1].text.startswith("2.2 Term.")


@pytest.mark.asyncio
async def test_section_hint_prevents_cross_section_merge() -> None:
    document = _cleaned(
        Domain.RESEARCH,
        (
            _text_element("elm_sec_001", "First section statement.", section_hint="Results"),
            _text_element("elm_sec_002", "Second section statement.", section_hint="Discussion"),
        ),
    )
    result = await ChunkingEngine().chunk(
        document,
        config=ChunkingConfig(
            strategy=ChunkStrategy.FIXED_256,
            chunk_size=256,
            overlap=32,
        ),
    )
    assert len(result.chunks) == 2


@pytest.mark.asyncio
async def test_no_source_token_loss_with_fixed_overlap() -> None:
    tokens = [f"unique{index}" for index in range(90)]
    document = _cleaned(
        Domain.RESEARCH,
        (_text_element("elm_loss_001", " ".join(tokens)),),
    )
    result = await ChunkingEngine().chunk(
        document,
        config=ChunkingConfig(
            strategy=ChunkStrategy.FIXED_256,
            chunk_size=20,
            overlap=5,
        ),
    )
    observed = {token for chunk in result.chunks for token in chunk.text.split()}
    assert observed == set(tokens)


@pytest.mark.asyncio
async def test_chunk_ids_and_config_fingerprints_are_deterministic() -> None:
    document = _cleaned(
        Domain.RESEARCH,
        (_text_element("elm_id_0001", "alpha beta gamma delta epsilon"),),
    )
    config = ChunkingConfig(
        strategy=ChunkStrategy.FIXED_256,
        chunk_size=3,
        overlap=1,
    )
    first = await ChunkingEngine().chunk(document, config=config)
    second = await ChunkingEngine().chunk(document, config=config)
    changed = await ChunkingEngine().chunk(
        document,
        config=config.model_copy(update={"overlap": 2}),
    )

    assert first.config_fingerprint == second.config_fingerprint
    assert [chunk.chunk_id for chunk in first.chunks] == [
        chunk.chunk_id for chunk in second.chunks
    ]
    assert changed.config_fingerprint != first.config_fingerprint
    assert changed.chunks[0].chunk_id != first.chunks[0].chunk_id


@pytest.mark.asyncio
async def test_ablation_report_is_machine_readable_and_has_full_provenance() -> None:
    documents = [
        _cleaned(
            Domain.FINANCIAL,
            (_text_element("elm_fin_0001", "Revenue increased by 10 percent."),),
            document_id="doc_fin_fixture",
        ),
        _cleaned(
            Domain.LEGAL,
            (_text_element("elm_leg_0001", "2.1 Fees. Payment is due in 30 days."),),
            document_id="doc_leg_fixture",
        ),
        _cleaned(
            Domain.RESEARCH,
            (_text_element("elm_res_0001", "Retrieval improved. Evaluation remained stable."),),
            document_id="doc_res_fixture",
        ),
    ]
    configs = tuple(reference_chunking_config(strategy) for strategy in ChunkStrategy)
    report = await run_chunking_ablation(
        documents,
        configs=configs,
        embedding_provider=LocalHashEmbeddingProvider(),
        metadata={"fixture": "unit"},
    )

    assert len(report.stats) == len(configs) * len(Domain)
    assert all(stat.provenance_coverage == 1.0 for stat in report.stats)
    assert all(stat.table_fragmentation_count == 0 for stat in report.stats)
    payload = report.model_dump_json()
    assert '"dataset_fingerprint"' in payload
    assert '"fixed_256"' in payload
    assert '"semantic"' in payload
