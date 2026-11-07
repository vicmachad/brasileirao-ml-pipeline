"""Camada de ingestao do pipeline."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import requests

from brasileirao.config import Settings

REQUEST_TIMEOUT_SECONDS = 30
_DATABRICKS_COLUMNS = (
    "match_id",
    "match_date",
    "status",
    "matchday",
    "home_team_id",
    "home_team_name",
    "away_team_id",
    "away_team_name",
    "home_score",
    "away_score",
)


class DatabricksIngestionError(RuntimeError):
    """Falha ao carregar partidas no Databricks."""


def fetch_competition_matches(settings: Settings) -> bytes:
    """Busca e retorna sem alteracao o JSON de partidas da competicao."""
    if not settings.football_data_api_token:
        raise ValueError("FOOTBALL_DATA_API_TOKEN nao esta configurado. Preencha o arquivo .env.")

    url = (
        f"{settings.football_data_base_url.rstrip('/')}/competitions/"
        f"{settings.competition_code}/matches"
    )
    response = requests.get(
        url,
        headers={"X-Auth-Token": settings.football_data_api_token},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.content


def write_raw_snapshot(
    raw_dir: Path,
    competition_code: str,
    content: bytes,
    *,
    fetched_at: datetime | None = None,
) -> Path:
    """Grava a resposta em arquivo novo, particionado pela data de ingestao."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", competition_code):
        raise ValueError(f"Codigo de competicao invalido: {competition_code!r}")

    timestamp = fetched_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("fetched_at precisa incluir fuso horario")

    timestamp = timestamp.astimezone(UTC)
    date_partition = timestamp.strftime("%Y-%m-%d")
    filename_timestamp = timestamp.strftime("%Y%m%dT%H%M%S%fZ")
    partition_dir = raw_dir / f"competition={competition_code}" / f"date={date_partition}"
    partition_dir.mkdir(parents=True, exist_ok=True)

    path = partition_dir / f"matches_{filename_timestamp}.json"
    with path.open("xb") as snapshot:
        snapshot.write(content)
    return path


def _validate_databricks_identifier(value: str, setting_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"{setting_name} invalido: {value!r}")
    return f"`{value}`"


def validate_databricks_config(settings: Settings) -> None:
    """Valida as credenciais e nomes usados pela conexao Databricks."""
    if not settings.databricks_host:
        raise ValueError("DATABRICKS_HOST nao esta configurado no arquivo .env.")
    if not settings.databricks_http_path:
        raise ValueError("DATABRICKS_HTTP_PATH nao esta configurado no arquivo .env.")
    if not settings.databricks_token:
        raise ValueError("DATABRICKS_TOKEN nao esta configurado no arquivo .env.")

    _validate_databricks_identifier(settings.databricks_catalog, "DATABRICKS_CATALOG")
    _validate_databricks_identifier(
        settings.databricks_raw_schema,
        "DATABRICKS_RAW_SCHEMA",
    )


def upload_matches_to_databricks(content: bytes, settings: Settings) -> int:
    """Carrega partidas na tabela Delta usada como fonte do dbt."""
    validate_databricks_config(settings)
    catalog = _validate_databricks_identifier(settings.databricks_catalog, "DATABRICKS_CATALOG")
    raw_schema = _validate_databricks_identifier(
        settings.databricks_raw_schema,
        "DATABRICKS_RAW_SCHEMA",
    )
    host = settings.databricks_host.removeprefix("https://").removeprefix("http://").rstrip("/")

    try:
        from databricks import sql
        from databricks.sql.exc import Error as DatabricksSQLError
    except ImportError as exc:
        raise DatabricksIngestionError(
            "Dependencias Databricks ausentes. Execute `uv sync --extra databricks`."
        ) from exc

    try:
        payload = json.loads(content)
    except ValueError as exc:
        raise ValueError("Resposta da API nao e um JSON valido.") from exc

    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise ValueError("Resposta da API nao contem a lista `matches` esperada.")

    records = []
    for match in matches:
        full_time = match.get("score", {}).get("fullTime", {})
        match_date = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
        records.append(
            (
                int(match["id"]),
                match_date.astimezone(UTC).replace(tzinfo=None),
                match["status"],
                match.get("matchday"),
                match.get("homeTeam", {}).get("id"),
                match.get("homeTeam", {}).get("name"),
                match.get("awayTeam", {}).get("id"),
                match.get("awayTeam", {}).get("name"),
                full_time.get("home"),
                full_time.get("away"),
            )
        )

    if not records:
        raise ValueError("A API nao retornou partidas para carregar no Databricks.")

    destination = f"{catalog}.{raw_schema}.`raw_matches`"
    temporary_table = f"{catalog}.{raw_schema}.`raw_matches_stage_{uuid4().hex}`"
    column_sql = ", ".join(f"`{column}`" for column in _DATABRICKS_COLUMNS)
    definitions = """
        `match_id` BIGINT,
        `match_date` TIMESTAMP,
        `status` STRING,
        `matchday` INT,
        `home_team_id` BIGINT,
        `home_team_name` STRING,
        `away_team_id` BIGINT,
        `away_team_name` STRING,
        `home_score` INT,
        `away_score` INT
    """
    placeholders = ", ".join("?" for _ in _DATABRICKS_COLUMNS)
    update_assignments = ", ".join(
        f"target.`{column}` = source.`{column}`"
        for column in _DATABRICKS_COLUMNS
        if column != "match_id"
    )
    insert_values = ", ".join(f"source.`{column}`" for column in _DATABRICKS_COLUMNS)
    created_stage = False

    try:
        with (
            sql.connect(
                server_hostname=host,
                http_path=settings.databricks_http_path,
                access_token=settings.databricks_token,
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{raw_schema}")
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {destination} ({definitions}) USING DELTA")
            cursor.execute(f"CREATE TABLE {temporary_table} ({definitions}) USING DELTA")
            created_stage = True
            cursor.executemany(
                f"INSERT INTO {temporary_table} ({column_sql}) VALUES ({placeholders})",
                records,
            )
            cursor.execute(
                f"""
                    MERGE INTO {destination} AS target
                    USING {temporary_table} AS source
                    ON target.`match_id` = source.`match_id`
                    WHEN MATCHED THEN UPDATE SET {update_assignments}
                    WHEN NOT MATCHED THEN INSERT ({column_sql})
                    VALUES ({insert_values})
                    """
            )
            cursor.execute(f"DROP TABLE {temporary_table}")
            created_stage = False
    except DatabricksSQLError as exc:
        cleanup_error = None
        if created_stage:
            try:
                with (
                    sql.connect(
                        server_hostname=host,
                        http_path=settings.databricks_http_path,
                        access_token=settings.databricks_token,
                    ) as cleanup_connection,
                    cleanup_connection.cursor() as cleanup_cursor,
                ):
                    cleanup_cursor.execute(f"DROP TABLE IF EXISTS {temporary_table}")
            except DatabricksSQLError as cleanup_exc:
                cleanup_error = cleanup_exc
        cleanup_message = (
            f" A tabela temporaria {temporary_table} pode precisar de remocao manual."
            if cleanup_error
            else ""
        )
        raise DatabricksIngestionError(
            "Falha na carga SQL para Databricks. Confira host, HTTP Path, token, "
            f"permissoes do Warehouse e privilegios no catalogo/schema.{cleanup_message}"
        ) from exc

    return len(records)
