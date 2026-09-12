"""Qdrant-backed dense indexing and retrieval for canonical RAG-Eval chunks."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from rageval.core.errors import IndexingError, ProviderError, RetrievalError
from rageval.models.contracts import Chunk, DocumentRecord, RetrievalResult
from rageval.retrieval.dense.models import (
    DenseIndexConfig,
    DenseSearchFilter,
    DenseSearchResponse,
    IndexConsistencyReport,
    IndexMutationResult,
)
from rageval.retrieval.dense.providers import DenseEmbeddingProvider

_POINT_NAMESPACE = uuid.UUID("fd816fab-e063-44a8-82f1-799511840f14")


def point_id_for_chunk(chunk_id: str) -> str:
    """Map a stable project chunk ID to a Qdrant-compatible deterministic UUID."""
    return str(uuid.uuid5(_POINT_NAMESPACE, chunk_id))


def _document_filter(document_id: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=document_id),
            )
        ]
    )


def _search_filter(search_filter: DenseSearchFilter) -> models.Filter | None:
    conditions: list[models.Condition] = []
    if search_filter.domain is not None:
        conditions.append(
            models.FieldCondition(
                key="domain",
                match=models.MatchValue(value=search_filter.domain.value),
            )
        )
    if search_filter.document_id is not None:
        conditions.append(
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=search_filter.document_id),
            )
        )
    if search_filter.chunking_config_fingerprint is not None:
        conditions.append(
            models.FieldCondition(
                key="chunking_config_fingerprint",
                match=models.MatchValue(value=search_filter.chunking_config_fingerprint),
            )
        )
    if search_filter.date_from is not None or search_filter.date_to is not None:
        conditions.append(
            models.FieldCondition(
                key="source_date_ordinal",
                range=models.Range(
                    gte=(search_filter.date_from.toordinal() if search_filter.date_from else None),
                    lte=(search_filter.date_to.toordinal() if search_filter.date_to else None),
                ),
            )
        )
    return models.Filter(must=conditions) if conditions else None


def _batched[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def _payload(
    *,
    chunk: Chunk,
    document: DocumentRecord,
    source_date: date | None,
    provider: DenseEmbeddingProvider,
    config: DenseIndexConfig,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "domain": document.domain.value,
        "source_type": document.source_type.value,
        "source_uri": document.source_uri,
        "checksum_sha256": document.checksum_sha256,
        "chunking_config_fingerprint": chunk.config_fingerprint,
        "embedding_provider": provider.name,
        "embedding_model": provider.model,
        "embedding_dimension": provider.dimension,
        "collection_version": config.collection_version,
        "chunk": chunk.model_dump(mode="json"),
    }
    if source_date is not None:
        payload["source_date"] = source_date.isoformat()
        payload["source_date_ordinal"] = source_date.toordinal()
    return payload


class QdrantDenseIndex:
    """Versioned dense index over a Qdrant collection."""

    def __init__(
        self,
        *,
        provider: DenseEmbeddingProvider,
        config: DenseIndexConfig,
        url: str = "http://localhost:6333",
        client: AsyncQdrantClient | None = None,
    ) -> None:
        if config.vector_size != provider.dimension:
            raise ValueError(
                "DenseIndexConfig.vector_size must match the embedding provider dimension"
            )
        self.provider = provider
        self.config = config
        self._owns_client = client is None
        self.client = client or AsyncQdrantClient(url=url, timeout=config.timeout_seconds)

    async def aclose(self) -> None:
        """Close the internally owned Qdrant client."""
        if self._owns_client:
            await self.client.close()

    async def ensure_collection(self) -> None:
        """Create or validate the versioned collection and required payload indexes."""
        try:
            exists = await self.client.collection_exists(self.config.collection_name)
            if not exists:
                await self.client.create_collection(
                    collection_name=self.config.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.config.vector_size,
                        distance=models.Distance.COSINE,
                    ),
                    hnsw_config=models.HnswConfigDiff(
                        m=self.config.hnsw_m,
                        ef_construct=self.config.hnsw_ef_construct,
                    ),
                )
            info = await self.client.get_collection(self.config.collection_name)
            self._validate_collection_schema(info)
            payload_schema = getattr(info, "payload_schema", {}) or {}
            required_indexes = {
                "domain": models.PayloadSchemaType.KEYWORD,
                "document_id": models.PayloadSchemaType.KEYWORD,
                "source_date_ordinal": models.PayloadSchemaType.INTEGER,
                "chunking_config_fingerprint": models.PayloadSchemaType.KEYWORD,
            }
            for field_name, schema_type in required_indexes.items():
                if field_name not in payload_schema:
                    await self.client.create_payload_index(
                        collection_name=self.config.collection_name,
                        field_name=field_name,
                        field_schema=schema_type,
                        wait=True,
                    )
        except IndexingError:
            raise
        except Exception as exc:
            raise IndexingError(
                f"cannot ensure Qdrant collection {self.config.collection_name!r}: {exc}"
            ) from exc

    def _validate_collection_schema(self, info: Any) -> None:
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):
            raise IndexingError(
                "dense collection uses named vectors but Phase 6 expects one unnamed vector; "
                "bump collection_version or rebuild the collection"
            )
        actual_size = int(vectors.size)
        actual_distance = vectors.distance
        if actual_size != self.config.vector_size or actual_distance != models.Distance.COSINE:
            raise IndexingError(
                "stale Qdrant collection schema: expected "
                f"size={self.config.vector_size}, distance=Cosine; got "
                f"size={actual_size}, distance={actual_distance}. "
                "Bump collection_version or delete/rebuild the collection."
            )

    async def upsert_document(
        self,
        document: DocumentRecord,
        chunks: Sequence[Chunk],
        *,
        source_date: date | None = None,
    ) -> IndexMutationResult:
        """Embed and idempotently upsert all supplied chunks for one document."""
        if any(chunk.document_id != document.document_id for chunk in chunks):
            raise IndexingError("all chunks must belong to the supplied document")
        await self.ensure_collection()
        texts = [chunk.text for chunk in chunks]
        vectors: list[list[float]] = []
        try:
            for batch in _batched(texts, self.config.embed_batch_size):
                embedded = await self.provider.embed(batch)
                if len(embedded) != len(batch):
                    raise ProviderError("embedding provider returned the wrong number of vectors")
                for vector in embedded:
                    if len(vector) != self.config.vector_size:
                        raise ProviderError(
                            "embedding provider dimension mismatch: "
                            f"expected {self.config.vector_size}, got {len(vector)}"
                        )
                vectors.extend(embedded)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"embedding provider failed during indexing: {exc}") from exc

        points = [
            models.PointStruct(
                id=point_id_for_chunk(chunk.chunk_id),
                vector=vector,
                payload=_payload(
                    chunk=chunk,
                    document=document,
                    source_date=source_date,
                    provider=self.provider,
                    config=self.config,
                ),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            for batch in _batched(points, self.config.upsert_batch_size):
                await self.client.upsert(
                    collection_name=self.config.collection_name,
                    points=batch,
                    wait=True,
                )
        except Exception as exc:
            raise IndexingError(f"Qdrant upsert failed: {exc}") from exc
        return IndexMutationResult(
            collection_name=self.config.collection_name,
            document_id=document.document_id,
            chunk_count=len(chunks),
            operation="upsert",
        )

    async def delete_document(self, document_id: str) -> IndexMutationResult:
        """Delete every indexed chunk for one document."""
        await self.ensure_collection()
        before = await self._document_chunk_ids(document_id)
        try:
            await self.client.delete(
                collection_name=self.config.collection_name,
                points_selector=models.FilterSelector(filter=_document_filter(document_id)),
                wait=True,
            )
        except Exception as exc:
            raise IndexingError(f"Qdrant document delete failed: {exc}") from exc
        return IndexMutationResult(
            collection_name=self.config.collection_name,
            document_id=document_id,
            chunk_count=len(before),
            operation="delete",
        )

    async def replace_document(
        self,
        document: DocumentRecord,
        chunks: Sequence[Chunk],
        *,
        source_date: date | None = None,
    ) -> IndexMutationResult:
        """Atomically-at-the-API-boundary replace one document's indexed chunk set."""
        await self.delete_document(document.document_id)
        result = await self.upsert_document(document, chunks, source_date=source_date)
        return result.model_copy(update={"operation": "replace"})

    async def _document_chunk_ids(self, document_id: str) -> tuple[str, ...]:
        try:
            records: list[Any] = []
            offset: Any = None
            while True:
                page, offset = await self.client.scroll(
                    collection_name=self.config.collection_name,
                    scroll_filter=_document_filter(document_id),
                    limit=256,
                    offset=offset,
                    with_payload=["chunk_id"],
                    with_vectors=False,
                )
                records.extend(page)
                if offset is None:
                    break
            chunk_ids = [
                record.payload.get("chunk_id")
                for record in records
                if isinstance(record.payload, dict)
                and isinstance(record.payload.get("chunk_id"), str)
            ]
            return tuple(sorted(chunk_ids))
        except Exception as exc:
            raise IndexingError(f"Qdrant consistency read failed: {exc}") from exc

    async def check_document_consistency(
        self,
        document_id: str,
        expected_chunks: Sequence[Chunk],
    ) -> IndexConsistencyReport:
        """Compare exact expected chunk IDs with the indexed document chunk IDs."""
        await self.ensure_collection()
        expected = tuple(sorted(chunk.chunk_id for chunk in expected_chunks))
        indexed = await self._document_chunk_ids(document_id)
        expected_set = set(expected)
        indexed_set = set(indexed)
        missing = tuple(sorted(expected_set - indexed_set))
        extra = tuple(sorted(indexed_set - expected_set))
        return IndexConsistencyReport(
            collection_name=self.config.collection_name,
            document_id=document_id,
            expected_chunk_ids=expected,
            indexed_chunk_ids=indexed,
            missing_chunk_ids=missing,
            extra_chunk_ids=extra,
            consistent=not missing and not extra,
        )

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filters: DenseSearchFilter | None = None,
    ) -> DenseSearchResponse:
        """Embed a query, search Qdrant, and reconstruct canonical retrieval results."""
        if not query.strip():
            raise ValueError("query must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        await self.ensure_collection()
        active_filters = filters or DenseSearchFilter()
        total_start = time.perf_counter()
        embed_start = time.perf_counter()
        try:
            vectors = await self.provider.embed([query])
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"embedding provider failed during query: {exc}") from exc
        embedding_latency_ms = (time.perf_counter() - embed_start) * 1000.0
        if len(vectors) != 1 or len(vectors[0]) != self.config.vector_size:
            raise ProviderError("query embedding has an unexpected count or dimension")

        qdrant_start = time.perf_counter()
        try:
            scored = await self.client.search(
                collection_name=self.config.collection_name,
                query_vector=vectors[0],
                query_filter=_search_filter(active_filters),
                search_params=models.SearchParams(
                    hnsw_ef=self.config.search_hnsw_ef,
                    exact=self.config.exact_search,
                ),
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise RetrievalError(f"Qdrant dense search failed: {exc}") from exc
        qdrant_latency_ms = (time.perf_counter() - qdrant_start) * 1000.0

        reconstructed: list[tuple[float, str, Chunk, dict[str, object]]] = []
        for point in scored:
            payload = point.payload
            if not isinstance(payload, dict):
                raise RetrievalError("Qdrant result is missing a payload object")
            raw_chunk = payload.get("chunk")
            if not isinstance(raw_chunk, dict):
                raise RetrievalError("Qdrant result cannot reconstruct its canonical chunk")
            chunk = Chunk.model_validate(raw_chunk)
            reconstructed.append(
                (
                    float(point.score),
                    chunk.chunk_id,
                    chunk,
                    {
                        "qdrant_point_id": str(point.id),
                        "embedding_provider": payload.get("embedding_provider"),
                        "embedding_model": payload.get("embedding_model"),
                        "collection_version": payload.get("collection_version"),
                    },
                )
            )
        reconstructed.sort(key=lambda item: (-item[0], item[1]))
        results = tuple(
            RetrievalResult(
                chunk=chunk,
                score=score,
                rank=rank,
                retriever="dense-qdrant",
                metadata=metadata,
            )
            for rank, (score, _, chunk, metadata) in enumerate(reconstructed, start=1)
        )
        total_latency_ms = (time.perf_counter() - total_start) * 1000.0
        return DenseSearchResponse(
            query=query,
            results=results,
            collection_name=self.config.collection_name,
            provider=self.provider.name,
            model=self.provider.model,
            total_latency_ms=total_latency_ms,
            embedding_latency_ms=embedding_latency_ms,
            qdrant_latency_ms=qdrant_latency_ms,
            filters=active_filters,
        )
