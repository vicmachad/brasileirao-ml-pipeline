"""Configuracao central do pipeline.

Todos os caminhos sao derivados da raiz do repositorio para que os scripts
funcionem igual em desenvolvimento local e no CI.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Parametros do pipeline, sobrescreviveis por variaveis de ambiente ou .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    # --- API football-data.org ---
    football_data_api_token: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"
    competition_code: str = "BSA"
    # Free tier: 10 requisicoes/minuto. Mantemos folga.
    api_requests_per_minute: int = 8

    # --- Camadas de dados ---
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    warehouse_path: Path = PROJECT_ROOT / "data" / "warehouse" / "brasileirao.duckdb"

    # --- ML ---
    mlflow_tracking_uri: str = f"file:///{(PROJECT_ROOT / 'mlruns').as_posix()}"
    mlflow_experiment_name: str = "brasileirao-match-outcome"
    focus_team: str = "Coritiba Foot Ball Club"

    def ensure_dirs(self) -> None:
        """Cria os diretorios de dados caso ainda nao existam."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.warehouse_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
