import hashlib
import json
import bcrypt
import secrets
import pandas as pd
import streamlit as st
from sqlalchemy import text
from sqlalchemy.orm import Session
from data.db import engine, SessionLocal, init_db
from services.import_export import create_template_excel, load_excel, export_excel_bytes

init_db()

st.title("Organizer")

with SessionLocal() as db:
    db.execute(text("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"))
    db.commit()

with SessionLocal() as db:
    row = db.execute(text("SELECT value FROM settings WHERE key='admin_password_hash'"))
    row = row.first()
    stored_hash = row[0] if row and row[0] not in (None, "") else None
    pwd_set = stored_hash is not None
    tok_row = db.execute(text("SELECT value FROM settings WHERE key='admin_auto_token_hash'"))
    tok_row = tok_row.first()
    stored_token_hash = tok_row[0] if tok_row and tok_row[0] not in (None, "") else None

def set_setting(key: str, value: str):
    with SessionLocal() as db:
        db.execute(text("INSERT INTO settings(key, value) VALUES(:k, :v) ON CONFLICT(key) DO UPDATE SET value=:v"), {"k": key, "v": value})
        db.commit()

if not pwd_set:
    st.subheader("Set Admin Password")
    p1 = st.text_input("Password", type="password")
    p2 = st.text_input("Confirm Password", type="password")
    if st.button("Save Password"):
        if not p1:
            st.error("Password cannot be empty")
        elif p1 != p2:
            st.error("Passwords do not match")
        else:
            # store as bcrypt
            hashed = bcrypt.hashpw(p1.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            set_setting('admin_password_hash', hashed)
            st.success("Admin password set")
else:
    # If password is set, require login unless session says authed
    # Auto-login via session token or query param token if present and valid
    if not st.session_state.get("admin_authed", False):
        try:
            # 1) session-state token
            sess_tok = st.session_state.get("org_token")
            if sess_tok and stored_token_hash:
                if hashlib.sha256(sess_tok.encode("utf-8")).hexdigest() == stored_token_hash:
                    st.session_state["admin_authed"] = True
                    # ensure query param present so deep links keep working
                    try:
                        st.query_params["org"] = sess_tok
                    except Exception:
                        pass
            # 2) query param token
            if not st.session_state.get("admin_authed", False):
                qp = dict(getattr(st, "query_params", {}))
                raw = qp.get("org")
                org_token = raw[0] if isinstance(raw, list) else raw
                if org_token and stored_token_hash:
                    candidate = hashlib.sha256(org_token.encode("utf-8")).hexdigest()
                    if candidate == stored_token_hash:
                        st.session_state["admin_authed"] = True
                        st.session_state["org_token"] = org_token
        except Exception:
            pass

    if not st.session_state.get("admin_authed", False):
        st.subheader("Organizer Login")
        lp = st.text_input("Password", type="password")
        remember = st.checkbox("Remember this session", value=True)
        if st.button("Login"):
            ok = False
            try:
                if stored_hash and stored_hash.startswith("$2b$"):
                    ok = bcrypt.checkpw(lp.encode("utf-8"), stored_hash.encode("utf-8"))
                else:
                    # legacy sha256 compare then upgrade to bcrypt
                    legacy = hashlib.sha256(lp.encode("utf-8")).hexdigest()
                    ok = (legacy == stored_hash)
                    if ok:
                        new_hash = bcrypt.hashpw(lp.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                        set_setting('admin_password_hash', new_hash)
            except Exception:
                ok = False
            if ok:
                st.session_state["admin_authed"] = True
                # Handle persistent remember via signed token in query params (stored hashed in DB)
                try:
                    if remember:
                        token = secrets.token_urlsafe(24)
                        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                        set_setting('admin_auto_token_hash', token_hash)
                        st.session_state["org_token"] = token
                        try:
                            st.query_params["org"] = token
                        except Exception:
                            try:
                                st.experimental_set_query_params(org=token)
                            except Exception:
                                pass
                    else:
                        set_setting('admin_auto_token_hash', "")
                        st.session_state.pop("org_token", None)
                        try:
                            st.query_params.pop("org", None)
                        except Exception:
                            try:
                                st.experimental_set_query_params()
                            except Exception:
                                pass
                except Exception:
                    pass
                st.success("Logged in")
                st.rerun()
            else:
                st.error("Invalid password")
        st.stop()
    else:
        # Logout button when authenticated
        colA, colB = st.columns([1,3])
        with colA:
            if st.button("Logout"):
                st.session_state.pop("admin_authed", None)
                try:
                    set_setting('admin_auto_token_hash', "")
                    st.session_state.pop("org_token", None)
                    st.query_params.clear()
                except Exception:
                    try:
                        st.experimental_set_query_params()
                    except Exception:
                        pass
                st.success("Logged out")
                st.rerun()
        with colB:
            st.caption("You are logged in as Organizer.")

st.subheader("Data Management")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Download Excel Template"):
        st.download_button(
            label="Download",
            data=create_template_excel(),
            file_name="padel_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
with col2:
    up = st.file_uploader("Upload Excel (Teams & Matches)", type=["xlsx"])
    if up is not None:
        try:
            teams_df, matches_df = load_excel(up.read())
            with engine.begin() as conn:
                teams_df.to_sql("teams", conn, if_exists="replace", index=False)
                matches_df.to_sql("matches", conn, if_exists="replace", index=False)
            st.success("Data imported")
        except Exception as e:
            st.error(f"Failed to import: {e}")
with col3:
    try:
        with engine.begin() as conn:
            tdf = pd.read_sql(text("SELECT COUNT(*) as c FROM teams"), conn)
            mdf = pd.read_sql(text("SELECT COUNT(*) as c FROM matches"), conn)
        st.metric("Teams", int(tdf["c"][0]))
        st.metric("Matches", int(mdf["c"][0]))
    except Exception:
        st.metric("Teams", 0)
        st.metric("Matches", 0)

st.subheader("Export")
if st.button("Export Excel"):
    try:
        with engine.begin() as conn:
            teams_df = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed FROM teams"), conn)
            matches_df = pd.read_sql(text("SELECT match_id, \"group\", team1_id, team2_id, status, set1_t1, set1_t2, set2_t1, set2_t2, set3_t1, set3_t2 FROM matches"), conn)
        st.download_button(
            label="Download Export",
            data=export_excel_bytes(teams_df, matches_df),
            file_name="padel_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.error(f"Failed to export: {e}")

def get_setting(key: str):
    with SessionLocal() as db:
        row = db.execute(text("SELECT value FROM settings WHERE key=:k"), {"k": key}).first()
        return row[0] if row else None

def set_setting(key: str, value: str):
    with SessionLocal() as db:
        db.execute(text("INSERT INTO settings(key, value) VALUES(:k, :v) ON CONFLICT(key) DO UPDATE SET value=:v"), {"k": key, "v": value})
        db.commit()

def get_json_setting(key: str):
    val = get_setting(key)
    if not val:
        return None
    try:
        return json.loads(val)
    except Exception:
        return None

def set_json_setting(key: str, obj):
    try:
        set_setting(key, json.dumps(obj))
    except Exception:
        set_setting(key, str(obj))

def get_active_tournament_id():
    v = get_setting("active_tournament_id")
    try:
        return int(v) if v not in (None, "", "null") else None
    except Exception:
        return None

def set_active_tournament_id(tid: int | None):
    set_setting("active_tournament_id", "" if tid is None else str(int(tid)))

# Active tournament selector (global for Admin)
with engine.begin() as conn:
    try:
        tournaments_list = pd.read_sql(
            text("SELECT tournament_id, name, start_date FROM tournaments ORDER BY (start_date IS NULL), start_date, tournament_id"),
            conn,
        )
    except Exception:
        tournaments_list = pd.DataFrame(columns=["tournament_id", "name", "start_date"])

cur_tid = get_active_tournament_id()
valid = tournaments_list.copy()
valid["tid_int"] = pd.to_numeric(valid.get("tournament_id"), errors="coerce")
valid = valid[valid["tid_int"].notna()]
ids = valid["tid_int"].astype(int).tolist()
names = valid.get("name", pd.Series(dtype=str)).fillna("").astype(str).tolist()
opts = ["-- none --"] + [f"{tid} — {name}" for tid, name in zip(ids, names)]
default_index = 0
if cur_tid is not None and cur_tid in ids:
    default_index = 1 + ids.index(cur_tid)
sel = st.selectbox("Active tournament", options=opts, index=int(default_index), key="admin_active_tid")
def _parse_tid(s: str):
    if not s or s == "-- none --":
        return None
    try:
        return int(s.split(" — ")[0])
    except Exception:
        return None
new_tid = _parse_tid(sel)
if new_tid != cur_tid:
    set_active_tournament_id(new_tid)
    st.success("Active tournament updated for Admin.")
    st.rerun()

tabs = st.tabs(["Data", "Tournaments", "Teams", "Scheduler", "Scoring", "Display"]) 

with tabs[0]:
    st.subheader("Data Management")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("Download Excel Template", key="dl_tpl"):
            st.download_button(
                label="Download",
                data=create_template_excel(),
                file_name="padel_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_btn",
            )
    with col2:
        up = st.file_uploader("Upload Excel (Teams & Matches)", type=["xlsx"], key="up_xlsx")
        if up is not None:
            try:
                teams_df, matches_df = load_excel(up.read())
                with engine.begin() as conn:
                    teams_df.to_sql("teams", conn, if_exists="replace", index=False)
                    matches_df.to_sql("matches", conn, if_exists="replace", index=False)
                st.success("Data imported")
            except Exception as e:
                st.error(f"Failed to import: {e}")
    with col3:
        try:
            with engine.begin() as conn:
                tdf = pd.read_sql(text("SELECT COUNT(*) as c FROM teams"), conn)
                mdf = pd.read_sql(text("SELECT COUNT(*) as c FROM matches"), conn)
            st.metric("Teams", int(tdf["c"][0]))
            st.metric("Matches", int(mdf["c"][0]))
        except Exception:
            st.metric("Teams", 0)
            st.metric("Matches", 0)

    st.subheader("Export")
    if st.button("Export Excel", key="export_xlsx"):
        try:
            with engine.begin() as conn:
                teams_df = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed FROM teams"), conn)
                matches_df = pd.read_sql(text("SELECT match_id, \"group\", team1_id, team2_id, status, set1_t1, set1_t2, set2_t1, set2_t2, set3_t1, set3_t2 FROM matches"), conn)
            st.download_button(
                label="Download Export",
                data=export_excel_bytes(teams_df, matches_df),
                file_name="padel_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="export_btn",
            )
        except Exception as e:
            st.error(f"Failed to export: {e}")

with tabs[1]:
    st.subheader("Tournaments")
    st.caption("Manage tournaments (name, location, dates).")
    # Load tournaments
    with engine.begin() as conn:
        try:
            t_df = pd.read_sql(text("SELECT tournament_id, name, location, start_date, end_date, description, icon_path FROM tournaments"), conn, parse_dates=["start_date", "end_date"])
        except Exception:
            t_df = pd.DataFrame(columns=["tournament_id", "name", "location", "start_date", "end_date", "description", "icon_path"])

    colf1, colf2 = st.columns([2,1])
    with colf1:
        edited_t = st.data_editor(
            t_df,
            use_container_width=True,
            num_rows="dynamic",
            key="tournaments_editor",
            column_config={
                "tournament_id": st.column_config.NumberColumn("ID", step=1, min_value=1),
                "name": st.column_config.TextColumn("Name"),
                "location": st.column_config.TextColumn("Location"),
                "start_date": st.column_config.DateColumn("Start Date"),
                "end_date": st.column_config.DateColumn("End Date"),
                "description": st.column_config.TextColumn("Description"),
                "icon_path": st.column_config.TextColumn("Icon Path", help="Auto-set when an image is uploaded", disabled=True),
            },
            hide_index=True,
        )
        if st.button("Save Tournaments", key="save_tournaments"):
            with engine.begin() as conn:
                edited_t.to_sql("tournaments", conn, if_exists="replace", index=False)
            st.success("Tournaments saved.")
            st.rerun()
    with colf2:
        st.markdown("### Add Tournament")
        with st.form("add_tournament_form"):
            tid = st.number_input("ID", min_value=1, step=1, key="t_add_id")
            nm = st.text_input("Name", key="t_add_name")
            loc = st.text_input("Location", key="t_add_loc")
            sd = st.date_input("Start Date", key="t_add_sd")
            ed = st.date_input("End Date", key="t_add_ed")
            desc = st.text_area("Description", key="t_add_desc")
            ok = st.form_submit_button("Add")
            if ok:
                if not nm:
                    st.error("Name is required.")
                elif tid in (t_df.get("tournament_id").tolist() if not t_df.empty else []):
                    st.error("ID already exists.")
                else:
                    new_row = pd.DataFrame([{
                        "tournament_id": int(tid),
                        "name": nm,
                        "location": loc,
                        "start_date": pd.to_datetime(sd),
                        "end_date": pd.to_datetime(ed),
                        "description": desc,
                    }])
                    out = pd.concat([t_df, new_row], ignore_index=True)
                    with engine.begin() as conn:
                        out.to_sql("tournaments", conn, if_exists="replace", index=False)
                    st.success("Tournament added.")
                    st.rerun()

    st.markdown("---")
    st.markdown("#### Tournament Icon Upload (Admins)")
    st.caption("Upload an image per tournament. PNG/JPG supported.")
    if t_df.empty:
        st.info("No tournaments yet.")
    else:
        import os
        media_dir = os.path.join(os.path.dirname(__file__), "..", "tournament_media")
        media_dir = os.path.abspath(media_dir)
        os.makedirs(media_dir, exist_ok=True)
        for _, row in t_df.iterrows():
            tid = int(row["tournament_id"]) if not pd.isna(row["tournament_id"]) else None
            name = row.get("name", "")
            if tid is None:
                continue
            with st.expander(f"{tid} — {name}"):
                colu1, colu2 = st.columns([2,1])
                with colu1:
                    upf = st.file_uploader("Upload icon (PNG/JPG)", type=["png", "jpg", "jpeg"], key=f"upl_{tid}")
                    if upf is not None and st.button("Upload", key=f"btn_upl_{tid}"):
                        ext = os.path.splitext(upf.name)[1].lower() or ".png"
                        fname = f"t_{tid}{ext}"
                        fpath = os.path.join(media_dir, fname)
                        try:
                            with open(fpath, "wb") as f:
                                f.write(upf.read())
                            rel_path = os.path.relpath(fpath, start=os.path.dirname(os.path.dirname(__file__)))
                            with engine.begin() as conn:
                                try:
                                    conn.execute(text("ALTER TABLE tournaments ADD COLUMN IF NOT EXISTS icon_path TEXT"))
                                except Exception:
                                    pass
                                conn.execute(text("UPDATE tournaments SET icon_path=:p WHERE tournament_id=:tid"), {"p": rel_path.replace("\\", "/"), "tid": tid})
                            st.success("Icon uploaded.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save icon: {e}")
                with colu2:
                    try:
                        existing = row.get("icon_path")
                        if existing and isinstance(existing, str):
                            st.image(existing, caption="Current", use_container_width=True)
                    except Exception:
                        pass

    st.markdown("---")
    with st.expander("Danger Zone — Delete Tournaments"):
        st.warning("Deleting tournaments cannot be undone.")
        coldz1, coldz2 = st.columns(2)
        with coldz1:
            # Delete selected tournament and its related data
            try:
                opts = [f"{int(r.tournament_id)} — {r.name}" for _, r in t_df.iterrows()] if not t_df.empty else []
            except Exception:
                opts = []
            sel = st.selectbox("Select tournament to delete", options=["-- pick --"] + opts, key="dz_sel")
            cascade = st.checkbox("Also delete Teams and Matches for this tournament", value=True, key="dz_cascade_one")
            if st.button("Delete selected tournament", type="primary", key="dz_delete_one") and sel != "-- pick --":
                try:
                    tid = int(str(sel).split(" — ")[0])
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM tournaments WHERE tournament_id=:tid"), {"tid": tid})
                        if cascade:
                            try:
                                conn.execute(text("DELETE FROM teams WHERE tournament_id=:tid"), {"tid": tid})
                            except Exception:
                                pass
                            try:
                                conn.execute(text("DELETE FROM matches WHERE tournament_id=:tid"), {"tid": tid})
                            except Exception:
                                pass
                    # Reset active tournament if it was the one deleted
                    cur_tid = get_active_tournament_id()
                    if cur_tid == tid:
                        set_active_tournament_id(None)
                    st.success(f"Tournament {tid} deleted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to delete tournament: {e}")
        with coldz2:
            cascade_all = st.checkbox("Also delete ALL Teams and Matches", value=False, key="dz_cascade_all")
            if st.button("Delete ALL tournaments", key="dz_delete_all"):
                try:
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM tournaments"))
                        if cascade_all:
                            try:
                                conn.execute(text("DELETE FROM teams"))
                            except Exception:
                                pass
                            try:
                                conn.execute(text("DELETE FROM matches"))
                            except Exception:
                                pass
                    set_active_tournament_id(None)
                    st.success("All tournaments deleted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to delete all tournaments: {e}")

with tabs[2]:
    st.subheader("Teams Management")
    st.markdown(
        """
        <style>
          .stDataFrame, .stDataEditor { font-size: 0.95rem; }
          .st-emotion-cache-ue6h4q { padding-top: 0.25rem; padding-bottom: 0.25rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    active_tid = get_active_tournament_id()
    with engine.begin() as conn:
        try:
            if active_tid is None:
                teams_df = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed, tournament_id FROM teams"), conn)
            else:
                teams_df = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed, tournament_id FROM teams WHERE tournament_id = :tid"), conn, params={"tid": active_tid})
        except Exception:
            teams_df = pd.DataFrame(columns=["team_id", "team_name", "player1", "player2", "group", "seed", "tournament_id"])
    # Filters
    fcol1, fcol2, fcol3 = st.columns([1.2, 1.2, 1])
    with fcol1:
        groups = sorted([g for g in teams_df.get("group", pd.Series(dtype=str)).dropna().unique().tolist()]) if not teams_df.empty else []
        sel_group = st.multiselect("Filter: Groups", options=groups, default=groups, placeholder="All", key="teams_filter_groups")
    with fcol2:
        q = st.text_input("Search team/player", placeholder="Type to filter…")
    with fcol3:
        st.write("")
        st.write("")
        st.caption(f"Teams: {0 if teams_df.empty else len(teams_df)}")

    view_df = teams_df.copy()
    if sel_group:
        view_df = view_df[view_df["group"].isin(sel_group)]
    if q:
        m = (
            view_df["team_name"].fillna("").str.contains(q, case=False)
            | view_df["player1"].fillna("").str.contains(q, case=False)
            | view_df["player2"].fillna("").str.contains(q, case=False)
        )
        view_df = view_df[m]

    st.caption("Edit existing teams inline. Save to persist.")
    edited_teams = st.data_editor(
        view_df,
        use_container_width=True,
        num_rows="dynamic",
        key="teams_editor",
        column_config={
            "team_id": st.column_config.NumberColumn("Team ID", help="Unique team identifier", step=1, min_value=0),
            "team_name": st.column_config.TextColumn("Team Name"),
            "player1": st.column_config.TextColumn("Player 1"),
            "player2": st.column_config.TextColumn("Player 2"),
            "group": st.column_config.TextColumn("Group"),
            "seed": st.column_config.NumberColumn("Seed", step=1, min_value=0),
        },
        hide_index=True,
    )
    if st.button("Save Team Changes", key="save_teams"):
        # Save only for the active tournament; keep other tournaments intact
        active_tid = get_active_tournament_id()
        upd = edited_teams.copy()
        upd["tournament_id"] = active_tid
        with engine.begin() as conn:
            try:
                cur = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed, tournament_id FROM teams"), conn)
            except Exception:
                cur = pd.DataFrame(columns=["team_id", "team_name", "player1", "player2", "group", "seed", "tournament_id"])
            if active_tid is None:
                out_df = upd
            else:
                others = cur[cur["tournament_id"] != active_tid]
                out_df = pd.concat([others, upd], ignore_index=True)
            out_df.to_sql("teams", conn, if_exists="replace", index=False)
        st.success("Teams updated.")
        st.rerun()

    st.markdown("---")
    st.caption("Add a new team")
    with st.form("add_team_form"):
        team_id = st.number_input("Team ID (unique)", min_value=0, step=1, format="%d")
        team_name = st.text_input("Team Name")
        player1 = st.text_input("Player 1")
        player2 = st.text_input("Player 2")
        existing_groups = sorted([g for g in teams_df.get("group", pd.Series(dtype=str)).dropna().unique().tolist()])
        group = st.selectbox("Group", options=["A", "B", "C", "D"] + existing_groups, index=0 if existing_groups == [] else 0)
        seed = st.number_input("Seed", min_value=0, step=1, format="%d")
        ok_add = st.form_submit_button("Add Team")
        if ok_add:
            new_row = {
                "team_id": int(team_id) if team_id is not None else None,
                "team_name": team_name,
                "player1": player1,
                "player2": player2,
                "group": group,
                "seed": int(seed) if seed is not None else None,
            }
            # Simple validation
            if not new_row["team_name"]:
                st.error("Team name is required.")
            elif teams_df["team_id"].astype("Int64").eq(new_row["team_id"]).any():
                st.error("Team ID already exists.")
            else:
                active_tid = get_active_tournament_id()
                new_row["tournament_id"] = active_tid
                with engine.begin() as conn:
                    try:
                        cur = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed, tournament_id FROM teams"), conn)
                    except Exception:
                        cur = pd.DataFrame(columns=["team_id", "team_name", "player1", "player2", "group", "seed", "tournament_id"])
                    if active_tid is None:
                        out_df = pd.concat([cur, pd.DataFrame([new_row])], ignore_index=True)
                    else:
                        others = cur[cur["tournament_id"] != active_tid]
                        out_df = pd.concat([others, pd.DataFrame([new_row])], ignore_index=True)
                    out_df.to_sql("teams", conn, if_exists="replace", index=False)
                st.success("Team added.")
                st.rerun()

    st.markdown("---")
    del_id = st.number_input("Delete Team by ID", min_value=0, step=1, format="%d", key="del_team_id")
    if st.button("Delete Team", key="del_team_btn"):
        with engine.begin() as conn:
            try:
                tid = get_active_tournament_id()
                if tid is None:
                    conn.exec_driver_sql("DELETE FROM teams WHERE team_id=?", (int(del_id),))
                else:
                    conn.execute(text("DELETE FROM teams WHERE team_id=:tid2 AND tournament_id=:tid"), {"tid2": int(del_id), "tid": tid})
            except Exception:
                tid = get_active_tournament_id()
                if tid is None:
                    conn.execute(text("DELETE FROM teams WHERE team_id=:tid2"), {"tid2": int(del_id)})
                else:
                    conn.execute(text("DELETE FROM teams WHERE team_id=:tid2 AND tournament_id=:tid"), {"tid2": int(del_id), "tid": tid})
        st.info(f"Team {int(del_id)} deleted (if existed).")
        st.rerun()

with tabs[3]:
    st.subheader("Scheduler (Round-robin)")
    st.caption("Generate fixtures per group. Choose replace or append.")
    def generate_round_robin(df: pd.DataFrame) -> pd.DataFrame:
        matches = []
        next_id = 1
        for grp, gdf in df.groupby("group"):
            ids = [int(x) for x in gdf["team_id"].dropna().tolist()]
            n = len(ids)
            for i in range(n):
                for j in range(i + 1, n):
                    matches.append({
                        "match_id": next_id,
                        "group": grp,
                        "team1_id": ids[i],
                        "team2_id": ids[j],
                        "status": "Scheduled",
                        "set1_t1": pd.NA, "set1_t2": pd.NA,
                        "set2_t1": pd.NA, "set2_t2": pd.NA,
                        "set3_t1": pd.NA, "set3_t2": pd.NA,
                    })
                    next_id += 1
        return pd.DataFrame(matches, columns=[
            "match_id", "group", "team1_id", "team2_id", "status",
            "set1_t1", "set1_t2", "set2_t1", "set2_t2", "set3_t1", "set3_t2"
        ])

    with engine.begin() as conn:
        try:
            tid = get_active_tournament_id()
            if tid is None:
                base_df = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed FROM teams"), conn)
            else:
                base_df = pd.read_sql(text("SELECT team_id, team_name, player1, player2, \"group\", seed FROM teams WHERE tournament_id = :tid"), conn, params={"tid": tid})
        except Exception:
            base_df = pd.DataFrame(columns=["team_id", "team_name", "player1", "player2", "group", "seed"])

    scol1, scol2, scol3 = st.columns([1.5, 1.5, 1])
    with scol1:
        gen_groups = st.multiselect("Groups to generate", options=sorted(base_df["group"].dropna().unique().tolist()) if not base_df.empty else [], placeholder="All groups")
    with scol2:
        mode = st.radio("Write mode", options=["Replace all", "Append"], horizontal=True)
    with scol3:
        start_id = st.number_input("Start MatchId", min_value=1, value=1, step=1)

    if st.button("Generate Matches", key="gen_rr"):
        df = base_df.copy()
        if gen_groups:
            df = df[df["group"].isin(gen_groups)]
        rr = generate_round_robin(df)
        # Shift match ids to start at start_id
        rr["match_id"] = range(int(start_id), int(start_id) + len(rr))
        rr["tournament_id"] = get_active_tournament_id()
        with engine.begin() as conn:
            try:
                cur = pd.read_sql(text("SELECT * FROM matches"), conn)
            except Exception:
                cur = pd.DataFrame(columns=rr.columns)
            tid = get_active_tournament_id()
            if mode == "Replace all":
                others = cur[cur.get("tournament_id").fillna(-1) != (tid if tid is not None else -1)] if not cur.empty else pd.DataFrame(columns=rr.columns)
                merged = pd.concat([others, rr], ignore_index=True)
            else:
                merged = pd.concat([cur, rr], ignore_index=True)
            merged.to_sql("matches", conn, if_exists="replace", index=False)
        st.success(f"Generated {len(rr)} matches.")
        st.rerun()

    try:
        with engine.begin() as conn:
            cur = pd.read_sql(text("SELECT COUNT(*) as c FROM matches"), conn)
        st.caption(f"Existing matches: {int(cur['c'][0])}")
    except Exception:
        st.caption("Existing matches: 0")

    st.markdown("---")
    st.subheader("Manual Match Maker")
    st.caption("Create a single match by selecting group and teams. This will append to the matches table.")

    # Load teams for selectors
    with engine.begin() as conn:
        try:
            tid = get_active_tournament_id()
            if tid is None:
                all_teams = pd.read_sql(text("SELECT team_id, team_name, \"group\" FROM teams"), conn)
            else:
                all_teams = pd.read_sql(text("SELECT team_id, team_name, \"group\" FROM teams WHERE tournament_id = :tid"), conn, params={"tid": tid})
        except Exception:
            all_teams = pd.DataFrame(columns=["team_id", "team_name", "group"])

    mcol_a, mcol_b, mcol_c = st.columns([1.2, 1.6, 1.6])
    with mcol_a:
        grp_opts = sorted(all_teams["group"].dropna().unique().tolist()) if not all_teams.empty else []
        sel_grp = st.selectbox("Group", options=grp_opts, index=0 if grp_opts else None, key="mm_group")
        status_opt = st.selectbox("Status", options=["Scheduled", "In Progress", "Completed"], index=0, key="mm_status")
        custom_id = st.number_input("Custom MatchId (optional)", min_value=0, step=1, value=0, key="mm_custom_id")
    with mcol_b:
        opts = []
        if sel_grp:
            gdf = all_teams[all_teams["group"] == sel_grp]
            opts = [f"{int(r.team_id)} — {r.team_name}" for _, r in gdf.iterrows()]
        t1 = st.selectbox("Team 1", options=opts, index=0 if opts else None, key="mm_t1")
    with mcol_c:
        t2 = st.selectbox("Team 2", options=opts, index=1 if len(opts) > 1 else None, key="mm_t2")

    def parse_team(opt: str):
        try:
            return int(str(opt).split(" — ")[0])
        except Exception:
            return None

    if st.button("Add Match", key="mm_add"):
        t1_id = parse_team(t1)
        t2_id = parse_team(t2)
        if not sel_grp:
            st.error("Please select a group.")
        elif t1_id is None or t2_id is None:
            st.error("Please select both Team 1 and Team 2.")
        elif t1_id == t2_id:
            st.error("Team 1 and Team 2 must be different.")
        else:
            with engine.begin() as conn:
                try:
                    cur = pd.read_sql(text("SELECT * FROM matches"), conn)
                except Exception:
                    cur = pd.DataFrame(columns=[
                        "match_id", "group", "team1_id", "team2_id", "status",
                        "set1_t1", "set1_t2", "set2_t1", "set2_t2", "set3_t1", "set3_t2", "tournament_id"
                    ])
                tid = get_active_tournament_id()
                cur_tid = cur[cur.get("tournament_id").fillna(-1) == (tid if tid is not None else -1)] if not cur.empty else pd.DataFrame(columns=cur.columns)
                if cur_tid.empty:
                    next_id_auto = 1
                else:
                    try:
                        next_id_auto = int(pd.to_numeric(cur_tid["match_id"], errors="coerce").max()) + 1
                    except Exception:
                        next_id_auto = 1
                new_id = int(custom_id) if custom_id and custom_id > 0 else next_id_auto

                new_row = pd.DataFrame([{
                    "match_id": new_id,
                    "group": sel_grp,
                    "team1_id": t1_id,
                    "team2_id": t2_id,
                    "status": status_opt,
                    "set1_t1": pd.NA, "set1_t2": pd.NA,
                    "set2_t1": pd.NA, "set2_t2": pd.NA,
                    "set3_t1": pd.NA, "set3_t2": pd.NA,
                    "tournament_id": tid,
                }])
                others = cur[cur.get("tournament_id").fillna(-1) != (tid if tid is not None else -1)] if not cur.empty else pd.DataFrame(columns=new_row.columns)
                merged = pd.concat([others, cur_tid, new_row], ignore_index=True).fillna({"tournament_id": tid})
                merged.to_sql("matches", conn, if_exists="replace", index=False)
            st.success(f"Match added: ID {new_id} — Team {t1_id} vs Team {t2_id} in Group {sel_grp}.")
            st.rerun()

with tabs[4]:
    st.subheader("Matches Scoring")
    st.markdown(
        """
        <style>
          .stDataEditor [data-baseweb="input"] input { text-align: center; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with engine.begin() as conn:
        try:
            tid = get_active_tournament_id()
            if tid is None:
                matches_df = pd.read_sql(text("SELECT match_id, \"group\", team1_id, team2_id, status, set1_t1, set1_t2, set2_t1, set2_t2, set3_t1, set3_t2, tournament_id FROM matches"), conn)
            else:
                matches_df = pd.read_sql(text("SELECT match_id, \"group\", team1_id, team2_id, status, set1_t1, set1_t2, set2_t1, set2_t2, set3_t1, set3_t2, tournament_id FROM matches WHERE tournament_id = :tid"), conn, params={"tid": tid})
        except Exception:
            matches_df = pd.DataFrame(columns=["match_id", "group", "team1_id", "team2_id", "status", "set1_t1", "set1_t2", "set2_t1", "set2_t2", "set3_t1", "set3_t2", "tournament_id"])
    # Filters
    tmap = {}
    try:
        with engine.begin() as conn:
            tdf = pd.read_sql(text("SELECT team_id, team_name FROM teams"), conn)
        tmap = dict(zip(tdf["team_id"], tdf["team_name"]))
    except Exception:
        pass
    mcol1, mcol2, mcol3 = st.columns([1.2, 1.2, 1])
    with mcol1:
        groups = sorted(matches_df["group"].dropna().unique().tolist()) if not matches_df.empty else []
        sel_group = st.multiselect("Filter: Groups", options=groups, default=groups, placeholder="All", key="scoring_filter_groups")
    with mcol2:
        status_opts = ["Scheduled", "In Progress", "Completed"]
        sel_status = st.multiselect("Filter: Status", options=status_opts, default=status_opts, key="scoring_filter_status")
    with mcol3:
        team_query = st.text_input("Search team", placeholder="Team name contains…")

    view_m = matches_df.copy()
    if sel_group:
        view_m = view_m[view_m["group"].isin(sel_group)]
    if sel_status:
        view_m = view_m[view_m["status"].isin(sel_status)]
    if team_query and tmap:
        view_m = view_m[
            view_m["team1_id"].map(tmap).fillna("").str.contains(team_query, case=False)
            | view_m["team2_id"].map(tmap).fillna("").str.contains(team_query, case=False)
        ]

    st.markdown("---")
    st.caption("Bulk actions")
    cba1, cba2, cba3 = st.columns([1,1,2])
    with cba1:
        do_reset_status = st.checkbox("Reset status to 'Scheduled'", value=False, key="bulk_reset_status")
    with cba2:
        apply_groups_scope = st.checkbox("Apply current group filter", value=bool(sel_group), key="bulk_apply_groups")
    with cba3:
        if st.button("Clear scoring (sets) for matches", key="bulk_clear_scores"):
            tid = get_active_tournament_id()
            where_clauses = []
            params = {}
            if tid is not None:
                where_clauses.append("tournament_id = :tid")
                params["tid"] = int(tid)
            if apply_groups_scope and sel_group:
                # build IN clause dynamically
                groups_list = [str(g) for g in sel_group]
                in_params = {f"g{i}": g for i, g in enumerate(groups_list)}
                where_clauses.append("\"group\" IN (" + ",".join([":"+k for k in in_params.keys()]) + ")")
                params.update(in_params)
            where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
            set_status_sql = ", status='Scheduled'" if do_reset_status else ""
            sql = (
                "UPDATE matches SET set1_t1=NULL, set1_t2=NULL, set2_t1=NULL, set2_t2=NULL, set3_t1=NULL, set3_t2=NULL"
                + set_status_sql + where_sql
            )
            try:
                with engine.begin() as conn:
                    conn.execute(text(sql), params)
                st.success("Scoring cleared." + (" Status reset." if do_reset_status else ""))
                st.rerun()
            except Exception as e:
                st.error(f"Failed to clear scores: {e}")

    st.caption("Edit scores and status inline. Save to persist.")
    edited_matches = st.data_editor(
        view_m,
        use_container_width=True,
        num_rows="dynamic",
        key="matches_editor",
        column_config={
            "match_id": st.column_config.NumberColumn("MatchId", step=1, min_value=1, help="ID must be unique"),
            "group": st.column_config.TextColumn("Group"),
            "team1_id": st.column_config.NumberColumn("Team1 ID", step=1, min_value=0),
            "team2_id": st.column_config.NumberColumn("Team2 ID", step=1, min_value=0),
            "status": st.column_config.SelectboxColumn("Status", options=["Scheduled", "In Progress", "Completed"]),
            "set1_t1": st.column_config.NumberColumn("S1 T1", min_value=0, max_value=7, step=1),
            "set1_t2": st.column_config.NumberColumn("S1 T2", min_value=0, max_value=7, step=1),
            "set2_t1": st.column_config.NumberColumn("S2 T1", min_value=0, max_value=7, step=1),
            "set2_t2": st.column_config.NumberColumn("S2 T2", min_value=0, max_value=7, step=1),
            "set3_t1": st.column_config.NumberColumn("S3 T1", min_value=0, max_value=7, step=1),
            "set3_t2": st.column_config.NumberColumn("S3 T2", min_value=0, max_value=7, step=1),
        },
        hide_index=True,
    )
    if st.button("Save Match Changes", key="save_matches"):
        tid = get_active_tournament_id()
        upd = edited_matches.copy()
        upd["tournament_id"] = tid
        with engine.begin() as conn:
            try:
                cur = pd.read_sql(text("SELECT * FROM matches"), conn)
            except Exception:
                cur = pd.DataFrame(columns=upd.columns)
            others = cur[cur.get("tournament_id").fillna(-1) != (tid if tid is not None else -1)] if not cur.empty else pd.DataFrame(columns=upd.columns)
            out = pd.concat([others, upd], ignore_index=True)
            out.to_sql("matches", conn, if_exists="replace", index=False)
        st.success("Matches updated.")
        st.rerun()

    st.markdown("---")
    del_mid = st.number_input("Delete Match by ID", min_value=0, step=1, format="%d", key="del_match_id")
    if st.button("Delete Match", key="del_match_btn"):
        with engine.begin() as conn:
            try:
                tid = get_active_tournament_id()
                if tid is None:
                    conn.exec_driver_sql("DELETE FROM matches WHERE match_id=?", (int(del_mid),))
                else:
                    conn.execute(text("DELETE FROM matches WHERE match_id=:mid AND tournament_id=:tid"), {"mid": int(del_mid), "tid": tid})
            except Exception:
                tid = get_active_tournament_id()
                if tid is None:
                    conn.execute(text("DELETE FROM matches WHERE match_id=:mid"), {"mid": int(del_mid)})
                else:
                    conn.execute(text("DELETE FROM matches WHERE match_id=:mid AND tournament_id=:tid"), {"mid": int(del_mid), "tid": tid})
        st.info(f"Match {int(del_mid)} deleted (if existed).")
        st.rerun()

with tabs[5]:
    st.subheader("Display Settings")
    st.caption("Control which columns are visible and customize header labels on the Overview page.")

    with st.expander("Columns (Visibility)", expanded=True):
        played_all_cols = ["MatchId", "Court", "Players", "Sets", "Games", "Status"]
        standings_all_cols = ["Rank", "Team", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"]
        teams_all_cols = ["Team", "Players", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"]

        current_played = get_json_setting("visible_cols_played") or played_all_cols
        current_stand = get_json_setting("visible_cols_standings") or standings_all_cols
        current_teams = get_json_setting("visible_cols_teams") or teams_all_cols

        sel_played = st.multiselect("Played Matches columns", options=played_all_cols, default=current_played, key="disp_played")
        sel_stand = st.multiselect("Winner Board / Standings columns", options=standings_all_cols, default=current_stand, key="disp_stand")
        sel_teams = st.multiselect("Teams columns", options=teams_all_cols, default=current_teams, key="disp_teams")

        if st.button("Save Column Visibility", key="save_disp_cols"):
            set_json_setting("visible_cols_played", sel_played or played_all_cols)
            set_json_setting("visible_cols_standings", sel_stand or standings_all_cols)
            set_json_setting("visible_cols_teams", sel_teams or teams_all_cols)
            st.success("Column visibility saved.")

    with st.expander("Header Labels", expanded=False):
        played_all_cols = ["MatchId", "Court", "Players", "Sets", "Games", "Status"]
        standings_all_cols = ["Rank", "Team", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"]
        teams_all_cols = ["Team", "Players", "MatchesPlayed", "MatchesWon", "MatchesLost", "Points"]

        played_labels = get_json_setting("header_labels_played") or {}
        standings_labels = get_json_setting("header_labels_standings") or {}
        teams_labels = get_json_setting("header_labels_teams") or {}

        new_played_labels = {}
        for c in played_all_cols:
            new_played_labels[c] = st.text_input(f"Played: label for '{c}'", value=str(played_labels.get(c, c)), key=f"hdr_played_{c}")

        st.markdown("---")
        new_standings_labels = {}
        for c in standings_all_cols:
            new_standings_labels[c] = st.text_input(f"Standings: label for '{c}'", value=str(standings_labels.get(c, c)), key=f"hdr_stand_{c}")

        st.markdown("---")
        new_teams_labels = {}
        for c in teams_all_cols:
            new_teams_labels[c] = st.text_input(f"Teams: label for '{c}'", value=str(teams_labels.get(c, c)), key=f"hdr_teams_{c}")

        if st.button("Save Header Labels", key="save_hdr_labels"):
            set_json_setting("header_labels_played", new_played_labels)
            set_json_setting("header_labels_standings", new_standings_labels)
            set_json_setting("header_labels_teams", new_teams_labels)
            st.success("Header labels saved.")
