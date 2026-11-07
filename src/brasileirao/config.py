"""Configuracao central do pipeline.

Todos os caminhos sao derivados da raiz do repositorio para que os scripts
funcionem igual em desenvolvimento local e no CI.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Em desenvolvimento o pacote roda a partir de src/, entao a raiz do repo esta
# dois niveis acima. Dentro do container o pacote vive na .venv, onde essa
# heuristica nao vale -- por isso PROJECT_ROOT e sobrescrivivel por env var.
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[2]))


class Settings(BaseSettings):
    """Parametros do pipeline, sobrescreviveis por variaveis de ambiente ou .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    # --- API football-data.org ---
    football_data_api_token: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"
    competition_code: str = "BSA"
    # Free tier: 10 requisicoes/minuto. Mantemos folga.
    api_requests_per_minute: int = 8

    # --- Camadas de dados ---
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    # DUCKDB_PATH e a mesma variavel lida pelo profiles.yml do dbt: um unico
    # ajuste aponta o Python e o dbt para o mesmo warehouse.
    warehouse_path: Path = Field(
        default=PROJECT_ROOT / "data" / "warehouse" / "brasileirao.duckdb",
        validation_alias="DUCKDB_PATH",
    )
    databricks_host: str = Field(default="", validation_alias="DATABRICKS_HOST")
    databricks_http_path: str = Field(default="", validation_alias="DATABRICKS_HTTP_PATH")
    databricks_token: str = Field(default="", validation_alias="DATABRICKS_TOKEN")
    databricks_catalog: str = Field(default="workspace", validation_alias="DATABRICKS_CATALOG")
    databricks_schema: str = Field(default="brasileirao", validation_alias="DATABRICKS_SCHEMA")
    databricks_raw_schema: str = Field(
        default="brasileirao_raw",
        validation_alias="DATABRICKS_RAW_SCHEMA",
    )
    warehouse_backend: Literal["duckdb", "databricks"] = Field(
        default="duckdb",
        validation_alias="WAREHOUSE_BACKEND",
    )

    # --- ML ---
    # Backend SQLite: o MLflow 3.x deprecou o file store, e um backend de banco
    # e pre-requisito para o model registry.
    mlflow_tracking_uri: str = f"sqlite:///{(PROJECT_ROOT / 'mlruns' / 'mlflow.db').as_posix()}"
    mlflow_artifact_root: Path = PROJECT_ROOT / "mlruns" / "artifacts"
    mlflow_experiment_name: str = "brasileirao-match-outcome"
    focus_team: str = "Coritiba Foot Ball Club"

    def ensure_dirs(self) -> None:
        """Cria os diretorios de dados caso ainda nao existam."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.warehouse_path.parent.mkdir(parents=True, exist_ok=True)
        self.mlflow_artifact_root.mkdir(parents=True, exist_ok=True)


settings = Settings()
