import os
import base64
import streamlit as st
import pandas as pd
from sqlalchemy import text
from data.db import engine

st.set_page_config(page_title="Padel Tournamemt Application", page_icon="🎾", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
      .hero { max-width: 1200px; margin: 0 auto; padding: 8px 12px; }
      .section { max-width: 1200px; margin: 0 auto; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='hero'>", unsafe_allow_html=True)
st.title("Padel Tournamemt App")
st.caption("Scoring and scheduling dashboard combined with Organizer section")
st.markdown("Select a page from the sidebar: Overview, Admin, Scoring, Scheduling.")
st.markdown("</div>", unsafe_allow_html=True)

def set_setting(key: str, value: str):
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO settings(key, value) VALUES(:k, :v) ON CONFLICT(key) DO UPDATE SET value=:v"), {"k": key, "v": value})
    except Exception:
        pass

# Handle deep-link selection via query param (?tid=123) using st.query_params
try:
    qp = dict(getattr(st, "query_params", {}))
    raw = qp.get("tid")
    tid_q = raw[0] if isinstance(raw, list) else raw
    if tid_q not in (None, ""):
        set_setting("active_tournament_id", str(int(tid_q)))
        try:
            # clear params to avoid loops
            st.query_params.clear()
        except Exception:
            pass
        try:
            st.switch_page("pages/1_Active_Tournament.py")
        except Exception:
            st.rerun()
except Exception:
    pass

def get_setting(key: str):
    try:
        with engine.begin() as conn:
            row = conn.execute(text("SELECT value FROM settings WHERE key=:k"), {"k": key}).first()
        return row[0] if row else None
    except Exception:
        return None

def get_active_tournament_id():
    v = get_setting("active_tournament_id")
    try:
        return int(v) if v not in (None, "", "null") else None
    except Exception:
        return None

# If a tournament is selected, show its image at the top-right
try:
    active_tid = get_active_tournament_id()
    if active_tid is not None:
        tinfo = pd.read_sql(text("SELECT name, icon_path FROM tournaments WHERE tournament_id = :tid"), engine, params={"tid": active_tid})
        if not tinfo.empty:
            icon = str(tinfo.loc[0, "icon_path"]) if "icon_path" in tinfo.columns and pd.notna(tinfo.loc[0, "icon_path"]) else ""
            if icon:
                c_top_l, c_top_r = st.columns([3,1])
                with c_top_r:
                    st.image(icon, use_container_width=True)
except Exception:
    pass

# Upcoming tournaments
try:
    tournaments_df = pd.read_sql(
        text("SELECT tournament_id, name, location, start_date, end_date, description, icon_path FROM tournaments"),
        engine,
        parse_dates=["start_date", "end_date"],
    )
except Exception:
    tournaments_df = pd.DataFrame(columns=["tournament_id", "name", "location", "start_date", "end_date", "description"])

if not tournaments_df.empty:
    today = pd.Timestamp.today().normalize()
    upcoming = tournaments_df.copy()
    for col in ["start_date", "end_date"]:
        if upcoming[col].dtype == object:
            upcoming[col] = pd.to_datetime(upcoming[col], errors="coerce")
    # Show tournaments where start is in the future OR end is in the future (or either is missing)
    cond_start = upcoming["start_date"].isna() | (upcoming["start_date"] >= today)
    cond_end = upcoming["end_date"].isna() | (upcoming["end_date"] >= today)
    upcoming = upcoming[cond_start | cond_end]
    upcoming = upcoming.sort_values(by=["start_date"], na_position="last").head(6)
    if not upcoming.empty:
        st.subheader("Upcoming Tournaments")
        # New fully responsive grid (image on top, text below). Each card is a link (?tid=ID)
        st.markdown(
            """
            <style>
              .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
              .card { background:#0f160f; border:1px solid #2a5f2a; border-radius:18px; overflow:hidden; box-shadow: 0 10px 28px rgba(0,0,0,0.28); }
              .card a { color:#e8f6e8; text-decoration:none; display:block; }
              .thumb { width:100%; height:180px; background:#122012; }
              .thumb img { width:100%; height:100%; object-fit:cover; display:block; }
              .body { padding:16px 18px 18px; }
              .title { font-weight:800; font-size:1.15rem; color:#9be37a; margin:6px 0 4px; line-height:1.3; }
              .meta { color:#b9d0b9; font-size:0.95rem; margin:2px 0; }
              .badge { display:inline-block; background:#204b20; color:#bff3b7; border:1px solid #2a5f2a; padding:3px 8px; border-radius:999px; font-size:0.8rem; }
              .card a:hover { outline:none; }
              .card:hover { border-color:#3fa43f; transform: translateY(-2px); transition: all .12s ease; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        html = ["<div class='grid'>"]
        for r in upcoming.itertuples(index=False):
            s = getattr(r, "start_date"); e = getattr(r, "end_date")
            sd = pd.to_datetime(s).strftime("%Y-%m-%d") if pd.notna(s) else "TBD"
            ed = pd.to_datetime(e).strftime("%Y-%m-%d") if pd.notna(e) else "TBD"
            name = (getattr(r, 'name') or 'Tournament')
            location = (getattr(r, 'location') or '')
            desc = (getattr(r, 'description') or '')
            icon = (getattr(r, 'icon_path') or '').replace('\\','/')
            tid = getattr(r, 'tournament_id')
            href = f"/?tid={int(tid)}" if pd.notna(tid) else "#"
            # Build <img> tag; if local path, embed as base64 so it renders inside HTML
            img_html = ''
            if icon:
                try:
                    if icon.startswith('http://') or icon.startswith('https://'):
                        img_html = f"<img src=\"{icon}\">"
                    else:
                        # Resolve relative to project root
                        # Resolve relative to the Padellers/ directory
                        base_dir = os.path.abspath(os.path.dirname(__file__))
                        abs_path = icon if os.path.isabs(icon) else os.path.abspath(os.path.join(base_dir, icon))
                        with open(abs_path, 'rb') as f:
                            data = base64.b64encode(f.read()).decode('utf-8')
                        # Try infer mime by extension
                        ext = os.path.splitext(abs_path)[1].lower()
                        mime = 'image/png' if ext in ('.png', '') else 'image/jpeg'
                        img_html = f"<img src=\"data:{mime};base64,{data}\">"
                except Exception:
                    img_html = ''
            html.append(
                f"<div class='card'>"
                f"<a href='{href}'>"
                f"<div class='thumb'>{img_html}</div>"
                f"<div class='body'>"
                f"<span class='badge'>Upcoming</span>"
                f"<div class='title'>{name}</div>"
                f"<div class='meta'>📍 {location}</div>"
                f"<div class='meta'>🗓️ {sd} — {ed}</div>"
                f"<div class='meta' style='opacity:.9'>{desc}</div>"
                f"</div>"
                f"</a>"
                f"</div>"
            )
        html.append("</div>")
        st.markdown("\n".join(html), unsafe_allow_html=True)
        # spacer between Upcoming and Held sections
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # Held (past) tournaments
    held = tournaments_df.copy()
    for col in ["start_date", "end_date"]:
        if held[col].dtype == object:
            held[col] = pd.to_datetime(held[col], errors="coerce")
    past_end = held["end_date"].notna() & (held["end_date"] < today)
    past_start_only = held["end_date"].isna() & held["start_date"].notna() & (held["start_date"] < today)
    held = held[past_end | past_start_only]
    held = held.sort_values(by=["end_date", "start_date"], ascending=[False, False], na_position="last").head(12)
    if not held.empty:
        st.subheader("Held Tournaments")
        st.markdown(
            """
            <style>
              .grid-held { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 5px; }
              .card-held { background:#0f160f; border:1px solid #2a5f2a; border-radius:18px; overflow:hidden; box-shadow: 0 10px 28px rgba(0,0,0,0.22); }
              .card-held a { color:#e8f6e8; text-decoration:none; display:block; }
              .thumb-held { width:100%; height:160px; background:#122012; }
              .thumb-held img { width:100%; height:100%; object-fit:cover; display:block; }
              .body-held { padding:14px 16px 16px; }
              .title-held { font-weight:800; font-size:1.05rem; color:#9be37a; margin:4px 0 2px; line-height:1.3; }
              .meta-held { color:#b9d0b9; font-size:0.9rem; margin:2px 0; }
              .badge-held { display:inline-block; background:#1a341a; color:#bff3b7; border:1px solid #2a5f2a; padding:3px 8px; border-radius:999px; font-size:0.78rem; }
              .card-held:hover { border-color:#3fa43f; transform: translateY(-2px); transition: all .12s ease; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        html_h = ["<div class='grid-held'>"]
        for r in held.itertuples(index=False):
            s = getattr(r, "start_date"); e = getattr(r, "end_date")
            sd = pd.to_datetime(s).strftime("%Y-%m-%d") if pd.notna(s) else "TBD"
            ed = pd.to_datetime(e).strftime("%Y-%m-%d") if pd.notna(e) else "TBD"
            name = (getattr(r, 'name') or 'Tournament')
            location = (getattr(r, 'location') or '')
            desc = (getattr(r, 'description') or '')
            icon = (getattr(r, 'icon_path') or '').replace('\\','/')
            tid = getattr(r, 'tournament_id')
            # Images: same base64 logic as above
            img_html = ''
            if icon:
                try:
                    if icon.startswith('http://') or icon.startswith('https://'):
                        img_html = f"<img src=\"{icon}\">"
                    else:
                        base_dir = os.path.abspath(os.path.dirname(__file__))
                        abs_path = icon if os.path.isabs(icon) else os.path.abspath(os.path.join(base_dir, icon))
                        with open(abs_path, 'rb') as f:
                            data = base64.b64encode(f.read()).decode('utf-8')
                        ext = os.path.splitext(abs_path)[1].lower()
                        mime = 'image/png' if ext in ('.png', '') else 'image/jpeg'
                        img_html = f"<img src=\"data:{mime};base64,{data}\">"
                except Exception:
                    img_html = ''
            html_h.append(
                f"<div class='card-held'>"
                f"<a href='#'>"
                f"<div class='thumb-held'>{img_html}</div>"
                f"<div class='body-held'>"
                f"<span class='badge-held'>Held</span>"
                f"<div class='title-held'>{name}</div>"
                f"<div class='meta-held'>📍 {location}</div>"
                f"<div class='meta-held'>🗓️ {sd} — {ed}</div>"
                f"<div class='meta-held' style='opacity:.9'>{desc}</div>"
                f"</div>"
                f"</a>"
                f"</div>"
            )
        html_h.append("</div>")
        st.markdown("\n".join(html_h), unsafe_allow_html=True)
