from brasileirao.config import PROJECT_ROOT, Settings


def test_paths_are_inside_project_root():
    s = Settings()
    assert s.raw_dir.is_relative_to(PROJECT_ROOT)
    assert s.warehouse_path.is_relative_to(PROJECT_ROOT)
    assert s.warehouse_path.suffix == ".duckdb"


def test_env_overrides_token(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_TOKEN", "token-de-teste")
    assert Settings().football_data_api_token == "token-de-teste"


def test_ensure_dirs_is_idempotent(tmp_path):
    s = Settings(raw_dir=tmp_path / "raw", warehouse_path=tmp_path / "wh" / "db.duckdb")
    s.ensure_dirs()
    s.ensure_dirs()
    assert s.raw_dir.is_dir()
    assert s.warehouse_path.parent.is_dir()
