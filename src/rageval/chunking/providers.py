"""Local deterministic embedding baseline for chunking diagnostics and fixture ablations."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence


class LocalHashEmbeddingProvider:
    """Dependency-free hashed bag-of-words embeddings for offline chunking mechanics.

    This adapter is deterministic and useful for tests/fixture ablations. It is not presented as
    evidence that a learned semantic embedding model has been evaluated.
    """

    name = "local-hash-embedding-v1"

    def __init__(self, *, dimensions: int = 64) -> None:
        if dimensions < 4:
            raise ValueError("dimensions must be at least 4")
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in text.casefold().split():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:2], "big") % self.dimensions
                sign = 1.0 if digest[2] % 2 == 0 else -1.0
                vector[bucket] += sign
            norm = math.sqrt(sum(value * value for value in vector))
            if norm:
                vector = [value / norm for value in vector]
            vectors.append(vector)
        return vectors
