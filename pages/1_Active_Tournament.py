import pandas as pd
import json
import streamlit as st
from sqlalchemy import text
from data.db import engine, init_db
from services.standings import compute_standings
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

init_db()

st.set_page_config(page_title="Legends on Court Tournament - Overview", page_icon="🎾", layout="wide", initial_sidebar_state="collapsed")

## Title will be set dynamically after resolving active tournament

def get_setting(key: str):
    try:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT value FROM settings WHERE key=:k"), {"k": key}).first()
        return row[0] if row else None
    except Exception:
        return None

def set_setting(key: str, value: str):
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO settings(key, value) VALUES(:k, :v) ON CONFLICT(key) DO UPDATE SET value=:v"), {"k": key, "v": value})
    except Exception:
        pass

def get_active_tournament_id():
    v = get_setting("active_tournament_id")
    try:
        return int(v) if v not in (None, "", "null") else None
    except Exception:
        return None

def set_active_tournament_id(tid):
    set_setting("active_tournament_id", "" if tid in (None, "") else str(int(tid)))

## Title placeholder (set below after fetching active tournament)

## Tournaments block removed from Overview; selection is done on App page

active_tid = get_active_tournament_id()
# Set dynamic title based on selected tournament and show a top info card
title_text = "Overview"
card = {}
try:
    if active_tid is not None:
        tinfo = pd.read_sql(text("SELECT name, location, start_date, end_date, description, icon_path FROM tournaments WHERE tournament_id = :tid"), engine, params={"tid": active_tid})
        if not tinfo.empty:
            tname = str(tinfo.loc[0, "name"]) if "name" in tinfo.columns else "Tournament"
            tloc = str(tinfo.loc[0, "location"]) if "location" in tinfo.columns and pd.notna(tinfo.loc[0, "location"]) else ""
            title_text = f"{tname} — Overview" if not tloc else f"{tname} @ {tloc} — Overview"
            card = {
                "name": tname,
                "location": tloc,
                "start": tinfo.loc[0, "start_date"] if "start_date" in tinfo.columns else None,
                "end": tinfo.loc[0, "end_date"] if "end_date" in tinfo.columns else None,
                "desc": str(tinfo.loc[0, "description"]) if "description" in tinfo.columns and pd.notna(tinfo.loc[0, "description"]) else "",
                "icon": str(tinfo.loc[0, "icon_path"]) if "icon_path" in tinfo.columns and pd.notna(tinfo.loc[0, "icon_path"]) else "",
            }
except Exception:
    pass
st.title(title_text)
st.markdown(
    f"<div style='color:#ffffff;font-size:1.1rem;'>Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}</div>",
    unsafe_allow_html=True,
)
if st_autorefresh is not None:
    st_autorefresh(interval=10000, key="overview_auto")

# Top card mirroring the App selection card
if card:
    try:
        sd = pd.to_datetime(card.get("start")).strftime("%Y-%m-%d") if pd.notna(card.get("start")) else "TBD"
        ed = pd.to_datetime(card.get("end")).strftime("%Y-%m-%d") if pd.notna(card.get("end")) else "TBD"
    except Exception:
        sd, ed = "TBD", "TBD"
    st.markdown(
        """
        <style>
          .ov-card { display:grid; grid-template-columns: 260px 1fr; gap:18px; align-items:stretch; margin: 8px 0 18px; }
          .ov-thumb { background:#122012; border:1px solid #2a5f2a; border-radius:16px; overflow:hidden; height:220px; }
          .ov-thumb img { width:100%; height:100%; object-fit:cover; display:block; }
          .ov-body { background:#0f160f; color:#e8f6e8; border:1px solid #2a5f2a; border-radius:18px; padding:18px 20px; }
          .ov-title { font-weight:800; font-size:1.25rem; color:#9be37a; margin:4px 0 6px; }
          .ov-meta { color:#b9d0b9; font-size:0.95rem; margin:2px 0; }
          @media (max-width: 820px) { .ov-card { grid-template-columns: 1fr; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
    import os, base64
    icon = (card.get("icon") or "").replace("\\", "/")
    img_html = ""
    if icon:
        try:
            if icon.startswith("http://") or icon.startswith("https://"):
                img_html = f"<img src=\"{icon}\">"
            else:
                # Resolve relative to project root (Padellers/), not pages/
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                abs_path = icon if os.path.isabs(icon) else os.path.abspath(os.path.join(project_root, icon))
                if os.path.exists(abs_path):
                    with open(abs_path, "rb") as f:
                        data = base64.b64encode(f.read()).decode("utf-8")
                    ext = os.path.splitext(abs_path)[1].lower()
                    mime = 'image/png' if ext in ('.png', '') else ('image/jpeg' if ext in ('.jpg', '.jpeg') else 'image/png')
                    img_html = f"<img src=\"data:{mime};base64,{data}\">"
                else:
                    img_html = ""
        except Exception:
            img_html = ""
    html = [
        "<div class='ov-card'>",
        f"<div class='ov-thumb'>{img_html}</div>",
        "<div class='ov-body'>",
        f"<div class='ov-title'>{card.get('name','Tournament')}</div>",
        f"<div class='ov-meta'>📍 {card.get('location','')}</div>",
        f"<div class='ov-meta'>🗓️ {sd} — {ed}</div>",
        f"<div class='ov-meta' style='opacity:.9'>{card.get('desc','')}</div>",
        "</div>",
        "</div>",
    ]
    st.markdown("\n".join(html), unsafe_allow_html=True)
## Top card added above; refresh stays active
try:
    if active_tid is None:
        teams_df = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed FROM teams"), engine)
    else:
        try:
            teams_df = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed FROM teams WHERE tournament_id = :tid"), engine, params={"tid": active_tid})
        except Exception:
            teams_df = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed FROM teams"), engine)
except Exception:
    teams_df = pd.DataFrame(columns=["team_id", "team_name", "player1", "player2", "group", "seed"])

try:
    if active_tid is None:
        matches_df = pd.read_sql(text("SELECT match_id, \"group\", team1_id, team2_id, status, set1_t1, set1_t2, set2_t1, set2_t2, set3_t1, set3_t2 FROM matches"), engine)
    else:
        try:
            matches_df = pd.read_sql(text("SELECT match_id, \"group\", team1_id, team2_id, status, set1_t1, set1_t2, set2_t1, set2_t2, set3_t1, set3_t2 FROM matches WHERE tournament_id = :tid"), engine, params={"tid": active_tid})
        except Exception:
            matches_df = pd.read_sql(text("SELECT match_id, \"group\", team1_id, team2_id, status, set1_t1, set1_t2, set2_t1, set2_t2, set3_t1, set3_t2 FROM matches"), engine)
except Exception:
    matches_df = pd.DataFrame(columns=["match_id", "group", "team1_id", "team2_id", "status", "set1_t1", "set1_t2", "set2_t1", "set2_t2", "set3_t1", "set3_t2"])

st.markdown(
    """
    <style>
      .table-outer { width:100%; max-width:100%; }
      [data-testid="stVerticalBlock"],
      [data-testid="stHorizontalBlock"],
      [data-testid="stMarkdownContainer"],
      section.main .block-container,
      .stMarkdown { overflow: visible !important; }
      .table-wrap { width:100%; border:1px solid #1f7a1f; border-radius:4px; overflow:hidden; margin-bottom:18px; }
      .table-scroll { width:100%; overflow-x:auto !important; overflow-y:hidden; -webkit-overflow-scrolling:touch; touch-action: pan-x; overscroll-behavior-x: contain; scrollbar-width: thin; }
      .table-inner { display:inline-block; min-width:100%; }
      table.custom { width:auto; min-width:100%; border-collapse:collapse; table-layout:auto; }
      table.custom thead tr { background:#1f7a1f; color:#fff; }
      table.custom th, table.custom td { padding:8px 10px; border-bottom:1px solid #2e2e2e; text-align:left; font-size:0.95rem; white-space:nowrap; }
      table.custom tbody tr { background:#3a3a3a; color:#f0f0f0; }
      table.custom tbody tr:nth-child(even) { background:#2f2f2f; }
      .section-title { color:#1f7a1f; font-weight:700; margin: 10px 0 6px; }
      @media (max-width: 900px) {
        table.custom { min-width:720px; }
        table.custom th, table.custom td { padding:6px 8px; font-size:0.85rem; }
      }
      @media (max-width: 700px) {
        table.custom { min-width:680px; }
        table.custom th, table.custom td { padding:6px 6px; font-size:0.8rem; }
      }
      @media (max-width: 520px) {
        table.custom { min-width:640px; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

def render_table(df: pd.DataFrame, columns: list[str], headers: list[str]):
    safe_df = df.copy() if not df.empty else pd.DataFrame(columns=columns)
    safe_df = safe_df.reindex(columns=columns)
    html = [
        "<div class='table-outer'>",
        "<div class='table-wrap'>",
        "<div class='table-scroll'>",
        "<div class='table-inner'>",
        f"<table class='custom'>",
        "<thead><tr>"
    ]
    for h in headers:
        html.append(f"<th>{h}</th>")
    html.append("</tr></thead><tbody>")
    for _, r in safe_df.iterrows():
        html.append("<tr>")
        for c in columns:
            v = r.get(c, "")
            html.append(f"<td>{'' if pd.isna(v) else v}</td>")
        html.append("</tr>")
    html.append("</tbody></table></div></div></div></div>")
    st.markdown("\n".join(html), unsafe_allow_html=True)

def get_json_setting(key: str):
    try:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT value FROM settings WHERE key=:k"), {"k": key}).first()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None
    except Exception:
        return None

if not teams_df.empty:
    standings = compute_standings(teams_df, matches_df)
else:
    standings = pd.DataFrame()

played = pd.DataFrame()
if not matches_df.empty:
    mm = matches_df.copy()
    mm["has_score"] = mm[["set1_t1", "set1_t2", "set2_t1", "set2_t2", "set3_t1", "set3_t2"]].notna().any(axis=1)
    played_df = mm[(mm["status"] == "Completed") | (mm["has_score"])].copy()
    label = (
        teams_df.assign(
            _lab=(teams_df["team_name"].fillna("")
                  .where(teams_df["team_name"].fillna("").str.len() > 0,
                         teams_df["player1"].fillna("") + " vs " + teams_df["player2"].fillna("")))
        )[["team_id", "_lab"]]
        if not teams_df.empty else pd.DataFrame(columns=["team_id", "_lab"])
    )
    id2lab = dict(zip(label["team_id"], label["_lab"]))
    rows = []
    for _, m in played_df.iterrows():
        t1 = m.get("team1_id"); t2 = m.get("team2_id")
        t1l = id2lab.get(int(t1)) if pd.notna(t1) else "?"
        t2l = id2lab.get(int(t2)) if pd.notna(t2) else "?"
        t1_sets = t2_sets = 0
        gw1 = gw2 = 0
        for a, b in [
            (m.get("set1_t1"), m.get("set1_t2")),
            (m.get("set2_t1"), m.get("set2_t2")),
            (m.get("set3_t1"), m.get("set3_t2")),
        ]:
            if pd.isna(a) or pd.isna(b):
                continue
            if a > b:
                t1_sets += 1
            elif b > a:
                t2_sets += 1
            gw1 += int(a); gw2 += int(b)
        rows.append({
            "MatchId": int(m.get("match_id")) if pd.notna(m.get("match_id")) else "",
            "Court": m.get("group", ""),
            "Players": f"{t1l} vs {t2l}",
            "Sets": f"{t1_sets} - {t2_sets}",
            "Games": f"{gw1} : {gw2}",
            "Status": m.get("status", ""),
        })
    played = pd.DataFrame(rows)

st.markdown("<div class='section-title'>▶ Played Matches</div>", unsafe_allow_html=True)
played_all_cols = ["MatchId", "Court", "Players", "Sets", "Games", "Status"]
played_cols = get_json_setting("visible_cols_played") or played_all_cols
played_labels_map = get_json_setting("header_labels_played") or {}
played_headers = [played_labels_map.get(c, c) for c in played_cols]
render_table(played, played_cols, played_headers)

st.markdown("<div class='section-title'>🏆 Winner Board / Standings</div>", unsafe_allow_html=True)
leaderboard = (
    standings.sort_values(by=["points", "wins", "sets_diff", "games_diff"], ascending=[False, False, False, False])
    .reset_index(drop=True)
    if not standings.empty else pd.DataFrame()
)
if not leaderboard.empty:
    leaderboard.insert(0, "Rank", leaderboard.index + 1)
    winners = leaderboard[[
        "Rank", "team_name", "played", "wins", "losses", "points"
    ]].copy()
    winners.columns = [
        "Rank", "Team", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"
    ]
else:
    winners = pd.DataFrame(columns=["Rank", "Team", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"])

standings_all_cols = ["Rank", "Team", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"]
standings_cols = get_json_setting("visible_cols_standings") or standings_all_cols
standings_labels_map = get_json_setting("header_labels_standings") or {}
standings_headers = [standings_labels_map.get(c, c) for c in standings_cols]
render_table(winners, standings_cols, standings_headers)

# Teams roster section
st.markdown("<div class='section-title'>👥 Teams</div>", unsafe_allow_html=True)
if not teams_df.empty:
    roster = teams_df.copy()
    roster["Players"] = roster["player1"].fillna("") + ", " + roster["player2"].fillna("")
    stats = standings.set_index("team_id") if not standings.empty else pd.DataFrame().set_index(pd.Index([]))
    roster = roster.set_index("team_id")
    if not stats.empty:
        roster = roster.join(stats[["played", "wins", "losses", "points"]], how="left")
    roster = roster.reset_index()
    teams_tbl = roster[["team_name", "Players", "played", "wins", "losses", "points"]].fillna(0)
    teams_tbl.columns = ["Team", "Players", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"]
else:
    teams_tbl = pd.DataFrame(columns=["Team", "Players", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"])

teams_all_cols = ["Team", "Players", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"]
teams_cols = get_json_setting("visible_cols_teams") or teams_all_cols
teams_labels_map = get_json_setting("header_labels_teams") or {}
teams_headers = [teams_labels_map.get(c, c) for c in teams_cols]
render_table(teams_tbl, teams_cols, teams_headers)
