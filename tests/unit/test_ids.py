from rageval.core.ids import fingerprint_mapping, make_chunk_id, make_document_id


def test_document_id_is_deterministic_and_sensitive_to_source() -> None:
    checksum = "a" * 64
    first = make_document_id(checksum_sha256=checksum, source_uri="file:///a.pdf")
    again = make_document_id(checksum_sha256=checksum, source_uri="file:///a.pdf")
    changed = make_document_id(checksum_sha256=checksum, source_uri="file:///b.pdf")

    assert first == again
    assert first != changed
    assert first.startswith("doc_")


def test_chunk_id_changes_with_ordinal_or_content() -> None:
    config = fingerprint_mapping({"size": 512, "overlap": 64})
    first = make_chunk_id(
        document_id="doc_12345678", ordinal=0, config_fingerprint=config, text="alpha"
    )
    again = make_chunk_id(
        document_id="doc_12345678", ordinal=0, config_fingerprint=config, text="alpha"
    )
    next_chunk = make_chunk_id(
        document_id="doc_12345678", ordinal=1, config_fingerprint=config, text="alpha"
    )
    changed_text = make_chunk_id(
        document_id="doc_12345678", ordinal=0, config_fingerprint=config, text="beta"
    )

    assert first == again
    assert len({first, next_chunk, changed_text}) == 3


def test_mapping_fingerprint_ignores_key_order() -> None:
    assert fingerprint_mapping({"a": 1, "b": 2}) == fingerprint_mapping({"b": 2, "a": 1})
