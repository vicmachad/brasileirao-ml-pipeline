{% if target.name == "ci" %}

select
    cast(match_id as bigint) as match_id,
    cast(match_date as timestamptz) as match_date,
    status,
    cast(matchday as integer) as matchday,
    cast(home_team_id as bigint) as home_team_id,
    home_team_name,
    cast(away_team_id as bigint) as away_team_id,
    away_team_name,
    cast(home_score as integer) as home_score,
    cast(away_score as integer) as away_score
from {{ ref("matches_fixture") }}

{% elif target.type == "databricks" %}

select
    cast(match_id as bigint) as match_id,
    cast(match_date as timestamp) as match_date,
    status,
    cast(matchday as integer) as matchday,
    cast(home_team_id as bigint) as home_team_id,
    home_team_name,
    cast(away_team_id as bigint) as away_team_id,
    away_team_name,
    cast(home_score as integer) as home_score,
    cast(away_score as integer) as away_score
from {{ source("databricks_raw", "raw_matches") }}

{% else %}

with raw_matches as (
    select unnest(matches) as match_data, filename
    from read_json_auto('{{ var("raw_glob") }}', filename = true, union_by_name = true)
),

ranked_matches as (
    select
        match_data,
        row_number() over (
            partition by match_data.id
            order by filename desc
        ) as snapshot_rank
    from raw_matches
)

select
    cast(match_data.id as bigint) as match_id,
    cast(match_data.utcDate as timestamptz) as match_date,
    match_data.status as status,
    cast(match_data.matchday as integer) as matchday,
    cast(match_data.homeTeam.id as bigint) as home_team_id,
    match_data.homeTeam.name as home_team_name,
    cast(match_data.awayTeam.id as bigint) as away_team_id,
    match_data.awayTeam.name as away_team_name,
    cast(match_data.score.fullTime.home as integer) as home_score,
    cast(match_data.score.fullTime.away as integer) as away_score
from ranked_matches
where snapshot_rank = 1

{% endif %}
