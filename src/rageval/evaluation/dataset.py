"""Deterministic fingerprints for held-out evaluation records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from rageval.corpus.models import EvaluationDatasetRecord


def fingerprint_evaluation_records(records: Sequence[EvaluationDatasetRecord]) -> str:
    """Fingerprint reviewed evaluation data independently of file/list ordering."""

    keyed: list[tuple[str, dict[str, object]]] = []
    for record in records:
        keyed.append(
            (
                record.example.example_id,
                {
                    "example": record.example.model_dump(mode="json"),
                    "split": record.split.value,
                    "supporting_document_ids": sorted(record.supporting_document_ids),
                    "corpus_fingerprint": record.corpus_fingerprint,
                },
            )
        )
    canonical = [payload for _, payload in sorted(keyed, key=lambda item: item[0])]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
