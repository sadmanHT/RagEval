.PHONY: install lint format format-check typecheck unit integration compose-up compose-down verify
.PHONY: dense-report sparse-report hybrid-report retrieval-report generation-report evaluation-report
.PHONY: evaluation-ablation-report serving-report test smoke ci

install:
	python -m pip install -e '.[dev]'

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

typecheck:
	mypy src

unit:
	pytest -q tests/unit

compose-up:
	docker compose up -d qdrant redis
	python scripts/wait_for_services.py

compose-down:
	docker compose down -v

integration: compose-up
	pytest -q tests/integration

dense-report:
	python scripts/dense_fixture_report.py

sparse-report:
	python scripts/sparse_fixture_report.py

hybrid-report:
	python scripts/hybrid_fixture_report.py

retrieval-report:
	python scripts/retrieval_service_fixture_report.py

generation-report:
	python scripts/generation_fixture_report.py

evaluation-report:
	python scripts/evaluation_fixture_report.py

evaluation-ablation-report:
	python scripts/evaluation_ablation_fixture_report.py

serving-report:
	python scripts/serving_fixture_report.py

smoke:
	python -m rageval.smoke

test:
	pytest -q

verify: lint format-check typecheck unit

ci: verify integration dense-report sparse-report hybrid-report retrieval-report generation-report \
	evaluation-report evaluation-ablation-report serving-report smoke test
