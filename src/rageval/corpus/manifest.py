"""Deterministic corpus discovery, checksums, manifests, and leakage checks."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from rageval.core.errors import DataLeakageError, ValidationError
from rageval.core.ids import make_document_id
from rageval.corpus.models import CorpusDocument, CorpusManifest, DatasetSplit, DuplicateGroup
from rageval.models import DocumentRecord, Domain, SourceType

_SUPPORTED_SUFFIXES: dict[str, SourceType] = {
    ".pdf": SourceType.PDF,
    ".docx": SourceType.DOCX,
    ".html": SourceType.HTML,
    ".htm": SourceType.HTML,
}


@dataclass(frozen=True, slots=True)
class ScanReport:
    """Manifest plus files intentionally excluded because their type is unsupported."""

    manifest: CorpusManifest
    unsupported_paths: tuple[str, ...]


def sha256_file(path: Path, *, block_size: int = 1024 * 1024) -> str:
    """Hash a file without loading the whole document into memory."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while block := stream.read(block_size):
                digest.update(block)
    except OSError as exc:
        raise ValidationError(f"cannot read source file {path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_document(document: CorpusDocument) -> dict[str, object]:
    """Return scan-time-independent fields that define a corpus revision."""

    return {
        "document_id": document.record.document_id,
        "checksum_sha256": document.record.checksum_sha256,
        "source_type": document.record.source_type.value,
        "domain": document.record.domain.value,
        "relative_path": document.relative_path,
        "logical_title": document.logical_title,
        "split": document.split.value,
        "size_bytes": document.size_bytes,
        "source_date": document.source_date.isoformat() if document.source_date else None,
        "parser_version": document.parser_version,
        "tenant_id": document.tenant_id,
        "security_tags": sorted(document.security_tags),
        "locator": document.locator.model_dump(mode="json") if document.locator else None,
    }


def fingerprint_documents(documents: tuple[CorpusDocument, ...] | list[CorpusDocument]) -> str:
    """Fingerprint corpus identity independent of input ordering and scan timestamps."""

    canonical = [_canonical_document(document) for document in documents]
    canonical.sort(
        key=lambda item: (
            str(item["checksum_sha256"]),
            str(item["relative_path"]),
            str(item["split"]),
        )
    )
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _duplicate_groups(documents: list[CorpusDocument]) -> tuple[DuplicateGroup, ...]:
    by_checksum: dict[str, list[CorpusDocument]] = defaultdict(list)
    for document in documents:
        by_checksum[document.record.checksum_sha256].append(document)

    groups: list[DuplicateGroup] = []
    for checksum, members in sorted(by_checksum.items()):
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda item: item.relative_path)
        groups.append(
            DuplicateGroup(
                checksum_sha256=checksum,
                document_ids=tuple(item.record.document_id for item in ordered),
                relative_paths=tuple(item.relative_path for item in ordered),
            )
        )
    return tuple(groups)


def assert_no_split_leakage(documents: tuple[CorpusDocument, ...] | list[CorpusDocument]) -> None:
    """Reject any document identity or byte-identical source crossing the held-out boundary."""

    checksum_splits: dict[str, set[DatasetSplit]] = defaultdict(set)
    id_splits: dict[str, set[DatasetSplit]] = defaultdict(set)

    for document in documents:
        checksum_splits[document.record.checksum_sha256].add(document.split)
        id_splits[document.record.document_id].add(document.split)

    leaked_checksums = sorted(key for key, splits in checksum_splits.items() if len(splits) > 1)
    leaked_ids = sorted(key for key, splits in id_splits.items() if len(splits) > 1)
    if leaked_checksums or leaked_ids:
        details: list[str] = []
        if leaked_checksums:
            details.append(f"checksums={','.join(leaked_checksums)}")
        if leaked_ids:
            details.append(f"document_ids={','.join(leaked_ids)}")
        raise DataLeakageError("development/evaluation leakage detected: " + "; ".join(details))


def _parse_layout(relative_path: Path) -> tuple[DatasetSplit, Domain]:
    if len(relative_path.parts) < 3:
        raise ValidationError(
            "supported corpus files must use <split>/<domain>/<file>; "
            f"got {relative_path.as_posix()}"
        )
    try:
        split = DatasetSplit(relative_path.parts[0])
    except ValueError as exc:
        raise ValidationError(
            f"invalid dataset split {relative_path.parts[0]!r} for {relative_path.as_posix()}"
        ) from exc
    try:
        domain = Domain(relative_path.parts[1])
    except ValueError as exc:
        raise ValidationError(
            f"invalid domain {relative_path.parts[1]!r} for {relative_path.as_posix()}"
        ) from exc
    return split, domain


def scan_corpus(root: Path, *, fail_on_unsupported: bool = False) -> ScanReport:
    """Discover supported source files without parsing their document contents."""

    root = root.resolve()
    if not root.exists():
        raise ValidationError(f"corpus root does not exist: {root}")
    if not root.is_dir():
        raise ValidationError(f"corpus root is not a directory: {root}")

    documents: list[CorpusDocument] = []
    unsupported: list[str] = []

    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root)
        suffix = path.suffix.lower()
        source_type = _SUPPORTED_SUFFIXES.get(suffix)
        if source_type is None:
            unsupported.append(relative.as_posix())
            continue

        split, domain = _parse_layout(relative)
        checksum = sha256_file(path)
        source_uri = f"file:///{relative.as_posix()}"
        record = DocumentRecord(
            document_id=make_document_id(checksum_sha256=checksum, source_uri=source_uri),
            source_uri=source_uri,
            source_type=source_type,
            domain=domain,
            checksum_sha256=checksum,
        )
        documents.append(
            CorpusDocument(
                record=record,
                relative_path=relative.as_posix(),
                logical_title=path.stem.replace("_", " ").replace("-", " ").strip() or path.name,
                split=split,
                size_bytes=path.stat().st_size,
            )
        )

    if fail_on_unsupported and unsupported:
        raise ValidationError("unsupported corpus files: " + ", ".join(sorted(unsupported)))

    assert_no_split_leakage(documents)
    manifest = CorpusManifest(
        root_hint=root.name,
        documents=tuple(documents),
        duplicates=_duplicate_groups(documents),
        fingerprint=fingerprint_documents(documents),
    )
    return ScanReport(manifest=manifest, unsupported_paths=tuple(sorted(unsupported)))


def write_manifest(manifest: CorpusManifest, path: Path) -> None:
    """Write deterministic JSON fields while retaining generated-at audit metadata."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_manifest(path: Path) -> CorpusManifest:
    """Read and validate a manifest, including its embedded corpus fingerprint."""

    try:
        manifest = CorpusManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(f"cannot read manifest {path}: {exc}") from exc
    except PydanticValidationError as exc:
        raise ValidationError(f"invalid corpus manifest {path}: {exc}") from exc

    expected = fingerprint_documents(list(manifest.documents))
    if manifest.fingerprint != expected:
        raise ValidationError(
            f"manifest fingerprint mismatch: stored={manifest.fingerprint} expected={expected}"
        )
    assert_no_split_leakage(list(manifest.documents))
    return manifest


def validate_manifest_files(manifest: CorpusManifest, root: Path) -> None:
    """Verify every manifest path still exists and still has the recorded bytes."""

    root = root.resolve()
    for document in manifest.documents:
        path = (root / document.relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValidationError(
                f"manifest path escapes corpus root: {document.relative_path}"
            ) from exc
        if not path.is_file():
            raise ValidationError(f"manifest source is missing: {document.relative_path}")
        actual = sha256_file(path)
        if actual != document.record.checksum_sha256:
            raise ValidationError(
                "manifest checksum mismatch for "
                f"{document.relative_path}: stored={document.record.checksum_sha256} actual={actual}"
            )
