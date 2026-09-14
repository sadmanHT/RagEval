from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "evaluation_ablation_fixture_report.py"


def test_phase12_fixture_ablation_recomputes_distinct_configuration_reports() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["target_dataset_supplied"] is False
    assert payload["fixture_records"] == 3
    assert payload["configuration_count"] == 5
    assert payload["tracker_events"] == 5
    assert payload["local_report_formats"] == ["html", "json", "markdown"]

    configurations = payload["configurations"]
    assert len({item["run_id"] for item in configurations}) == 5
    assert len({item["config_fingerprint"] for item in configurations}) == 5
    assert {item["chunking"] for item in configurations} == {
        "fixed_256",
        "fixed_512",
        "fixed_1024",
        "semantic",
        "table_aware",
    }
    for item in configurations:
        assert all(metric["count"] == 3 for metric in item["overall"].values())
