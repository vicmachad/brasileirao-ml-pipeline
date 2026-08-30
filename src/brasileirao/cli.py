"""Ponto de entrada unico do pipeline.

Cada camada expoe um subcomando. Por enquanto apenas `config` esta
implementado; ingestao, treino e predicao entram nas proximas etapas.
"""

from __future__ import annotations

import typer

from brasileirao.config import settings

app = typer.Typer(help="Pipeline Brasileirao: ingestao -> dbt -> features -> ML.")


@app.callback()
def main() -> None:
    """Mantem o CLI como multi-comando enquanto as demais camadas nao existem."""


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


if __name__ == "__main__":
    app()
