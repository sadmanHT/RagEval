from __future__ import annotations

from pathlib import Path

from rageval.ingestion.cli import main


def test_file_cli_writes_debug_json(tmp_path: Path) -> None:
    source = tmp_path / "paper.html"
    output = tmp_path / "parsed.json"
    source.write_text("<html><body><h1>Title</h1><p>Text</p></body></html>", encoding="utf-8")

    status = main(
        [
            "file",
            str(source),
            "--domain",
            "research",
            "--output",
            str(output),
            "--ocr-mode",
            "disabled",
        ]
    )

    assert status == 0
    text = output.read_text(encoding="utf-8")
    assert '"kind": "title"' in text
    assert '"kind": "text"' in text


def test_file_cli_rejects_unsupported_extension(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("no", encoding="utf-8")
    status = main(
        [
            "file",
            str(source),
            "--domain",
            "research",
            "--output",
            str(tmp_path / "parsed.json"),
        ]
    )
    assert status == 2
