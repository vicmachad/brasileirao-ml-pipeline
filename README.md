# brasileirao-ml-pipeline

Pipeline de dados e ML ponta a ponta sobre o **Brasileirão Série A**, com recorte no
**Coritiba**. O objetivo é prever o resultado de uma partida (vitória do mandante /
empate / vitória do visitante) usando apenas informação disponível **antes** do apito
inicial.

O projeto existe para exercitar, num escopo pequeno e auditável, as práticas que
separam um notebook de um sistema: raw layer imutável, transformações versionadas e
testadas em dbt, feature store sem vazamento temporal, experimentos rastreados e CI.

> Status: ingestão, transformações dbt, feature store e treino inicial estão
> implementados. `make pipeline` consulta a API e precisa de `FOOTBALL_DATA_API_TOKEN`
> configurado no `.env`.

---

## Arquitetura

```
football-data.org (API pública, competição BSA)
        │
        ▼
┌───────────────────┐
│ 1. Ingestão       │  Python + requests → JSON bruto, particionado por data
│    src/.../ingestion   data/raw/                    (imutável, append-only)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 2. Transformação  │  dbt Core + DuckDB
│    dbt/models/         staging → intermediate → marts
│                        + dbt tests (not_null, unique, relationships)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 3. Feature store  │  mart final: 1 linha por partida, features calculadas
│    marts/              com corte temporal estrito (as-of the match date)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 4. Modelo de ML   │  scikit-learn (classificação 3 classes)
│    src/.../ml          + MLflow: params, métricas, artefato do modelo
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 5. CI/CD          │  GitHub Actions: ruff + pytest + dbt build/test + build
└───────────────────┘  da imagem Docker, em cada PR
```

Tudo roda de duas formas equivalentes: **local com [uv](https://docs.astral.sh/uv/)**
ou **em containers com Docker Compose**. As duas partem do mesmo `uv.lock`, então o
ambiente é idêntico.

### Camadas dbt

| Camada         | Papel                                                                 |
| -------------- | --------------------------------------------------------------------- |
| `staging`      | Tipagem e deduplicação dos snapshots JSON da API. Tabelas dbt.      |
| `intermediate` | Lógica reutilizável: partidas em formato *long* (uma linha por time por jogo), forma recente, mando de campo, confrontos diretos. |
| `marts`        | `fct_matches` (grão: partida) e `feature_store_matches` (grão: partida, pronto para o modelo). |

---

## Decisões técnicas

**DuckDB como engine.** O dataset é pequeno (algumas milhares de partidas). DuckDB dá
SQL analítico completo, roda como um arquivo local, e permite que o CI reconstrua o
warehouse inteiro do zero em segundos — sem credencial de nuvem e sem custo. A mesma
modelagem dbt sobe para Snowflake/BigQuery trocando o adapter.

**dbt para a transformação, não pandas.** A lógica de negócio (o que é "forma
recente", como se conta um confronto direto) fica declarativa, versionada e testada.
`dbt test` é a rede de segurança que um script de feature engineering em pandas não
tem.

**Feature store com corte temporal explícito.** Toda feature de uma partida em `t` é
calculada com janelas que terminam em `t-1`. Isso é o ponto mais fácil de errar num
projeto de futebol — usar a tabela final do campeonato como feature vaza o futuro
inteiro para dentro do treino. As window functions são escritas com
`ROWS BETWEEN ... PRECEDING AND 1 PRECEDING` e cobertas por testes dbt.

**Split temporal, não aleatório.** Validação por temporada/rodada, não `train_test_split`
embaralhado — o modelo é avaliado como seria usado: prevendo rodadas que ainda não viu.

**MLflow local (backend de arquivo).** Rastreia experimentos sem exigir servidor.
Suficiente para comparar runs e versionar o modelo; a migração para um tracking server
remoto é uma variável de ambiente.

**football-data.org, free tier.** API pública, estável, com histórico do Brasileirão.
Limite de 10 req/min — a ingestão respeita isso com throttle e grava a resposta crua
antes de qualquer parsing, para que a raw layer seja sempre reprocessável.

**dbt fixado na série 1.12** (`dbt-core~=1.12.0`, `dbt-duckdb~=1.11.0`). O pin `~=` deixa
patches entrarem e exige decisão explícita para mudar de minor. Ficar numa série
suportada importa: a 1.8 já está depreciada e emite aviso a cada comando. O
`package-lock.yml` do dbt também é commitado, fixando a versão do `dbt_utils`.

**uv para dependências, com lock commitado.** `uv.lock` fixa a árvore inteira, e o CI
roda `uv sync --frozen` — se o lock divergir do `pyproject.toml`, o build falha em vez
de resolver versões silenciosamente. O uv também provisiona o próprio Python 3.11, o
que elimina a divergência entre a máquina local, o container e o CI.

**Docker com build em dois estágios.** O estágio de build usa a imagem oficial do uv e
monta `uv.lock`/`pyproject.toml` como bind mount, então a camada de dependências só
invalida quando o lock muda. O estágio final carrega apenas o runtime e a `.venv`
pronta, roda como usuário não-root, e recebe `data/` e `mlruns/` como bind mounts — o
estado do pipeline sobrevive ao container e continua inspecionável do host.

**MLflow com backend SQLite, não file store.** O MLflow 3.x colocou o backend de
arquivo (`./mlruns`) em modo de manutenção e recusa iniciar sobre ele. SQLite não exige
serviço externo e é pré-requisito do model registry.

---

## Como rodar

Em ambos os caminhos, comece pelo token gratuito da
[football-data.org](https://www.football-data.org/client/register):

```bash
git clone https://github.com/vicmachad/brasileirao-ml-pipeline.git
cd brasileirao-ml-pipeline
cp .env.example .env      # e preencha FOOTBALL_DATA_API_TOKEN
```

### Opção A — local com uv

Único pré-requisito é o [uv](https://docs.astral.sh/uv/getting-started/installation/);
ele baixa o Python 3.11 e monta a `.venv` sozinho.

```bash
make install              # uv sync (respeita o uv.lock)
uv run brasileirao config # confere a configuração efetiva

make pipeline             # ingest → dbt build → train
```

Ou passo a passo:

```bash
make ingest               # API → data/raw/
make dbt-deps             # instala pacotes dbt (uma vez)
make dbt-build            # constrói modelos e roda os testes
make train                # treina e registra o run no MLflow
```

Para validar as transformações sem consultar a API, use os dados determinísticos
do CI: `make dbt-build DBT_TARGET=ci`. O treino usa partidas concluídas do warehouse
gerado pelo dbt e faz uma validação temporal 80/20.

### Databricks SQL Warehouse (opcional)

O DuckDB continua sendo o padrão local. Para executar ingestão, dbt e treino
usando um Databricks SQL Warehouse:

1. Instale o adapter opcional: `make install-databricks`.
2. No `.env`, configure `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH` e
   `DATABRICKS_TOKEN`. O `HTTP_PATH` é o valor exibido em **Connection details**,
   não a URL da página do Warehouse (para SQL Warehouse, o formato usual é
   `/sql/1.0/warehouses/<warehouse-id>`). Nunca versione nem compartilhe o token.
3. Configure `DATABRICKS_CATALOG` e, se necessário, ajuste
   `DATABRICKS_SCHEMA`/`DATABRICKS_RAW_SCHEMA`.
4. Valide o acesso com `make databricks-debug`; depois execute
   `make databricks-pipeline`.

A ingestão mantém o snapshot JSON local e sincroniza as partidas numa tabela Delta
`raw_matches`; o dbt constrói staging, marts e feature store no Databricks. O treino
lê a feature store remota e continua registrando o modelo no MLflow local.

### Opção B — Docker Compose

Três serviços sobre a mesma imagem: `pipeline` (CLI Python), `dbt` e `mlflow` (UI).

```bash
make docker-build                        # docker compose build

docker compose run --rm pipeline ingest  # camada 1
docker compose run --rm dbt build        # camadas 2 e 3 (+ dbt tests)
docker compose run --rm pipeline train   # camada 4

make docker-pipeline                     # ou os três de uma vez
```

MLflow UI em [http://localhost:5000](http://localhost:5000):

```bash
make mlflow-up
make mlflow-down
```

`data/` e `mlruns/` são bind mounts — o resultado de um run em container fica
disponível no host, e vice-versa.

### Qualidade

```bash
make lint     # ruff check + format --check
make format   # aplica as correções
make test     # pytest
```

---

## Estrutura do repositório

```
.
├── src/brasileirao/
│   ├── config.py           # configuração central (pydantic-settings)
│   ├── cli.py              # entrypoint único: ingest / train / predict
│   ├── ingestion/          # cliente da API + escrita na raw layer
│   ├── features/           # leitura do feature store a partir do DuckDB
│   └── ml/                 # treino, avaliação, tracking MLflow
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml        # DuckDB local (sem segredos, versionado)
│   ├── models/{staging,intermediate,marts}/
│   └── seeds/              # fixtures determinísticas usadas pelo CI
├── data/
│   ├── raw/                # JSON bruto da API (gitignored)
│   └── warehouse/          # arquivo DuckDB (gitignored)
├── mlruns/                 # backend SQLite + artefatos MLflow (gitignored)
├── tests/                  # pytest
├── .github/workflows/ci.yml
├── Dockerfile              # build em dois estágios com uv
├── docker-compose.yml      # serviços pipeline / dbt / mlflow
├── Makefile                # atalhos local (uv) e Docker
├── pyproject.toml
└── uv.lock                 # árvore de dependências fixada (commitado)
```

---

## Roadmap

- [x] **0.** Scaffold: estrutura, uv, dbt, Docker Compose, CI, README
- [x] **1.** Ingestão: cliente football-data.org e raw layer particionada
- [x] **2.** dbt: staging, intermediate, marts + testes
- [x] **3.** Feature store: `feature_store_matches` com corte temporal validado
- [x] **4.** ML: modelo inicial, avaliação com split temporal, MLflow
- [x] **5.** CI: seed de fixture para `dbt build` reprodutível no CI
- [ ] **6.** README final com resultados, matriz de confusão e leitura do recorte Coritiba

---

## Licença

MIT. Dados via [football-data.org](https://www.football-data.org/), sujeitos aos termos
de uso da API.
