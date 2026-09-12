"""CLI for parsing, cleaning, and chunking one source without indexing."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from rageval.cleaning import clean_parsed_document
from rageval.core.errors import RagEvalError
from rageval.core.ids import make_document_id
from rageval.corpus.manifest import sha256_file
from rageval.ingestion.loaders import parse_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import DocumentRecord, Domain, SourceType

from rageval.chunking.engine import ChunkingEngine
from rageval.chunking.models import (
    ChunkingConfig,
    ChunkStrategy,
    reference_chunking_config,
)
from rageval.chunking.providers import LocalHashEmbeddingProvider


def _source_type(path: Path) -> SourceType:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return SourceType.PDF
    if suffix == ".docx":
        return SourceType.DOCX
    if suffix in {".html", ".htm"}:
        return SourceType.HTML
    raise ValueError(f"unsupported file extension: {suffix!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rageval-chunk")
    parser.add_argument("path", type=Path)
    parser.add_argument("--domain", choices=[domain.value for domain in Domain], required=True)
    parser.add_argument(
        "--strategy",
        choices=[strategy.value for strategy in ChunkStrategy],
        default=ChunkStrategy.FIXED_512.value,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int)
    parser.add_argument("--overlap", type=int)
    parser.add_argument("--semantic-threshold", type=float)
    parser.add_argument("--semantic-min-tokens", type=int)
    parser.add_argument("--semantic-max-tokens", type=int)
    parser.add_argument("--no-table-aware", action="store_true")
    parser.add_argument("--no-section-aware", action="store_true")
    parser.add_argument(
        "--ocr-mode",
        choices=[mode.value for mode in OCRMode],
        default=OCRMode.FALLBACK.value,
    )
    parser.add_argument("--ocr-min-native-chars", type=int, default=20)
    parser.add_argument("--ocr-dpi", type=int, default=200)
    return parser


def _chunking_config(args: argparse.Namespace) -> ChunkingConfig:
    base = reference_chunking_config(ChunkStrategy(args.strategy))
    values = base.model_dump()
    if args.chunk_size is not None:
        values["chunk_size"] = args.chunk_size
    if args.overlap is not None:
        values["overlap"] = args.overlap
    if args.semantic_threshold is not None:
        values["semantic_similarity_threshold"] = args.semantic_threshold
    if args.semantic_min_tokens is not None:
        values["semantic_min_tokens"] = args.semantic_min_tokens
    if args.semantic_max_tokens is not None:
        values["semantic_max_tokens"] = args.semantic_max_tokens
    values["table_aware"] = not args.no_table_aware
    values["section_aware"] = not args.no_section_aware
    return ChunkingConfig.model_validate(values)


async def _run(args: argparse.Namespace) -> int:
    path: Path = args.path
    source_type = _source_type(path)
    checksum = sha256_file(path)
    source_uri = f"file:///{path.name}"
    record = DocumentRecord(
        document_id=make_document_id(checksum_sha256=checksum, source_uri=source_uri),
        source_uri=source_uri,
        source_type=source_type,
        domain=Domain(args.domain),
        checksum_sha256=checksum,
    )
    parsed = parse_document(
        path,
        record,
        config=ParserConfig(
            ocr_mode=OCRMode(args.ocr_mode),
            ocr_min_native_chars=args.ocr_min_native_chars,
            ocr_dpi=args.ocr_dpi,
            detect_tables=True,
        ),
    )
    cleaned = clean_parsed_document(parsed)
    config = _chunking_config(args)
    embedding_provider = (
        LocalHashEmbeddingProvider() if config.strategy is ChunkStrategy.SEMANTIC else None
    )
    result = await ChunkingEngine(embedding_provider=embedding_provider).chunk(
        cleaned,
        config=config,
    )
    output: Path = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        f"strategy={config.strategy.value} chunks={len(result.chunks)} "
        f"config={result.config_fingerprint[:12]}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (RagEvalError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
