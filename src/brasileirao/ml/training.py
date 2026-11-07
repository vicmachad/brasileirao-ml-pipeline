"""Treino e registro do classificador de resultados."""

from __future__ import annotations

from pathlib import Path

import duckdb
import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

from brasileirao.config import Settings

FEATURE_COLUMNS = [
    "home_avg_points_prior",
    "home_avg_goals_for_prior",
    "home_avg_goals_against_prior",
    "away_avg_points_prior",
    "away_avg_goals_for_prior",
    "away_avg_goals_against_prior",
]
MIN_MATCHES = 10
FEATURE_STORE_TABLE = "main_marts.feature_store_matches"


class TrainingError(RuntimeError):
    """Erro claro de pré-condição ou execução do treino."""


def train_temporal_model(matches: pd.DataFrame) -> tuple[RandomForestClassifier, dict[str, float]]:
    """Treina nos jogos mais antigos e mede desempenho nos jogos mais recentes."""
    if len(matches) < MIN_MATCHES:
        raise TrainingError(
            f"São necessárias ao menos {MIN_MATCHES} partidas concluídas; "
            f"foram encontradas {len(matches)}."
        )

    matches = matches.sort_values("match_date").reset_index(drop=True)
    split_index = int(len(matches) * 0.8)
    train = matches.iloc[:split_index]
    test = matches.iloc[split_index:]
    if train["outcome"].nunique() < 2:
        raise TrainingError(
            "O período de treino precisa conter ao menos dois resultados diferentes."
        )
    model = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        random_state=42,
    )
    model.fit(train[FEATURE_COLUMNS], train["outcome"])
    accuracy = accuracy_score(test["outcome"], model.predict(test[FEATURE_COLUMNS]))
    return model, {
        "accuracy": float(accuracy),
        "train_matches": float(len(train)),
        "test_matches": float(len(test)),
    }


def load_feature_store(warehouse_path: Path) -> pd.DataFrame:
    """Lê as features materializadas pelo dbt do warehouse configurado."""
    if not warehouse_path.is_file():
        raise TrainingError(
            f"Warehouse nao encontrado em {warehouse_path}. Execute `make dbt-build` antes."
        )

    try:
        with duckdb.connect(str(warehouse_path), read_only=True) as connection:
            return connection.execute(
                f"select match_date, outcome, {', '.join(FEATURE_COLUMNS)} "
                f"from {FEATURE_STORE_TABLE} order by match_date"
            ).fetchdf()
    except duckdb.Error as exc:
        raise TrainingError(
            "Nao foi possivel ler a feature store. Execute `make dbt-build` antes."
        ) from exc


def run_training(settings: Settings) -> tuple[dict[str, float], str]:
    """Treina o modelo, registra métricas e artefato no MLflow."""
    matches = load_feature_store(settings.warehouse_path)
    model, metrics = train_temporal_model(matches)

    settings.ensure_dirs()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
    experiment = client.get_experiment_by_name(settings.mlflow_experiment_name)
    experiment_id = (
        experiment.experiment_id
        if experiment
        else client.create_experiment(
            settings.mlflow_experiment_name,
            artifact_location=settings.mlflow_artifact_root.resolve().as_uri(),
        )
    )
    mlflow.set_experiment(experiment_id=experiment_id)

    split_index = int(len(matches.sort_values("match_date")) * 0.8)
    split_date = str(matches.sort_values("match_date").iloc[split_index]["match_date"])
    with mlflow.start_run() as run:
        mlflow.log_params(
            {
                "model": "RandomForestClassifier",
                "n_estimators": 200,
                "split_strategy": "temporal_80_20",
                "feature_count": len(FEATURE_COLUMNS),
            }
        )
        mlflow.log_metrics(metrics)
        mlflow.log_param("split_date", split_date)
        mlflow.sklearn.log_model(model, artifact_path="model")

    return metrics, run.info.run_id
