"""CLI for validating, fingerprinting, and exporting held-out evaluation datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rageval.corpus.manifest import read_manifest
from rageval.evaluation.dataset import (
    export_review_csv,
    fingerprint_evaluation_records,
    load_evaluation_jsonl,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rageval.evaluation.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("dataset", type=Path)
    validate.add_argument("--manifest", type=Path)

    fingerprint = subparsers.add_parser("fingerprint")
    fingerprint.add_argument("dataset", type=Path)

    review = subparsers.add_parser("export-review")
    review.add_argument("dataset", type=Path)
    review.add_argument("output", type=Path)

    return parser


def main() -> None:
    args = _parser().parse_args()
    dataset_path = Path(args.dataset)

    if args.command == "validate":
        manifest_path = getattr(args, "manifest", None)
        manifest = read_manifest(Path(manifest_path)) if manifest_path is not None else None
        records = load_evaluation_jsonl(dataset_path, manifest=manifest)
        print(
            json.dumps(
                {
                    "records": len(records),
                    "dataset_fingerprint": fingerprint_evaluation_records(records),
                    "manifest_validated": manifest is not None,
                },
                sort_keys=True,
            )
        )
        return

    records = load_evaluation_jsonl(dataset_path)
    if args.command == "fingerprint":
        print(fingerprint_evaluation_records(records))
        return

    output = Path(args.output)
    export_review_csv(records, output)
    print(output)


if __name__ == "__main__":
    main()
