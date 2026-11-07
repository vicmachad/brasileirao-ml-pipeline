"""Camada de ingestao do pipeline."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import requests

from brasileirao.config import Settings

REQUEST_TIMEOUT_SECONDS = 30


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
