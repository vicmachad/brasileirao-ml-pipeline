import pandas as pd
import pytest

from brasileirao.config import Settings
from brasileirao.ml.training import (
    FEATURE_COLUMNS,
    TrainingError,
    load_feature_store,
    train_temporal_model,
)


def _matches(count: int) -> pd.DataFrame:
    rows = []
    outcomes = ["home_win", "draw", "away_win"]
    for index in range(count):
        row = {
            "match_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=index),
            "outcome": outcomes[index % len(outcomes)],
        }
        row.update(
            {column: float((index + offset) % 4) for offset, column in enumerate(FEATURE_COLUMNS)}
        )
        rows.append(row)
    return pd.DataFrame(rows)


def test_train_temporal_model_splits_latest_matches_for_evaluation():
    model, metrics = train_temporal_model(_matches(30))

    assert metrics["train_matches"] == 24
    assert metrics["test_matches"] == 6
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert set(model.classes_) == {"home_win", "draw", "away_win"}


def test_train_temporal_model_rejects_too_few_matches():
    with pytest.raises(TrainingError, match="ao menos 10 partidas"):
        train_temporal_model(_matches(9))


def test_load_feature_store_from_databricks(monkeypatch):
    from databricks import sql

    queries = []
    feature_columns = ["match_date", "outcome", *FEATURE_COLUMNS]

    class FakeCursor:
        description = [(column, None) for column in feature_columns]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query):
            queries.append(query)

        def fetchall(self):
            return [(pd.Timestamp("2026-01-01"), "home_win", *([0.0] * len(FEATURE_COLUMNS)))]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(sql, "connect", lambda **_: FakeConnection())
    settings = Settings(
        warehouse_backend="databricks",
        databricks_host="workspace.example",
        databricks_http_path="/sql/1.0/warehouses/warehouse-id",
        databricks_token="test-token",
        databricks_catalog="workspace",
        databricks_schema="brasileirao",
    )

    result = load_feature_store(settings)

    assert len(result) == 1
    assert result.iloc[0]["outcome"] == "home_win"
    assert "`workspace`.`brasileirao_marts`.`feature_store_matches`" in queries[0]
