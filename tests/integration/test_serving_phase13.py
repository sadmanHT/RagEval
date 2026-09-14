from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "serving_fixture_report.py"


def test_phase13_serving_fixture_uses_real_local_qdrant_and_redis() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["authenticated_query"] is True
    assert payload["qdrant_ready"] is True
    assert payload["redis_ready"] is True
    assert payload["cache_hit"] is True
    assert payload["cache_invalidated_after_index_change"] is True
    assert payload["stream_final_citations"]
    assert payload["evaluation_job_status"] == "succeeded"
    assert payload["latest_job_id"]
    assert payload["evidence_label"] == "phase13-serving-fixture-mechanics-only"
