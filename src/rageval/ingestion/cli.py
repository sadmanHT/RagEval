"""Debug CLI for parsing files or corpus subsets without indexing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rageval.core.errors import RagEvalError
from rageval.core.ids import make_document_id
from rageval.corpus.manifest import read_manifest, sha256_file
from rageval.corpus.models import DatasetSplit
from rageval.ingestion.loaders import parse_batch, parse_document
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import DocumentRecord, Domain, SourceType


def _source_type(path: Path) -> SourceType:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return SourceType.PDF
    if suffix == ".docx":
        return SourceType.DOCX
    if suffix in {".html", ".htm"}:
        return SourceType.HTML
    raise ValueError(f"unsupported file extension: {suffix!r}")


def _config(args: argparse.Namespace) -> ParserConfig:
    return ParserConfig(
        ocr_mode=OCRMode(args.ocr_mode),
        ocr_min_native_chars=args.ocr_min_native_chars,
        ocr_dpi=args.ocr_dpi,
        detect_tables=not args.no_tables,
    )


def _add_parser_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ocr-mode",
        choices=[mode.value for mode in OCRMode],
        default=OCRMode.FALLBACK.value,
    )
    parser.add_argument("--ocr-min-native-chars", type=int, default=20)
    parser.add_argument("--ocr-dpi", type=int, default=200)
    parser.add_argument("--no-tables", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rageval-parse")
    subparsers = parser.add_subparsers(dest="command", required=True)

    single = subparsers.add_parser("file", help="parse one source file into debug JSON")
    single.add_argument("path", type=Path)
    single.add_argument("--domain", choices=[domain.value for domain in Domain], required=True)
    single.add_argument("--output", type=Path, required=True)
    _add_parser_options(single)

    corpus = subparsers.add_parser("corpus", help="parse a filtered corpus manifest subset")
    corpus.add_argument("manifest", type=Path)
    corpus.add_argument("--root", type=Path, required=True)
    corpus.add_argument("--output-dir", type=Path, required=True)
    corpus.add_argument("--domain", choices=[domain.value for domain in Domain])
    corpus.add_argument("--split", choices=[split.value for split in DatasetSplit])
    corpus.add_argument("--max-failures", type=int, default=0)
    _add_parser_options(corpus)
    return parser


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = _config(args)
        if args.command == "file":
            path: Path = args.path
            source_type = _source_type(path)
            checksum = sha256_file(path)
            source_uri = f"file:///{path.name}"
            record = DocumentRecord(
                document_id=make_document_id(
                    checksum_sha256=checksum,
                    source_uri=source_uri,
                ),
                source_uri=source_uri,
                source_type=source_type,
                domain=Domain(args.domain),
                checksum_sha256=checksum,
            )
            parsed = parse_document(path, record, config=config)
            _write_json(args.output, parsed.model_dump(mode="json"))
            print(f"elements={len(parsed.elements)} ocr={parsed.used_ocr}")
            return 0

        manifest = read_manifest(args.manifest)
        selected = tuple(
            item
            for item in manifest.documents
            if (args.domain is None or item.record.domain is Domain(args.domain))
            and (args.split is None or item.split is DatasetSplit(args.split))
        )
        result = parse_batch(selected, args.root, config=config)
        output_dir: Path = args.output_dir
        for parsed in result.successes:
            _write_json(
                output_dir / f"{parsed.document.document_id}.json",
                parsed.model_dump(mode="json"),
            )
        _write_json(
            output_dir / "_failures.json",
            [failure.model_dump(mode="json") for failure in result.failures],
        )
        print(f"successes={len(result.successes)} failures={len(result.failures)}")
        return 2 if result.exceeds_failure_policy(max_failures=args.max_failures) else 0
    except (RagEvalError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
