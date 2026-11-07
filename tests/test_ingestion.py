from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests
from typer.testing import CliRunner

from brasileirao.cli import app
from brasileirao.config import Settings
from brasileirao.ingestion import fetch_competition_matches, write_raw_snapshot


def test_fetch_competition_matches_uses_configured_api(monkeypatch):
    settings = Settings(
        football_data_api_token="token-de-teste",
        football_data_base_url="https://example.test/v4/",
        competition_code="BSA",
    )
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"matches":[]}'
    request_args = {}

    def fake_get(url, **kwargs):
        request_args["url"] = url
        request_args.update(kwargs)
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    assert fetch_competition_matches(settings) == b'{"matches":[]}'
    assert request_args["url"] == "https://example.test/v4/competitions/BSA/matches"
    assert request_args["headers"] == {"X-Auth-Token": "token-de-teste"}
    assert request_args["timeout"] > 0


def test_fetch_competition_matches_requires_token():
    with pytest.raises(ValueError, match="FOOTBALL_DATA_API_TOKEN"):
        fetch_competition_matches(Settings(football_data_api_token=""))


def test_write_raw_snapshot_partitions_by_utc_date_and_preserves_bytes(tmp_path):
    content = b'{"raw": true}\n'
    fetched_at = datetime(2026, 11, 7, 18, 30, tzinfo=UTC)

    path = write_raw_snapshot(tmp_path, "BSA", content, fetched_at=fetched_at)

    assert path == (
        tmp_path / "competition=BSA" / "date=2026-11-07" / "matches_20261107T183000000000Z.json"
    )
    assert path.read_bytes() == content


def test_write_raw_snapshot_never_overwrites_existing_file(tmp_path):
    fetched_at = datetime(2026, 11, 7, 18, 30, tzinfo=UTC)
    path = write_raw_snapshot(tmp_path, "BSA", b"first", fetched_at=fetched_at)

    with pytest.raises(FileExistsError):
        write_raw_snapshot(tmp_path, "BSA", b"second", fetched_at=fetched_at)

    assert path.read_bytes() == b"first"


def test_write_raw_snapshot_rejects_unsafe_competition_code(tmp_path):
    with pytest.raises(ValueError, match="Codigo de competicao invalido"):
        write_raw_snapshot(tmp_path, "../elsewhere", b"data")


def test_cli_ingest_reports_missing_token(monkeypatch, tmp_path: Path):
    from brasileirao import cli

    monkeypatch.setattr(cli, "settings", Settings(football_data_api_token="", raw_dir=tmp_path))
    result = CliRunner().invoke(app, ["ingest"])

    assert result.exit_code == 1
    assert "FOOTBALL_DATA_API_TOKEN" in result.output
