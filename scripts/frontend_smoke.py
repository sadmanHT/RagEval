#!/usr/bin/env python3
"""End-to-end smoke test for the Next.js console and its server-side backend proxy."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

WEB_URL = os.environ.get("RAGEVAL_WEB_URL", "http://127.0.0.1:3001").rstrip("/")


def _request(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> tuple[int, bytes]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(
        f"{WEB_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _wait(path: str, *, deadline_seconds: float = 120.0) -> bytes:
    deadline = time.monotonic() + deadline_seconds
    last_status = 0
    while time.monotonic() < deadline:
        try:
            last_status, body = _request(path)
            if last_status == 200:
                return body
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1.0)
    raise RuntimeError(f"timed out waiting for frontend path {path}; last_status={last_status}")


def main() -> None:
    html = _wait("/")
    page = html.decode("utf-8", errors="replace")
    if "RAG-Eval" not in page or "Grounded answers" not in page:
        raise RuntimeError("frontend page did not render the RAG-Eval console")

    health_body = _wait("/api/health")
    health = json.loads(health_body)
    if health.get("status") != "ok":
        raise RuntimeError(f"frontend health proxy is not ready: {health}")

    query_status, query_body = _request(
        "/api/query",
        method="POST",
        payload={
            "schema_version": "1.0",
            "question": "Verify the frontend proxy returns a grounded cited answer.",
            "domain": None,
            "filters": {},
            "top_k": 8,
            "options": {
                "use_cache": True,
                "include_retrieval_diagnostics": True,
                "stream": False,
            },
        },
    )
    if query_status != 200:
        raise RuntimeError(f"frontend query proxy failed with status {query_status}")
    query = json.loads(query_body)
    if not query.get("cited_chunk_ids") or query.get("insufficient_context") is True:
        raise RuntimeError("frontend query proxy did not return grounded citations")

    eval_status, eval_body = _request(
        "/api/evaluation/run",
        method="POST",
        payload={"schema_version": "1.0", "reason": "frontend-ci-smoke"},
    )
    if eval_status != 202:
        raise RuntimeError(f"frontend evaluation proxy failed with status {eval_status}")
    job_id = json.loads(eval_body)["job_id"]

    final_status = "queued"
    for _ in range(100):
        status_code, status_body = _request(f"/api/evaluation/jobs/{job_id}")
        if status_code != 200:
            raise RuntimeError(f"frontend evaluation status failed with status {status_code}")
        final_status = json.loads(status_body)["status"]
        if final_status == "succeeded":
            break
        if final_status == "failed":
            raise RuntimeError("frontend evaluation job failed")
        time.sleep(0.05)

    if final_status != "succeeded":
        raise RuntimeError(f"frontend evaluation job did not finish; status={final_status}")

    print(
        json.dumps(
            {
                "schema_version": "1.0",
                "frontend_rendered": True,
                "health_proxy": True,
                "query_proxy": True,
                "cited_chunk_ids": query["cited_chunk_ids"],
                "evaluation_proxy": True,
                "evaluation_job_status": final_status,
                "evidence_label": "frontend-container-mechanics-only",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
