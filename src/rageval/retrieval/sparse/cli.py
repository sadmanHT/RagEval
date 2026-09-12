"""Diagnostic CLI for persisted Phase 7 BM25/BM25+ indexes."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path

from rageval.models.contracts import Domain
from rageval.retrieval.sparse import BM25SparseIndex, SparseSearchFilter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query a persisted RAG-Eval sparse index")
    parser.add_argument("snapshot", type=Path, help="Sparse index snapshot JSON")
    parser.add_argument("query", help="Lexical query")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--domain", choices=[domain.value for domain in Domain])
    parser.add_argument("--document-id")
    parser.add_argument("--date-from", type=date.fromisoformat)
    parser.add_argument("--date-to", type=date.fromisoformat)
    parser.add_argument("--chunking-config-fingerprint")
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    index = BM25SparseIndex.load(args.snapshot)
    filters = SparseSearchFilter(
        domain=Domain(args.domain) if args.domain else None,
        document_id=args.document_id,
        date_from=args.date_from,
        date_to=args.date_to,
        chunking_config_fingerprint=args.chunking_config_fingerprint,
    )
    response = await index.search(args.query, top_k=args.top_k, filters=filters)
    return response.model_dump(mode="json")


def main() -> None:
    args = _parser().parse_args()
    print(json.dumps(asyncio.run(_run(args)), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
