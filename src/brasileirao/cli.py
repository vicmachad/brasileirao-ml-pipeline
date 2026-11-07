"""Ponto de entrada unico do pipeline.

Cada camada expoe um subcomando. `config` inspeciona a configuracao e `ingest`
baixa a resposta bruta da API.
"""

from __future__ import annotations

import requests
import typer

from brasileirao.config import settings
from brasileirao.ingestion import (
    DatabricksIngestionError,
    fetch_competition_matches,
    upload_matches_to_databricks,
    validate_databricks_config,
    write_raw_snapshot,
)
from brasileirao.ml import TrainingError, run_training

app = typer.Typer(help="Pipeline Brasileirao: ingestao -> dbt -> features -> ML.")


@app.callback()
def main() -> None:
    """Mantem o CLI como multi-comando."""


@app.command()
def config() -> None:
    """Mostra a configuracao efetiva (util para depurar .env e CI)."""
    token = settings.football_data_api_token
    typer.echo(f"competition_code      : {settings.competition_code}")
    typer.echo(f"api_token             : {'definido' if token else 'AUSENTE'}")
    typer.echo(f"raw_dir               : {settings.raw_dir}")
    typer.echo(f"warehouse_path        : {settings.warehouse_path}")
    typer.echo(f"mlflow_tracking_uri   : {settings.mlflow_tracking_uri}")
    typer.echo(f"mlflow_artifact_root  : {settings.mlflow_artifact_root}")
    typer.echo(f"focus_team            : {settings.focus_team}")


@app.command()
def ingest() -> None:
    """Baixa partidas da API e salva a resposta original em data/raw/."""
    try:
        content = fetch_competition_matches(settings)
        path = write_raw_snapshot(settings.raw_dir, settings.competition_code, content)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except requests.RequestException as exc:
        typer.echo(f"Falha ao consultar football-data.org: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        typer.echo(f"Falha ao gravar resposta bruta: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Resposta bruta salva em: {path}")


@app.command("ingest-databricks")
def ingest_databricks() -> None:
    """Salva o snapshot local e sincroniza partidas para uma tabela Delta."""
    try:
        validate_databricks_config(settings)
        content = fetch_competition_matches(settings)
        path = write_raw_snapshot(settings.raw_dir, settings.competition_code, content)
        row_count = upload_matches_to_databricks(content, settings)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except requests.RequestException as exc:
        typer.echo(f"Falha ao consultar football-data.org: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        typer.echo(f"Falha ao gravar resposta bruta: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except DatabricksIngestionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Snapshot local salvo em: {path}")
    typer.echo(
        f"{row_count} partidas sincronizadas em "
        f"{settings.databricks_catalog}.{settings.databricks_raw_schema}.raw_matches"
    )


@app.command()
def train() -> None:
    """Treina e registra um modelo usando a feature store criada pelo dbt."""
    try:
        metrics, run_id = run_training(settings)
    except TrainingError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        typer.echo(f"Falha ao preparar o armazenamento do MLflow: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Modelo registrado no MLflow (run_id={run_id})")
    typer.echo(f"Acuracia temporal: {metrics['accuracy']:.3f}")
    typer.echo(
        f"Partidas: treino={int(metrics['train_matches'])}, teste={int(metrics['test_matches'])}"
    )


if __name__ == "__main__":
    app()
