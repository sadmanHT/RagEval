from __future__ import annotations

from pathlib import Path

from rageval.corpus.cli import main


def test_cli_scan_validate_and_fingerprint(tmp_path: Path, capsys) -> None:
    corpus = tmp_path / "corpus"
    source = corpus / "development" / "research" / "note.html"
    source.parent.mkdir(parents=True)
    source.write_text("<html><body>fixture</body></html>", encoding="utf-8")
    manifest = tmp_path / "manifest.json"

    assert main(["scan", str(corpus), "--output", str(manifest)]) == 0
    scan_output = capsys.readouterr().out
    assert "documents=1" in scan_output
    assert "fingerprint=" in scan_output

    assert main(["validate", str(manifest), "--root", str(corpus)]) == 0
    validate_output = capsys.readouterr().out
    assert "valid fingerprint=" in validate_output

    assert main(["fingerprint", str(manifest)]) == 0
    fingerprint_output = capsys.readouterr().out.strip()
    assert len(fingerprint_output) == 64


def test_cli_returns_nonzero_for_missing_corpus(tmp_path: Path, capsys) -> None:
    manifest = tmp_path / "manifest.json"
    assert main(["scan", str(tmp_path / "missing"), "--output", str(manifest)]) == 2
    assert "corpus root does not exist" in capsys.readouterr().out
