import io
import logging

from rageval.core.logging import JsonFormatter, SecretRedactionFilter


def test_structured_logging_redacts_secrets() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretRedactionFilter())
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("rageval-test-redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info(
        "provider token=message-secret",
        extra={"context": {"api_key": "context-secret", "safe": "visible"}},
    )
    output = stream.getvalue()

    assert "message-secret" not in output
    assert "context-secret" not in output
    assert "[REDACTED]" in output
    assert "visible" in output
