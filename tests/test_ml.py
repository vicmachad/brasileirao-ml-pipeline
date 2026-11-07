import pandas as pd
import pytest

from brasileirao.ml.training import FEATURE_COLUMNS, TrainingError, train_temporal_model


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
