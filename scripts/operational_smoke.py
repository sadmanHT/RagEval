#!/usr/bin/env python3
"""End-to-end Phase 14 operational smoke against the Compose stack."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

API_URL = os.environ.get("RAGEVAL_SMOKE_API_URL", "http://127.0.0.1:8000").rstrip("/")
PROMETHEUS_URL = os.environ.get(
    "RAGEVAL_SMOKE_PROMETHEUS_URL", "http://127.0.0.1:9090"
).rstrip("/")
GRAFANA_URL = os.environ.get("RAGEVAL_SMOKE_GRAFANA_URL", "http://127.0.0.1:3000").rstrip("/")
API_KEY = os.environ.get("RAGEVAL_SERVING_API_KEY", "local-compose-change-me")


def _request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    api_key: bool = False,
) -> tuple[int, bytes]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if api_key:
        headers["X-API-Key"] = API_KEY
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _wait(url: str, *, expected: int = 200, deadline_seconds: float = 120.0) -> bytes:
    deadline = time.monotonic() + deadline_seconds
    last_status = 0
    while time.monotonic() < deadline:
        try:
            last_status, body = _request(url)
            if last_status == expected:
                return body
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1.0)
    raise RuntimeError(f"timed out waiting for operational endpoint; last_status={last_status}")


def _wait_for_prometheus_scrape(deadline_seconds: float = 60.0) -> None:
    expression = urllib.parse.quote('up{job="rageval-api"}')
    url = f"{PROMETHEUS_URL}/api/v1/query?query={expression}"
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        try:
            status, body = _request(url)
            if status == 200:
                payload = json.loads(body)
                results = payload.get("data", {}).get("result", [])
                if results and results[0].get("value", [None, "0"])[1] == "1":
                    return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(1.0)
    raise RuntimeError("Prometheus never reported rageval-api up=1")


def main() -> None:
    _wait(f"{API_URL}/health/ready")
    status, query_body = _request(
        f"{API_URL}/query",
        method="POST",
        payload={"question": "Verify the Phase 14 containerized serving boundary."},
        api_key=True,
    )
    if status != 200:
        raise RuntimeError(f"operational query failed with status {status}")
    query = json.loads(query_body)
    cited = query.get("cited_chunk_ids", [])
    if not cited or query.get("insufficient_context") is True:
        raise RuntimeError("operational query did not return a grounded cited fixture answer")

    status, created_body = _request(
        f"{API_URL}/eval/run",
        method="POST",
        payload={"reason": "phase14-operational-smoke"},
        api_key=True,
    )
    if status != 202:
        raise RuntimeError(f"evaluation job creation failed with status {status}")
    job_id = json.loads(created_body)["job_id"]
    job_status = "queued"
    for _ in range(100):
        status, body = _request(f"{API_URL}/eval/jobs/{job_id}", api_key=True)
        if status != 200:
            raise RuntimeError(f"evaluation status failed with status {status}")
        job_status = json.loads(body)["status"]
        if job_status == "succeeded":
            break
        time.sleep(0.05)
    if job_status != "succeeded":
        raise RuntimeError(f"evaluation job did not succeed; status={job_status}")

    status, metrics_body = _request(f"{API_URL}/metrics")
    metrics_text = metrics_body.decode("utf-8", errors="replace")
    if status != 200 or "rageval_http_requests_total" not in metrics_text:
        raise RuntimeError("Prometheus metrics endpoint is missing HTTP request metrics")
    if "rageval_evaluation_jobs_total" not in metrics_text:
        raise RuntimeError("Prometheus metrics endpoint is missing evaluation job metrics")

    _wait(f"{PROMETHEUS_URL}/-/ready")
    _wait_for_prometheus_scrape()
    grafana_body = _wait(f"{GRAFANA_URL}/api/health")
    grafana = json.loads(grafana_body)
    if grafana.get("database") != "ok":
        raise RuntimeError("Grafana health did not report database=ok")

    print(
        json.dumps(
            {
                "schema_version": "1.0",
                "api_ready": True,
                "authenticated_query": True,
                "cited_chunk_ids": cited,
                "evaluation_job_status": job_status,
                "metrics_endpoint": True,
                "prometheus_scrape_up": True,
                "grafana_database": grafana["database"],
                "evidence_label": "phase14-container-operational-mechanics-only",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    import urllib.parse

    main()
