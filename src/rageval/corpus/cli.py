"""CLI for corpus discovery, validation, and fingerprint inspection."""

from __future__ import annotations

import argparse
from pathlib import Path

from rageval.core.errors import RagEvalError
from rageval.corpus.manifest import (
    read_manifest,
    scan_corpus,
    validate_manifest_files,
    write_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rageval-corpus")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="discover a corpus and write a manifest")
    scan.add_argument("root", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--fail-on-unsupported", action="store_true")

    validate = subparsers.add_parser("validate", help="validate a manifest and source files")
    validate.add_argument("manifest", type=Path)
    validate.add_argument("--root", type=Path, required=True)

    fingerprint = subparsers.add_parser("fingerprint", help="print the stored verified fingerprint")
    fingerprint.add_argument("manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            report = scan_corpus(args.root, fail_on_unsupported=args.fail_on_unsupported)
            write_manifest(report.manifest, args.output)
            print(f"documents={len(report.manifest.documents)}")
            print(f"duplicates={len(report.manifest.duplicates)}")
            print(f"unsupported={len(report.unsupported_paths)}")
            print(f"fingerprint={report.manifest.fingerprint}")
            return 0
        if args.command == "validate":
            manifest = read_manifest(args.manifest)
            validate_manifest_files(manifest, args.root)
            print(f"valid fingerprint={manifest.fingerprint}")
            return 0
        if args.command == "fingerprint":
            manifest = read_manifest(args.manifest)
            print(manifest.fingerprint)
            return 0
    except RagEvalError as exc:
        print(f"error: {exc}")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
