.PHONY: install install-databricks lint format test ingest dbt-deps dbt-build dbt-test train pipeline \
        databricks-debug databricks-ingest databricks-build databricks-test databricks-train databricks-pipeline \
        docker-build docker-pipeline docker-dbt mlflow-up mlflow-down clean

export DBT_PROFILES_DIR := $(CURDIR)/dbt
DBT_TARGET ?= dev

# --- Local (uv) ---------------------------------------------------------

install:
	uv sync

install-databricks:
	uv sync --extra databricks

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
	cd dbt && uv run dbt build --target $(DBT_TARGET)

dbt-test:
	cd dbt && uv run dbt test --target $(DBT_TARGET)

train:
	uv run brasileirao train

# Pipeline completo: raw -> dbt -> feature store -> modelo.
pipeline: ingest dbt-build train

databricks-ingest:
	uv run --extra databricks brasileirao ingest-databricks

databricks-debug:
	cd dbt && uv run --extra databricks dbt debug --target databricks

databricks-build:
	cd dbt && uv run --extra databricks dbt build --target databricks

databricks-test:
	cd dbt && uv run --extra databricks dbt test --target databricks

databricks-train:
	WAREHOUSE_BACKEND=databricks uv run --extra databricks brasileirao train

databricks-pipeline: databricks-ingest databricks-build databricks-train

# --- Docker -------------------------------------------------------------

docker-build:
	docker compose build pipeline

docker-pipeline: docker-build
	docker compose run --rm pipeline ingest
	docker compose run --rm dbt build
	docker compose run --rm pipeline train

docker-dbt: docker-build
	docker compose run --rm dbt build

mlflow-up: docker-build
	docker compose up -d mlflow

mlflow-down:
	docker compose down

clean:
	rm -rf dbt/target dbt/dbt_packages dbt/logs data/warehouse/*.duckdb .pytest_cache .ruff_cache
