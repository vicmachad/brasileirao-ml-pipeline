select
    matches.match_id,
    matches.match_date,
    matches.matchday,
    matches.home_team_id,
    matches.home_team_name,
    matches.away_team_id,
    matches.away_team_name,
    matches.home_score,
    matches.away_score,
    matches.outcome,
    coalesce(home_form.avg_points_prior, 0.0) as home_avg_points_prior,
    coalesce(home_form.avg_goals_for_prior, 0.0) as home_avg_goals_for_prior,
    coalesce(home_form.avg_goals_against_prior, 0.0) as home_avg_goals_against_prior,
    coalesce(away_form.avg_points_prior, 0.0) as away_avg_points_prior,
    coalesce(away_form.avg_goals_for_prior, 0.0) as away_avg_goals_for_prior,
    coalesce(away_form.avg_goals_against_prior, 0.0) as away_avg_goals_against_prior
from {{ ref("fct_matches") }} as matches
left join {{ ref("int_team_match_form") }} as home_form
    on matches.match_id = home_form.match_id
    and matches.home_team_id = home_form.team_id
left join {{ ref("int_team_match_form") }} as away_form
    on matches.match_id = away_form.match_id
    and matches.away_team_id = away_form.team_id
