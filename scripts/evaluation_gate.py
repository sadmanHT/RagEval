#!/usr/bin/env python3
"""Run the deterministic evaluation subset as a PR gate or scheduled alert-only check."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Policy floors are intentionally below the accepted deterministic fixture values. They are
# regression thresholds for mechanics evidence, not representative production-quality targets.
_MINIMUMS = {
    "context_precision": 0.80,
    "context_recall": 0.80,
    "faithfulness": 0.80,
    "answer_relevancy": 0.70,
}
_MAX_HALLUCINATION_RATE = 0.34
_MIN_FIXTURE_RECORDS = 3


def _run_fixture() -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluation_fixture_report.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("evaluation fixture report was not a JSON object")
    return payload


def _evaluate(payload: dict[str, object]) -> list[str]:
    failures: list[str] = []
    aggregates = payload.get("aggregates")
    if not isinstance(aggregates, dict):
        return ["evaluation fixture did not expose aggregate metrics"]

    for metric, minimum in _MINIMUMS.items():
        value = aggregates.get(metric)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            failures.append(f"missing numeric aggregate: {metric}")
        elif float(value) < minimum:
            failures.append(f"{metric}={float(value):.6f} below fixture floor={minimum:.6f}")

    records = payload.get("fixture_records")
    if not isinstance(records, int) or isinstance(records, bool) or records < _MIN_FIXTURE_RECORDS:
        failures.append(
            f"fixture_records={records!r} below required mechanics "
            f"sample count={_MIN_FIXTURE_RECORDS}"
        )

    hallucination = payload.get("hallucination")
    if not isinstance(hallucination, dict):
        failures.append("evaluation fixture did not expose hallucination arithmetic")
    else:
        rate = hallucination.get("rate")
        flagged = hallucination.get("flagged_count")
        total = hallucination.get("total_count")
        if not isinstance(rate, (int, float)) or isinstance(rate, bool):
            failures.append("hallucination rate is missing or non-numeric")
        elif float(rate) > _MAX_HALLUCINATION_RATE:
            failures.append(
                f"hallucination_rate={float(rate):.6f} above fixture "
                f"ceiling={_MAX_HALLUCINATION_RATE:.6f}"
            )
        if not isinstance(flagged, int) or not isinstance(total, int) or total <= 0:
            failures.append("hallucination count/denominator is invalid")
        elif abs(float(rate) - (flagged / total)) > 1e-12:
            failures.append("hallucination rate is inconsistent with flagged_count / total_count")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("pr", "nightly"), default="pr")
    args = parser.parse_args()

    payload = _run_fixture()
    failures = _evaluate(payload)
    report = {
        "schema_version": "1.0",
        "mode": args.mode,
        "blocking": args.mode == "pr",
        "target_dataset_supplied": payload.get("target_dataset_supplied"),
        "dataset_fingerprint": payload.get("dataset_fingerprint"),
        "run_fingerprint": payload.get("run_fingerprint"),
        "fixture_records": payload.get("fixture_records"),
        "aggregates": payload.get("aggregates"),
        "hallucination": payload.get("hallucination"),
        "violations": failures,
        "gate_failed": bool(failures) and args.mode == "pr",
        "alert_triggered": bool(failures) and args.mode == "nightly",
        "evidence_label": "phase14-fast-evaluation-fixture-gate-only",
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    if failures and args.mode == "nightly":
        warning = (
            "::warning::Scheduled deterministic evaluation fixture detected "
            "regression policy violations: "
        )
        print(warning + "; ".join(failures), file=sys.stderr)
    if failures and args.mode == "pr":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
