from __future__ import annotations

import hashlib
from pathlib import Path

from rageval.corpus.models import CorpusDocument, DatasetSplit
from rageval.ingestion.loaders import parse_batch
from rageval.ingestion.models import OCRMode, ParserConfig
from rageval.models import DocumentRecord, Domain, SourceType


def _item(root: Path, relative: str, source_type: SourceType) -> CorpusDocument:
    path = root / relative
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return CorpusDocument(
        record=DocumentRecord(
            document_id=f"doc_{checksum[:32]}",
            source_uri=f"file:///{relative}",
            source_type=source_type,
            domain=Domain.RESEARCH,
            checksum_sha256=checksum,
        ),
        relative_path=relative,
        logical_title=path.stem,
        split=DatasetSplit.DEVELOPMENT,
        size_bytes=path.stat().st_size,
    )


def test_batch_preserves_successes_and_collects_failures(tmp_path: Path) -> None:
    good = tmp_path / "development" / "research" / "good.html"
    bad = tmp_path / "development" / "research" / "bad.pdf"
    good.parent.mkdir(parents=True)
    good.write_text("<h1>Good</h1><p>Document</p>", encoding="utf-8")
    bad.write_bytes(b"broken")

    result = parse_batch(
        (
            _item(tmp_path, "development/research/good.html", SourceType.HTML),
            _item(tmp_path, "development/research/bad.pdf", SourceType.PDF),
        ),
        tmp_path,
        config=ParserConfig(ocr_mode=OCRMode.DISABLED),
    )

    assert len(result.successes) == 1
    assert len(result.failures) == 1
    assert result.failures[0].relative_path.endswith("bad.pdf")
