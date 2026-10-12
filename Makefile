.PHONY: install migrate check test demo
install:
	uv sync --frozen --python 3.12
migrate:
	uv run alembic upgrade head
check:
	uv run ruff check src tests migrations scripts
	uv run ruff format --check src tests migrations scripts
	uv run mypy

test:
	uv run pytest -q

demo:
	uv run python -m pulse.cli seed-fixture
	uv run python -m pulse.cli schedule
	uv run python -m pulse.cli capture-fixture
	uv run python -m pulse.cli parse
	uv run python -m pulse.cli snapshot
