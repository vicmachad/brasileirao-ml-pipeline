# syntax=docker/dockerfile:1.7
# Build em dois estagios: o primeiro resolve o ambiente com uv, o segundo
# carrega apenas o runtime + a .venv pronta.

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Camada de dependencias: so invalida quando uv.lock ou pyproject.toml mudam.
# --frozen garante que o lock e respeitado a risca (build reproduzivel).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Camada do projeto.
COPY src ./src
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.11-slim-bookworm AS runtime

# git e exigido pelo `dbt deps` para instalar pacotes do dbt Hub.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src ./src
COPY --chown=app:app dbt ./dbt
COPY --chown=app:app pyproject.toml README.md ./

# Diretorios montados como volume no compose; criados aqui para que existam
# tambem quando a imagem roda sem compose.
RUN mkdir -p /app/data/raw /app/data/warehouse /app/mlruns/artifacts \
    && chown -R app:app /app/data /app/mlruns

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DBT_PROFILES_DIR=/app/dbt \
    PROJECT_ROOT=/app \
    RAW_DIR=/app/data/raw \
    DUCKDB_PATH=/app/data/warehouse/brasileirao.duckdb \
    MLFLOW_TRACKING_URI=sqlite:////app/mlruns/mlflow.db \
    MLFLOW_ARTIFACT_ROOT=/app/mlruns/artifacts

USER app

ENTRYPOINT ["brasileirao"]
CMD ["config"]
