.PHONY: install lint test ingest dbt-deps dbt-build dbt-test train pipeline clean

export DBT_PROFILES_DIR := dbt

install:
	python -m pip install --upgrade pip
	pip install -e ".[dbt,dev]"

lint:
	ruff check src tests
	ruff format --check src tests

test:
	pytest

ingest:
	python -m brasileirao.cli ingest

dbt-deps:
	cd dbt && dbt deps

dbt-build:
	cd dbt && dbt build

dbt-test:
	cd dbt && dbt test

train:
	python -m brasileirao.cli train

# Executa o pipeline completo: raw -> dbt -> feature store -> modelo.
pipeline: ingest dbt-build train

clean:
	rm -rf dbt/target dbt/dbt_packages data/warehouse/*.duckdb .pytest_cache
