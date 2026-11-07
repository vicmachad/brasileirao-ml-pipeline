select
    match_id,
    match_date,
    matchday,
    home_team_id,
    home_team_name,
    away_team_id,
    away_team_name,
    home_score,
    away_score,
    case
        when home_score > away_score then 'home_win'
        when home_score = away_score then 'draw'
        else 'away_win'
    end as outcome
from {{ ref("stg_matches") }}
where status in ('FINISHED', 'AWARDED')
  and home_score is not null
  and away_score is not null
