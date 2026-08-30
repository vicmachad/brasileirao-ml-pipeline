.PHONY: install lint format test ingest dbt-deps dbt-build dbt-test train pipeline \
        docker-build docker-pipeline docker-dbt mlflow-up mlflow-down clean

export DBT_PROFILES_DIR := dbt

# --- Local (uv) ---------------------------------------------------------

install:
	uv sync

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

test:
	uv run pytest

ingest:
	uv run brasileirao ingest

dbt-deps:
	cd dbt && uv run dbt deps

dbt-build:
	cd dbt && uv run dbt build

dbt-test:
	cd dbt && uv run dbt test

train:
	uv run brasileirao train

# Pipeline completo: raw -> dbt -> feature store -> modelo.
pipeline: ingest dbt-build train

# --- Docker -------------------------------------------------------------

docker-build:
	docker compose build

docker-pipeline: docker-build
	docker compose run --rm pipeline ingest
	docker compose run --rm dbt build
	docker compose run --rm pipeline train

docker-dbt:
	docker compose run --rm dbt build

mlflow-up:
	docker compose up -d mlflow

mlflow-down:
	docker compose down

clean:
	rm -rf dbt/target dbt/dbt_packages dbt/logs data/warehouse/*.duckdb .pytest_cache .ruff_cache
