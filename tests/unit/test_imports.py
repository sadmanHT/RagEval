import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "rageval",
        "rageval.core",
        "rageval.models",
        "rageval.ingestion",
        "rageval.cleaning",
        "rageval.chunking",
        "rageval.retrieval",
        "rageval.retrieval.dense",
        "rageval.retrieval.sparse",
        "rageval.retrieval.hybrid",
        "rageval.retrieval.rerank",
        "rageval.retrieval.service",
        "rageval.generation",
        "rageval.evaluation",
        "rageval.serving",
    ],
)
def test_top_level_packages_import(module_name: str) -> None:
    importlib.import_module(module_name)
