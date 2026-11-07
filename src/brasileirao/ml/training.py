"""Treino e registro do classificador de resultados."""

from __future__ import annotations

import re

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


def load_feature_store(settings: Settings) -> pd.DataFrame:
    """Lê a feature store do DuckDB local ou do Databricks."""
    columns = f"match_date, outcome, {', '.join(FEATURE_COLUMNS)}"
    if settings.warehouse_backend == "databricks":
        if not settings.databricks_host or not settings.databricks_http_path:
            raise TrainingError("Configure DATABRICKS_HOST e DATABRICKS_HTTP_PATH no .env.")
        if not settings.databricks_token:
            raise TrainingError("Configure DATABRICKS_TOKEN no .env.")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", settings.databricks_catalog):
            raise TrainingError("DATABRICKS_CATALOG contem identificador invalido.")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", settings.databricks_schema):
            raise TrainingError("DATABRICKS_SCHEMA contem identificador invalido.")

        try:
            from databricks import sql
            from databricks.sql.exc import Error as DatabricksSQLError
        except ImportError as exc:
            raise TrainingError(
                "Dependencias Databricks ausentes. Execute `uv sync --extra databricks`."
            ) from exc

        host = settings.databricks_host.removeprefix("https://").removeprefix("http://").rstrip("/")
        table = (
            f"`{settings.databricks_catalog}`."
            f"`{settings.databricks_schema}_marts`.`feature_store_matches`"
        )
        try:
            with (
                sql.connect(
                    server_hostname=host,
                    http_path=settings.databricks_http_path,
                    access_token=settings.databricks_token,
                ) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(f"select {columns} from {table} order by match_date")
                rows = cursor.fetchall()
                names = [column[0] for column in cursor.description]
            return pd.DataFrame.from_records(rows, columns=names)
        except DatabricksSQLError as exc:
            raise TrainingError(
                "Nao foi possivel ler a feature store no Databricks. "
                "Confirme se `make databricks-build` concluiu com sucesso."
            ) from exc

    if not settings.warehouse_path.is_file():
        raise TrainingError(
            f"Warehouse nao encontrado em {settings.warehouse_path}. "
            "Execute `make dbt-build` antes."
        )

    try:
        with duckdb.connect(str(settings.warehouse_path), read_only=True) as connection:
            return connection.execute(
                f"select {columns} from {FEATURE_STORE_TABLE} order by match_date"
            ).fetchdf()
    except duckdb.Error as exc:
        raise TrainingError(
            "Nao foi possivel ler a feature store. Execute `make dbt-build` antes."
        ) from exc


def run_training(settings: Settings) -> tuple[dict[str, float], str]:
    """Treina o modelo, registra métricas e artefato no MLflow."""
    matches = load_feature_store(settings)
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
