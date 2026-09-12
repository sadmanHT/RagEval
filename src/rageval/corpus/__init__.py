"""Corpus discovery, manifests, fingerprints, and split governance."""

from rageval.corpus.manifest import (
    ScanReport,
    assert_no_split_leakage,
    fingerprint_documents,
    read_manifest,
    scan_corpus,
    sha256_file,
    validate_manifest_files,
    write_manifest,
)
from rageval.corpus.models import (
    CorpusDocument,
    CorpusManifest,
    DatasetSplit,
    DuplicateGroup,
    EvaluationDatasetRecord,
    SourceLocator,
)

__all__ = [
    "CorpusDocument",
    "CorpusManifest",
    "DatasetSplit",
    "DuplicateGroup",
    "EvaluationDatasetRecord",
    "ScanReport",
    "SourceLocator",
    "assert_no_split_leakage",
    "fingerprint_documents",
    "read_manifest",
    "scan_corpus",
    "sha256_file",
    "validate_manifest_files",
    "write_manifest",
]
