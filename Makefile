.PHONY: install lint format format-check typecheck unit integration dense-report test compose-up compose-down verify smoke ci

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

smoke:
	python -m rageval.smoke

test:
	pytest -q

verify: lint format-check typecheck unit

ci: verify integration dense-report smoke test
