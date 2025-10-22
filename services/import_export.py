import io
import pandas as pd

TEAMS_COLUMNS = ["team_id", "team_name", "player1", "player2", "group", "seed"]
MATCHES_COLUMNS = [
    "match_id", "group", "team1_id", "team2_id", "status",
    "set1_t1", "set1_t2", "set2_t1", "set2_t2", "set3_t1", "set3_t2"
]

STATUS_VALUES = ["Scheduled", "In Progress", "Completed"]


def create_template_excel() -> bytes:
    teams_df = pd.DataFrame(columns=TEAMS_COLUMNS)
    matches_df = pd.DataFrame(columns=MATCHES_COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        teams_df.to_excel(writer, sheet_name="Teams", index=False)
        matches_df.to_excel(writer, sheet_name="Matches", index=False)
    buf.seek(0)
    return buf.getvalue()


def validate_excel(xl: pd.ExcelFile) -> tuple[bool, str | None]:
    sheets = xl.sheet_names
    if "Teams" not in sheets:
        return False, "Missing 'Teams' sheet"
    if "Matches" not in sheets:
        return False, "Missing 'Matches' sheet"
    teams_df = xl.parse("Teams")
    matches_df = xl.parse("Matches")
    missing_teams_cols = [c for c in TEAMS_COLUMNS if c not in teams_df.columns]
    if missing_teams_cols:
        return False, f"Teams sheet missing columns: {missing_teams_cols}"
    missing_matches_cols = [c for c in MATCHES_COLUMNS if c not in matches_df.columns]
    if missing_matches_cols:
        return False, f"Matches sheet missing columns: {missing_matches_cols}"
    return True, None


def load_excel(file_bytes: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    ok, err = validate_excel(xl)
    if not ok:
        raise ValueError(err)
    teams_df = xl.parse("Teams")
    matches_df = xl.parse("Matches")
    for c in ["team_id", "seed"]:
        if c in teams_df.columns:
            teams_df[c] = pd.to_numeric(teams_df[c], errors="coerce").astype("Int64")
    for c in ["match_id", "team1_id", "team2_id", "set1_t1", "set1_t2", "set2_t1", "set2_t2", "set3_t1", "set3_t2"]:
        if c in matches_df.columns:
            matches_df[c] = pd.to_numeric(matches_df[c], errors="coerce").astype("Int64")
    if "status" in matches_df.columns:
        matches_df["status"] = matches_df["status"].fillna("Scheduled")
        matches_df.loc[~matches_df["status"].isin(STATUS_VALUES), "status"] = "Scheduled"
    return teams_df, matches_df


def export_excel_bytes(teams_df: pd.DataFrame, matches_df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        teams_df = teams_df.reindex(columns=TEAMS_COLUMNS)
        matches_df = matches_df.reindex(columns=MATCHES_COLUMNS)
        teams_df.to_excel(writer, sheet_name="Teams", index=False)
        matches_df.to_excel(writer, sheet_name="Matches", index=False)
    buf.seek(0)
    return buf.getvalue()
