"""Human- and machine-readable Phase 12 comparative evaluation reports."""

from __future__ import annotations

import asyncio
import html
import json
from collections import Counter
from pathlib import Path

from rageval.evaluation.run_models import ComparativeEvaluationReport, ConfigurationRun


def report_json(report: ComparativeEvaluationReport) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )


def _scope_label(run_slice_domain: object) -> str:
    if run_slice_domain is None:
        return "overall"
    return str(getattr(run_slice_domain, "value", run_slice_domain))


def render_markdown(report: ComparativeEvaluationReport) -> str:
    lines = [
        "# Comparative Evaluation Report",
        "",
        f"Evidence label: `{report.evidence_label}`",
        f"Dataset fingerprint: `{report.dataset_fingerprint}`",
        f"Matrix fingerprint: `{report.matrix_fingerprint}`",
        "",
        (
            "> Metric rows include sample counts. Small fixture differences must not be "
            "treated as representative quality improvements."
        ),
        "",
    ]
    for run in report.runs:
        lines.extend(_run_markdown(run))
    return "\n".join(lines).rstrip() + "\n"


def _run_markdown(run: ConfigurationRun) -> list[str]:
    lines = [
        f"## {run.config.config_id}",
        "",
        f"Run ID: `{run.run_id}`",
        f"Configuration fingerprint: `{run.config_fingerprint}`",
        f"Pipeline: `{run.config.retrieval_pipeline.value}`",
        f"Chunking: `{run.config.chunking_strategy.value}`",
        f"Query expansion: `{run.config.query_expansion}`",
        f"Multi-hop: `{run.config.multi_hop}`",
        f"Resumed examples: **{run.resumed_examples}**",
        f"Produced examples: **{run.produced_examples}**",
        "",
        "| Scope | Metric | N | Mean |",
        "| --- | --- | ---: | ---: |",
    ]
    for item in run.metric_slices:
        lines.append(
            f"| {_scope_label(item.domain)} | {item.metric} | {item.count} | "
            f"{item.mean_score:.6f} |"
        )
    lines.extend(["", "### Failure taxonomy", ""])
    counts = Counter(category.value for failure in run.failures for category in failure.categories)
    if not counts:
        lines.append("No classified failures in this run.")
    else:
        lines.extend(["| Category | Count |", "| --- | ---: |"])
        for category, count in sorted(counts.items()):
            lines.append(f"| {category} | {count} |")
    lines.append("")
    return lines


def render_html(report: ComparativeEvaluationReport) -> str:
    body: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<title>Comparative Evaluation Report</title></head><body>",
        "<h1>Comparative Evaluation Report</h1>",
        f"<p>Evidence label: <code>{html.escape(report.evidence_label)}</code></p>",
        (
            "<p>Dataset fingerprint: "
            f"<code>{html.escape(report.dataset_fingerprint)}</code></p>"
        ),
        (
            "<p>Matrix fingerprint: "
            f"<code>{html.escape(report.matrix_fingerprint)}</code></p>"
        ),
        (
            "<p><strong>Interpretation:</strong> metric rows include sample counts; "
            "tiny fixture differences are not representative quality evidence.</p>"
        ),
    ]
    for run in report.runs:
        body.extend(_run_html(run))
    body.append("</body></html>\n")
    return "\n".join(body)


def _run_html(run: ConfigurationRun) -> list[str]:
    lines = [
        f"<h2>{html.escape(run.config.config_id)}</h2>",
        "<ul>",
        f"<li>Run ID: <code>{run.run_id}</code></li>",
        f"<li>Pipeline: <code>{html.escape(run.config.retrieval_pipeline.value)}</code></li>",
        f"<li>Chunking: <code>{html.escape(run.config.chunking_strategy.value)}</code></li>",
        f"<li>Query expansion: {run.config.query_expansion}</li>",
        f"<li>Multi-hop: {run.config.multi_hop}</li>",
        f"<li>Resumed examples: {run.resumed_examples}</li>",
        f"<li>Produced examples: {run.produced_examples}</li>",
        "</ul>",
        "<table><thead><tr><th>Scope</th><th>Metric</th><th>N</th><th>Mean</th></tr></thead>",
        "<tbody>",
    ]
    for item in run.metric_slices:
        lines.append(
            "<tr>"
            f"<td>{html.escape(_scope_label(item.domain))}</td>"
            f"<td>{html.escape(item.metric)}</td>"
            f"<td>{item.count}</td>"
            f"<td>{item.mean_score:.6f}</td>"
            "</tr>"
        )
    lines.extend(["</tbody></table>", "<h3>Failure taxonomy</h3>"])
    counts = Counter(category.value for failure in run.failures for category in failure.categories)
    if not counts:
        lines.append("<p>No classified failures in this run.</p>")
    else:
        lines.append("<ul>")
        for category, count in sorted(counts.items()):
            lines.append(f"<li>{html.escape(category)}: {count}</li>")
        lines.append("</ul>")
    return lines


async def write_comparative_reports(
    report: ComparativeEvaluationReport,
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    """Persist JSON, Markdown, and HTML reports from the same immutable report model."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "ablation-report.json"
    markdown_path = output_dir / "ablation-report.md"
    html_path = output_dir / "ablation-report.html"
    await asyncio.gather(
        asyncio.to_thread(json_path.write_text, report_json(report), encoding="utf-8"),
        asyncio.to_thread(markdown_path.write_text, render_markdown(report), encoding="utf-8"),
        asyncio.to_thread(html_path.write_text, render_html(report), encoding="utf-8"),
    )
    return json_path, markdown_path, html_path
