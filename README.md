# brasileirao-ml-pipeline

Pipeline de dados e ML ponta a ponta sobre o **Brasileirão Série A**, com recorte no
**Coritiba**. O objetivo é prever o resultado de uma partida (vitória do mandante /
empate / vitória do visitante) usando apenas informação disponível **antes** do apito
inicial.

O projeto existe para exercitar, num escopo pequeno e auditável, as práticas que
separam um notebook de um sistema: raw layer imutável, transformações versionadas e
testadas em dbt, feature store sem vazamento temporal, experimentos rastreados e CI.

> Status: scaffold pronto. As camadas estão sendo implementadas uma a uma — veja o
> [Roadmap](#roadmap).

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
│ 5. CI/CD          │  GitHub Actions: ruff + pytest + dbt build/test em cada PR
└───────────────────┘
```

### Camadas dbt

| Camada         | Papel                                                                 |
| -------------- | --------------------------------------------------------------------- |
| `staging`      | 1:1 com a fonte. Renomeia, tipa e desaninha o JSON da API. Views.      |
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

---

## Como rodar localmente

Pré-requisitos: Python 3.10+ e um token gratuito da
[football-data.org](https://www.football-data.org/client/register).

```bash
git clone https://github.com/vicmachad/brasileirao-ml-pipeline.git
cd brasileirao-ml-pipeline

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

make install                     # instala o pacote + dbt + ferramentas de dev

cp .env.example .env             # e preencha FOOTBALL_DATA_API_TOKEN
python -m brasileirao.cli config # confere a configuração efetiva
```

Pipeline completo:

```bash
make pipeline     # ingest → dbt build → train
```

Ou passo a passo:

```bash
make ingest       # API → data/raw/
make dbt-deps     # instala pacotes dbt (uma vez)
make dbt-build    # constrói modelos e roda os testes
make train        # treina o modelo e registra o run no MLflow

mlflow ui         # abre em http://localhost:5000
```

Qualidade:

```bash
make lint         # ruff check + format
make test         # pytest
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
├── tests/                  # pytest
├── .github/workflows/ci.yml
├── Makefile
└── pyproject.toml
```

---

## Roadmap

- [x] **0.** Scaffold: estrutura, configuração, dbt, CI, README
- [ ] **1.** Ingestão: cliente football-data.org com throttle e raw layer particionada
- [ ] **2.** dbt: staging, intermediate, marts + testes
- [ ] **3.** Feature store: `feature_store_matches` com corte temporal validado
- [ ] **4.** ML: baseline + modelo, avaliação com split temporal, MLflow
- [ ] **5.** CI: seeds de fixture para `dbt build` reprodutível no CI
- [ ] **6.** README final com resultados, matriz de confusão e leitura do recorte Coritiba

---

## Licença

MIT. Dados via [football-data.org](https://www.football-data.org/), sujeitos aos termos
de uso da API.
