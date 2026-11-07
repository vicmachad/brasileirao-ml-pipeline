with completed_matches as (
    select *
    from {{ ref("stg_matches") }}
    where status in ('FINISHED', 'AWARDED')
      and home_score is not null
      and away_score is not null
),

team_matches as (
    select
        match_id,
        match_date,
        home_team_id as team_id,
        case
            when home_score > away_score then 3
            when home_score = away_score then 1
            else 0
        end as points,
        home_score as goals_for,
        away_score as goals_against
    from completed_matches

    union all

    select
        match_id,
        match_date,
        away_team_id as team_id,
        case
            when away_score > home_score then 3
            when away_score = home_score then 1
            else 0
        end as points,
        away_score as goals_for,
        home_score as goals_against
    from completed_matches
),

form as (
    select
        *,
        avg(points) over (
            partition by team_id
            order by match_date, match_id
            rows between {{ var("form_window") }} preceding and 1 preceding
        ) as avg_points_prior,
        avg(goals_for) over (
            partition by team_id
            order by match_date, match_id
            rows between {{ var("form_window") }} preceding and 1 preceding
        ) as avg_goals_for_prior,
        avg(goals_against) over (
            partition by team_id
            order by match_date, match_id
            rows between {{ var("form_window") }} preceding and 1 preceding
        ) as avg_goals_against_prior
    from team_matches
)

select *
from form
