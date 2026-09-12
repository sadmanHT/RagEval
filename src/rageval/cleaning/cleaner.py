"""Document cleaning pipeline from parsed elements to retrieval-ready normalized content."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from rageval.cleaning.models import (
    CleanedDocument,
    CleaningConfig,
    CleaningStats,
    RemovalEvidence,
    RemovalReason,
)
from rageval.cleaning.normalizer import (
    cleaning_config_fingerprint,
    is_page_number_pattern,
    normalize_text,
    repeated_pattern_signature,
    text_similarity,
)
from rageval.core.ids import stable_digest
from rageval.ingestion.models import ParsedDocument
from rageval.models.contracts import DocumentElement, ElementType


@dataclass(frozen=True)
class _PreparedElement:
    index: int
    source: DocumentElement
    text: str


@dataclass
class _DuplicateCluster:
    representative: _PreparedElement
    members: list[tuple[_PreparedElement, float]] = field(default_factory=list)
    pages: set[int] = field(default_factory=set)


def _clean_element_id(
    source: DocumentElement,
    *,
    normalized_text: str,
    config_fingerprint: str,
) -> str:
    digest = stable_digest(
        "clean",
        source.element_id,
        source.kind.value,
        normalized_text,
        config_fingerprint,
    )
    return f"elm_{digest[:32]}"


def _prepared_elements(parsed: ParsedDocument, config: CleaningConfig) -> list[_PreparedElement]:
    return [
        _PreparedElement(
            index=index,
            source=element,
            text=normalize_text(element.text, kind=element.kind, config=config),
        )
        for index, element in enumerate(parsed.elements)
    ]


def _repeated_header_footer_removals(
    prepared: list[_PreparedElement],
    config: CleaningConfig,
) -> dict[int, RemovalEvidence]:
    if not config.suppress_repeated_headers_footers:
        return {}

    groups: dict[tuple[ElementType, str], list[_PreparedElement]] = defaultdict(list)
    for item in prepared:
        if item.source.kind not in {ElementType.HEADER, ElementType.FOOTER} or not item.text:
            continue
        signature = repeated_pattern_signature(
            item.text,
            canonicalize_page_numbers=config.canonicalize_page_numbers,
        )
        if signature:
            groups[(item.source.kind, signature)].append(item)

    removals: dict[int, RemovalEvidence] = {}
    for (kind, signature), members in groups.items():
        pages = {item.source.page_number for item in members if item.source.page_number is not None}
        repeated = len(pages) >= config.repeated_pattern_min_pages
        if not pages:
            repeated = len(members) >= config.repeated_pattern_min_pages
        if not repeated:
            continue
        for item in members:
            if is_page_number_pattern(item.text):
                reason = RemovalReason.PAGE_NUMBER
            elif kind is ElementType.HEADER:
                reason = RemovalReason.REPEATED_HEADER
            else:
                reason = RemovalReason.REPEATED_FOOTER
            removals[item.index] = RemovalEvidence(
                source_element_id=item.source.element_id,
                reason=reason,
                page_number=item.source.page_number,
                pattern_signature=signature,
                original_text=item.source.text,
            )
    return removals


def _eligible_for_boilerplate(item: _PreparedElement, config: CleaningConfig) -> bool:
    if item.source.kind not in {ElementType.TEXT, ElementType.OCR_TEXT}:
        return False
    if item.source.page_number is None:
        return False
    return config.dedup_min_chars <= len(item.text) <= config.dedup_max_chars


def _duplicate_boilerplate_removals(
    prepared: list[_PreparedElement],
    config: CleaningConfig,
    already_removed: set[int],
) -> dict[int, RemovalEvidence]:
    if not config.deduplicate_boilerplate:
        return {}

    clusters: list[_DuplicateCluster] = []
    for item in prepared:
        if item.index in already_removed or not _eligible_for_boilerplate(item, config):
            continue
        best_cluster: _DuplicateCluster | None = None
        best_similarity = -1.0
        for cluster in clusters:
            similarity = text_similarity(item.text, cluster.representative.text)
            if similarity >= config.dedup_similarity_threshold and similarity > best_similarity:
                best_cluster = cluster
                best_similarity = similarity
        if best_cluster is None:
            cluster = _DuplicateCluster(representative=item)
            cluster.members.append((item, 1.0))
            if item.source.page_number is not None:
                cluster.pages.add(item.source.page_number)
            clusters.append(cluster)
        else:
            best_cluster.members.append((item, best_similarity))
            if item.source.page_number is not None:
                best_cluster.pages.add(item.source.page_number)

    removals: dict[int, RemovalEvidence] = {}
    for cluster in clusters:
        if len(cluster.pages) < config.dedup_min_pages:
            continue
        representative = cluster.representative
        for item, similarity in cluster.members[1:]:
            reason = (
                RemovalReason.DUPLICATE_BOILERPLATE
                if similarity == 1.0
                else RemovalReason.NEAR_DUPLICATE_BOILERPLATE
            )
            removals[item.index] = RemovalEvidence(
                source_element_id=item.source.element_id,
                reason=reason,
                page_number=item.source.page_number,
                matched_source_element_id=representative.source.element_id,
                similarity=similarity,
                original_text=item.source.text,
            )
    return removals


def clean_parsed_document(
    parsed: ParsedDocument,
    *,
    config: CleaningConfig | None = None,
) -> CleanedDocument:
    """Clean one parsed document while retaining source provenance and removal evidence."""
    effective_config = config or CleaningConfig()
    fingerprint = cleaning_config_fingerprint(effective_config)
    prepared = _prepared_elements(parsed, effective_config)

    removals_by_index = _repeated_header_footer_removals(prepared, effective_config)
    duplicate_removals = _duplicate_boilerplate_removals(
        prepared,
        effective_config,
        set(removals_by_index),
    )
    removals_by_index.update(duplicate_removals)

    cleaned: list[DocumentElement] = []
    for item in prepared:
        if item.index in removals_by_index:
            continue
        if not item.text and item.source.kind not in {ElementType.TABLE, ElementType.PAGE_BREAK}:
            removals_by_index[item.index] = RemovalEvidence(
                source_element_id=item.source.element_id,
                reason=RemovalReason.EMPTY_AFTER_NORMALIZATION,
                page_number=item.source.page_number,
                original_text=item.source.text,
            )
            continue

        metadata = dict(item.source.metadata)
        metadata.update(
            {
                "source_element_id": item.source.element_id,
                "source_parser_config_fingerprint": parsed.config_fingerprint,
                "cleaning_config_fingerprint": fingerprint,
                "normalization": {
                    "text_changed": item.text != item.source.text,
                    "characters_removed": max(0, len(item.source.text) - len(item.text)),
                },
            }
        )
        cleaned.append(
            DocumentElement(
                element_id=_clean_element_id(
                    item.source,
                    normalized_text=item.text,
                    config_fingerprint=fingerprint,
                ),
                document_id=item.source.document_id,
                kind=item.source.kind,
                text=item.text,
                page_number=item.source.page_number,
                metadata=metadata,
            )
        )

    ordered_removals = tuple(removals_by_index[index] for index in sorted(removals_by_index))
    duplicate_reasons = {
        RemovalReason.DUPLICATE_BOILERPLATE,
        RemovalReason.NEAR_DUPLICATE_BOILERPLATE,
    }
    header_footer_reasons = {
        RemovalReason.REPEATED_HEADER,
        RemovalReason.REPEATED_FOOTER,
        RemovalReason.PAGE_NUMBER,
    }
    characters_in = sum(len(item.source.text) for item in prepared)
    characters_out = sum(len(element.text) for element in cleaned)
    source_table_ids = {
        item.source.element_id for item in prepared if item.source.kind is ElementType.TABLE
    }
    retained_table_source_ids = {
        str(element.metadata["source_element_id"])
        for element in cleaned
        if element.kind is ElementType.TABLE
    }
    duplicate_count = sum(item.reason in duplicate_reasons for item in ordered_removals)
    header_footer_count = sum(item.reason in header_footer_reasons for item in ordered_removals)
    stats = CleaningStats(
        elements_in=len(prepared),
        elements_out=len(cleaned),
        duplicates_removed=duplicate_count,
        boilerplate_removed=duplicate_count + header_footer_count,
        header_footer_removed=header_footer_count,
        page_numbers_removed=sum(
            item.reason is RemovalReason.PAGE_NUMBER for item in ordered_removals
        ),
        ocr_elements=sum(
            item.source.kind is ElementType.OCR_TEXT for item in prepared
        ),
        tables_preserved=len(source_table_ids & retained_table_source_ids),
        characters_in=characters_in,
        characters_out=characters_out,
        characters_removed=max(0, characters_in - characters_out),
    )

    metadata = dict(parsed.metadata)
    metadata.update(
        {
            "cleaner_version": effective_config.cleaner_version,
            "source_used_ocr": parsed.used_ocr,
        }
    )
    return CleanedDocument(
        document=parsed.document,
        source_parser_name=parsed.parser_name,
        source_parser_version=parsed.parser_version,
        source_parser_config_fingerprint=parsed.config_fingerprint,
        cleaning_config_fingerprint=fingerprint,
        elements=tuple(cleaned),
        removals=ordered_removals,
        stats=stats,
        metadata=metadata,
    )
