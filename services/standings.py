import pandas as pd

def compute_match_result(row: pd.Series) -> tuple[int, int]:
    t1_sets = 0
    t2_sets = 0
    for a, b in [
        (row.get("set1_t1"), row.get("set1_t2")),
        (row.get("set2_t1"), row.get("set2_t2")),
        (row.get("set3_t1"), row.get("set3_t2")),
    ]:
        if pd.isna(a) or pd.isna(b):
            continue
        if a > b:
            t1_sets += 1
        elif b > a:
            t2_sets += 1
    return t1_sets, t2_sets


def compute_standings(teams_df: pd.DataFrame, matches_df: pd.DataFrame) -> pd.DataFrame:
    base = teams_df[["team_id", "team_name", "group"]].copy()
    base["played"] = 0
    base["wins"] = 0
    base["losses"] = 0
    base["sets_won"] = 0
    base["sets_lost"] = 0
    base["games_won"] = 0
    base["games_lost"] = 0
    base["points"] = 0

    for _, m in matches_df.iterrows():
        t1 = m.get("team1_id"); t2 = m.get("team2_id")
        if pd.isna(t1) or pd.isna(t2):
            continue
        t1 = int(t1); t2 = int(t2)
        t1_sets, t2_sets = compute_match_result(m)
        if t1_sets == 0 and t2_sets == 0:
            continue
        gw1 = 0; gw2 = 0
        for a, b in [
            (m.get("set1_t1"), m.get("set1_t2")),
            (m.get("set2_t1"), m.get("set2_t2")),
            (m.get("set3_t1"), m.get("set3_t2")),
        ]:
            if pd.isna(a) or pd.isna(b):
                continue
            gw1 += int(a); gw2 += int(b)
        base.loc[base["team_id"] == t1, "played"] += 1
        base.loc[base["team_id"] == t2, "played"] += 1
        base.loc[base["team_id"] == t1, "sets_won"] += t1_sets
        base.loc[base["team_id"] == t1, "sets_lost"] += t2_sets
        base.loc[base["team_id"] == t1, "games_won"] += gw1
        base.loc[base["team_id"] == t1, "games_lost"] += gw2
        base.loc[base["team_id"] == t2, "sets_won"] += t2_sets
        base.loc[base["team_id"] == t2, "sets_lost"] += t1_sets
        base.loc[base["team_id"] == t2, "games_won"] += gw2
        base.loc[base["team_id"] == t2, "games_lost"] += gw1
        if t1_sets > t2_sets:
            base.loc[base["team_id"] == t1, "wins"] += 1
            base.loc[base["team_id"] == t2, "losses"] += 1
            base.loc[base["team_id"] == t1, "points"] += 3
        elif t2_sets > t1_sets:
            base.loc[base["team_id"] == t2, "wins"] += 1
            base.loc[base["team_id"] == t1, "losses"] += 1
            base.loc[base["team_id"] == t2, "points"] += 3

    base["sets_diff"] = base["sets_won"] - base["sets_lost"]
    base["games_diff"] = base["games_won"] - base["games_lost"]

    base = base.sort_values(
        by=["group", "points", "wins", "sets_diff", "games_diff"], ascending=[True, False, False, False, False]
    ).reset_index(drop=True)
    return base
