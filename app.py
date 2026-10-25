# -*- coding: utf-8 -*-
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import re

# ==============================================================================
# 0. KONFIGURÁCIÓ, PWA META-TAGEK ÉS RESZPONZÍV MOBIL / ENTERPRISE CSS
# ==============================================================================
st.set_page_config(
    page_title="Chronos Enterprise | Munkaidő App",
    page_icon="⏱️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Chronos">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#2563EB">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">

<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stButton > button {
        min-height: 48px !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }
    .stTextInput input, .stSelectbox div[data-baseweb="select"], .stDateInput input, .stNumberInput input {
        min-height: 45px !important;
        border-radius: 8px !important;
    }
    .saas-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 18px 20px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        margin-bottom: 14px;
    }
    .saas-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }
    .quick-tap-box {
        background: linear-gradient(135deg, #eff6ff 0%, #f5f3ff 100%);
        border: 1px solid #bfdbfe;
        border-radius: 14px;
        padding: 16px;
        margin-bottom: 18px;
    }
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-fixed { background-color: #dbeafe; color: #1e40af; }
    .badge-retainer { background-color: #f3e8ff; color: #6b21a8; }
    .badge-admin { background-color: #f1f5f9; color: #475569; }
    .role-admin { background-color: #fee2e2; color: #991b1b; }
    .role-pm { background-color: #fef3c7; color: #92400e; }
    .role-emp { background-color: #dcfce7; color: #166534; }
    .proj-pill {
        display: inline-block;
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        color: #334155;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.72rem;
        margin-right: 4px;
        margin-bottom: 4px;
    }
    .avatar-circle {
        width: 44px;
        height: 44px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 1rem;
        color: white;
        margin-right: 12px;
        flex-shrink: 0;
    }
    .progress-track {
        width: 100%;
        height: 8px;
        background-color: #e2e8f0;
        border-radius: 999px;
        overflow: hidden;
        margin: 6px 0;
    }
    .progress-fill {
        height: 100%;
        border-radius: 999px;
    }
    .timeblock-container {
        display: flex;
        width: 100%;
        height: 36px;
        background-color: #f1f5f9;
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #cbd5e1;
        margin-bottom: 10px;
    }
    .timeblock-segment {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #ffffff;
        font-size: 0.75rem;
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        padding: 0 6px;
    }
    @media (max-width: 768px) {
        .block-container {
            padding-top: 2.2rem !important;
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
            padding-bottom: 4rem !important;
        }
        div[data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
            gap: 0.5rem !important;
        }
        div[data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }
        div[data-baseweb="tab-list"] {
            overflow-x: auto !important;
            white-space: nowrap !important;
            flex-wrap: nowrap !important;
            padding-bottom: 4px !important;
        }
        .saas-card { padding: 14px !important; margin-bottom: 10px !important; }
        .saas-card-header { flex-direction: column !important; align-items: flex-start !important; gap: 6px !important; }
    }
</style>
""", unsafe_allow_html=True)

TYPE_COLORS = {"Fixed": "#2563EB", "Retainer": "#7C3AED", "Admin": "#64748B"}
TYPE_LABELS = {"Fixed": "Fix keretes projekt", "Retainer": "Átalánydíjas (Retainer)", "Admin": "Belső / Adminisztratív"}
ROLE_HIERARCHY = {"Dolgozó": 1, "Projektgazda": 2, "Admin": 3}

# ==============================================================================
# 1. IDŐFORMÁTUM KONVERTEREK
# ==============================================================================
def format_duration(hours_float, mode="decimal", daily_target=8.0):
    try:
        h = float(hours_float)
    except (ValueError, TypeError):
        h = 0.0
    if mode == "hhmm":
        total_minutes = int(round(h * 60))
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
    elif mode == "percent":
        pct = (h / daily_target) * 100.0 if daily_target > 0 else 0.0
        return f"{pct:.1f}%"
    return f"{h:.2f} óra"

def parse_duration_input(val_str, daily_target=8.0):
    if isinstance(val_str, (int, float)):
        return max(0.0, float(val_str))
    s = str(val_str).strip()
    if not s:
        return 0.0
    try:
        if s.endswith("%"):
            pct_val = float(s[:-1].replace(",", ".").strip())
            return round((pct_val / 100.0) * daily_target, 2)
        if ":" in s:
            parts = s.split(":")
            return round(float(parts[0].strip() or 0) + (float(parts[1].strip() or 0) / 60.0), 2)
        clean_s = re.sub(r"[^\d.,-]", "", s).replace(",", ".")
        return round(max(0.0, float(clean_s)), 2) if clean_s else 0.0
    except Exception:
        return None

# ==============================================================================
# 2. DEMÓ ADATOK ÉS ADATBÁZIS RÉTEG
# ==============================================================================
def get_seed_data():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    d_str = lambda offset: (monday + timedelta(days=offset)).strftime("%Y-%m-%d")
    last_m = (monday - timedelta(days=25)).strftime("%Y-%m-%d")

    users = pd.DataFrame([
        {"email": "kiss.tamas@ceg.hu", "password": "123", "name": "Kiss Tamás", "role": "Admin", "title": "Ügyvezető Igazgató", "department": "Menedzsment", "weekly_capacity": 40},
        {"email": "nagy.eszter@ceg.hu", "password": "123", "name": "Nagy Eszter", "role": "Projektgazda", "title": "Senior Projektmenedzser", "department": "Tanácsadás & Audit", "weekly_capacity": 40},
        {"email": "kovacs.dori@ceg.hu", "password": "123", "name": "Kovács Dóra", "role": "Dolgozó", "title": "Szenior Tanácsadó", "department": "Tanácsadás & Audit", "weekly_capacity": 40},
        {"email": "szabo.bence@ceg.hu", "password": "123", "name": "Szabó Bence", "role": "Dolgozó", "title": "Adatelemző & Fejlesztő", "department": "Digitális Üzletág", "weekly_capacity": 40},
        {"email": "varga.mate@ceg.hu", "password": "123", "name": "Varga Máté", "role": "Dolgozó", "title": "Rendszermérnök", "department": "Infrastruktúra", "weekly_capacity": 32}
    ])

    projects = pd.DataFrame([
        {"id": 1, "name": "ERP Rendszer Migráció & Adatmodell", "project_type": "Fixed", "budget_hours": 120.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "2026-12-15", "status": "Aktív", "color": "#2563EB", "owner_email": "nagy.eszter@ceg.hu", "assigned_to": "kovacs.dori@ceg.hu,varga.mate@ceg.hu,nagy.eszter@ceg.hu", "tags": "Backend,Kritikus,Q4"},
        {"id": 2, "name": "Vállalati Controlling & BI Dashboard", "project_type": "Fixed", "budget_hours": 60.0, "monthly_retainer_hours": 0.0, "manual_completion": 85.0, "deadline": "2026-11-20", "status": "Aktív", "color": "#0284C7", "owner_email": "nagy.eszter@ceg.hu", "assigned_to": "szabo.bence@ceg.hu,kovacs.dori@ceg.hu,nagy.eszter@ceg.hu", "tags": "BI,Elemzés,Ügyfél"},
        {"id": 3, "name": "Éves Kockázati & Megfelelőségi Audit", "project_type": "Fixed", "budget_hours": 25.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "2026-11-05", "status": "Aktív", "color": "#DC2626", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "kovacs.dori@ceg.hu,kiss.tamas@ceg.hu", "tags": "Audit,Sürgős"},
        {"id": 4, "name": "Átalánydíjas Üzleti és Szakmai Tanácsadás", "project_type": "Retainer", "budget_hours": 0.0, "monthly_retainer_hours": 40.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#7C3AED", "owner_email": "nagy.eszter@ceg.hu", "assigned_to": "kovacs.dori@ceg.hu,varga.mate@ceg.hu,nagy.eszter@ceg.hu,kiss.tamas@ceg.hu", "tags": "Retainer,Átalánydíjas,Havi"},
        {"id": 5, "name": "Folyamatos Rendszertámogatás (SLA)", "project_type": "Retainer", "budget_hours": 0.0, "monthly_retainer_hours": 30.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#0D9488", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "varga.mate@ceg.hu,szabo.bence@ceg.hu", "tags": "SLA,Support"},
        {"id": 6, "name": "Adminisztráció & Napi Operáció", "project_type": "Admin", "budget_hours": 0.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#64748B", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "*", "tags": "Belső,Nem elszámolható"},
        {"id": 7, "name": "Belső Megbeszélés & Csapatmeeting", "project_type": "Admin", "budget_hours": 0.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#475569", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "*", "tags": "Meeting,Belső"},
        {"id": 8, "name": "Oktatás, Szakmai Képzés & Kutatás", "project_type": "Admin", "budget_hours": 0.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#94A3B8", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "*", "tags": "Képzés,Fejlődés"},
        {"id": 9, "name": "Szabadság / Távollét", "project_type": "Admin", "budget_hours": 0.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#CBD5E1", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "*", "tags": "HR,Szabadság"}
    ])

    logs = pd.DataFrame([
        {"id": 101, "email": "kovacs.dori@ceg.hu", "project_id": 1, "date": d_str(0), "hours": 5.5, "notes": "Adatbázis séma migráció és dokumentáció"},
        {"id": 102, "email": "kovacs.dori@ceg.hu", "project_id": 4, "date": d_str(0), "hours": 1.5, "notes": "Átalánydíjas ügyfél konzultáció"},
        {"id": 103, "email": "kovacs.dori@ceg.hu", "project_id": 7, "date": d_str(0), "hours": 1.0, "notes": "Hétindító szakmai egyeztetés"},
        {"id": 104, "email": "kovacs.dori@ceg.hu", "project_id": 1, "date": d_str(1), "hours": 6.0, "notes": "Folyamatok validálása"},
        {"id": 105, "email": "kovacs.dori@ceg.hu", "project_id": 2, "date": d_str(1), "hours": 2.0, "notes": "Kimutatás sablonok ellenőrzése"},
        {"id": 106, "email": "kovacs.dori@ceg.hu", "project_id": 3, "date": d_str(2), "hours": 7.5, "notes": "Kockázatelemzési jegyzőkönyv"},
        {"id": 107, "email": "kovacs.dori@ceg.hu", "project_id": 6, "date": d_str(2), "hours": 0.5, "notes": "Heti adminisztráció"},
        {"id": 108, "email": "szabo.bence@ceg.hu", "project_id": 2, "date": d_str(0), "hours": 7.0, "notes": "BI adatkapcsolatok építése"},
        {"id": 109, "email": "szabo.bence@ceg.hu", "project_id": 7, "date": d_str(0), "hours": 1.0, "notes": "Státusz megbeszélés"},
        {"id": 110, "email": "szabo.bence@ceg.hu", "project_id": 2, "date": d_str(1), "hours": 8.0, "notes": "Vezetői riport tesztelés"},
        {"id": 111, "email": "szabo.bence@ceg.hu", "project_id": 8, "date": d_str(2), "hours": 4.0, "notes": "Belső szakmai workshop"},
        {"id": 112, "email": "varga.mate@ceg.hu", "project_id": 4, "date": d_str(0), "hours": 6.0, "notes": "Infrastruktúra tanácsadás"},
        {"id": 113, "email": "varga.mate@ceg.hu", "project_id": 5, "date": d_str(1), "hours": 7.5, "notes": "Szerver karbantartás"},
        {"id": 114, "email": "nagy.eszter@ceg.hu", "project_id": 1, "date": d_str(0), "hours": 4.0, "notes": "Projekt mérföldkő kontroll"},
        {"id": 115, "email": "nagy.eszter@ceg.hu", "project_id": 4, "date": d_str(1), "hours": 5.0, "notes": "Havi átalánydíjas riportálás"},
        {"id": 116, "email": "nagy.eszter@ceg.hu", "project_id": 6, "date": d_str(1), "hours": 2.0, "notes": "Erőforrás tervezés"},
        {"id": 117, "email": "kovacs.dori@ceg.hu", "project_id": 1, "date": last_m, "hours": 72.0, "notes": "Alaprendszer előkészítés I. fázis"},
        {"id": 118, "email": "szabo.bence@ceg.hu", "project_id": 2, "date": last_m, "hours": 34.0, "notes": "Adatmodell specifikáció"},
        {"id": 119, "email": "kovacs.dori@ceg.hu", "project_id": 3, "date": last_m, "hours": 17.0, "notes": "Előzetes dokumentum átvilágítás"}
    ])
    return users, projects, logs

def normalize_schemas(users_df, projects_df, logs_df):
    u_Seed, p_Seed, l_Seed = get_seed_data()
    if users_df is None or users_df.empty:
        users_df = u_Seed.copy()
    else:
        for col, default in [("name", ""), ("role", "Dolgozó"), ("title", "Munkatárs"), ("department", "Általános"), ("weekly_capacity", 40)]:
            if col not in users_df.columns:
                users_df[col] = default
        users_df["role"] = users_df["role"].replace({"Vezető": "Admin"})
        users_df["name"] = users_df.apply(lambda r: r["email"].split("@")[0].replace(".", " ").title() if not str(r.get("name", "")).strip() else r["name"], axis=1)
        users_df["weekly_capacity"] = pd.to_numeric(users_df["weekly_capacity"], errors="coerce").fillna(40).astype(int)

    if projects_df is None or projects_df.empty:
        projects_df = p_Seed.copy()
    else:
        if "budget_hours" not in projects_df.columns and "target_hours" in projects_df.columns:
            projects_df["budget_hours"] = projects_df["target_hours"]
        for col, default in [
            ("project_type", "Fixed"), ("budget_hours", 40.0), ("monthly_retainer_hours", 0.0),
            ("manual_completion", 0.0), ("deadline", "-"), ("status", "Aktív"),
            ("color", "#2563EB"), ("owner_email", ""), ("assigned_to", "*"), ("tags", "Projekt")
        ]:
            if col not in projects_df.columns:
                projects_df[col] = default
        projects_df["id"] = pd.to_numeric(projects_df["id"], errors="coerce").fillna(0).astype(int)
        projects_df["budget_hours"] = pd.to_numeric(projects_df["budget_hours"], errors="coerce").fillna(0.0)
        projects_df["monthly_retainer_hours"] = pd.to_numeric(projects_df["monthly_retainer_hours"], errors="coerce").fillna(0.0)
        projects_df["manual_completion"] = pd.to_numeric(projects_df["manual_completion"], errors="coerce").fillna(0.0)
        if not (projects_df["project_type"] == "Admin").any():
            admin_rows = p_Seed[p_Seed["project_type"].isin(["Admin", "Retainer"])].copy()
            max_id = projects_df["id"].max() if not projects_df.empty else 0
            admin_rows["id"] = range(max_id + 1, max_id + 1 + len(admin_rows))
            projects_df = pd.concat([projects_df, admin_rows], ignore_index=True)

    if logs_df is None or logs_df.empty:
        logs_df = l_Seed.copy()
    else:
        if "notes" not in logs_df.columns:
            logs_df["notes"] = ""
        if "id" not in logs_df.columns:
            logs_df["id"] = range(1, len(logs_df) + 1)
        logs_df["project_id"] = pd.to_numeric(logs_df["project_id"], errors="coerce").fillna(0).astype(int)
        logs_df["hours"] = pd.to_numeric(logs_df["hours"], errors="coerce").fillna(0.0)
        logs_df["notes"] = logs_df["notes"].fillna("").astype(str)

    return users_df, projects_df, logs_df

def init_data_store():
    if "db_initialized" not in st.session_state:
        st.session_state.gsheets_connected = False
        u_df, p_df, l_df = None, None, None
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            u_raw = conn.read(worksheet="users", ttl=0).dropna(how="all")
            p_raw = conn.read(worksheet="projects", ttl=0).dropna(how="all")
            l_raw = conn.read(worksheet="logs", ttl=0).dropna(how="all")
            st.session_state.gsheets_conn = conn
            st.session_state.gsheets_connected = True
            u_df, p_df, l_df = normalize_schemas(u_raw, p_raw, l_raw)
            if u_raw.empty:
                conn.update(worksheet="users", data=u_df)
            if p_raw.empty:
                conn.update(worksheet="projects", data=p_df)
            if l_raw.empty:
                conn.update(worksheet="logs", data=l_df)
        except Exception:
            u_df, p_df, l_df = normalize_schemas(None, None, None)

        st.session_state.users_df = u_df
        st.session_state.projects_df = p_df
        st.session_state.logs_df = l_df
        st.session_state.db_initialized = True

def save_table(sheet_name, df):
    st.session_state[f"{sheet_name}_df"] = df.copy()
    if st.session_state.get("gsheets_connected", False):
        try:
            st.session_state.gsheets_conn.update(worksheet=sheet_name, data=df)
        except Exception as e:
            st.toast(f"Google Sheets mentési figyelmeztetés ({sheet_name}): {e}", icon="⚠️")

init_data_store()

# ==============================================================================
# 3. HITELESÍTÉS, DEMÓ SZEREPKÖR-VÁLTÓ ÉS GLOBÁLIS FEJLÉC
# ==============================================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = True
    st.session_state.user_email = st.session_state.users_df.iloc[0]["email"]
    st.session_state.time_format = "decimal"

users_df = st.session_state.users_df
projects_df = st.session_state.projects_df
logs_df = st.session_state.logs_df

if not st.session_state.logged_in:
    col_l1, col_l2, col_l3 = st.columns([1, 1.5, 1])
    with col_l2:
        st.title("⏱️ Chronos Enterprise")
        st.caption("Böngészős és Mobil (PWA) Munkaidő-nyilvántartó")
        t_log, t_pw = st.tabs(["🔑 Bejelentkezés", "🛠️ Jelszó beállítása"])
        with t_log:
            in_email = st.text_input("E-mail cím", value="kiss.tamas@ceg.hu").strip()
            in_pass = st.text_input("Jelszó (demó fiókokhoz: 123)", type="password", value="123").strip()
            if st.button("Belépés a rendszerbe", use_container_width=True, type="primary"):
                match = users_df[users_df["email"].str.lower() == in_email.lower()]
                if not match.empty:
                    saved_pw = str(match.iloc[0]["password"]).replace(".0", "").strip()
                    if saved_pw == in_pass or saved_pw == "":
                        st.session_state.logged_in = True
                        st.session_state.user_email = match.iloc[0]["email"]
                        st.rerun()
                st.error("Hibás e-mail cím vagy jelszó!")
        with t_pw:
            pw_em = st.text_input("Regisztrált e-mail címed")
            pw_new = st.text_input("Új jelszó", type="password")
            if st.button("Jelszó mentése", use_container_width=True):
                idx = users_df[users_df["email"].str.lower() == pw_em.lower()].index
                if len(idx) > 0 and pw_new:
                    users_df.loc[idx[0], "password"] = pw_new
                    save_table("users", users_df)
                    st.success("Jelszó frissítve!")
                else:
                    st.error("Ismeretlen e-mail vagy üres jelszó!")
    st.stop()

top_c1, top_c2, top_c3 = st.columns([2.2, 2.2, 1.4])

with top_c1:
    user_options = users_df["email"].tolist()
    if st.session_state.user_email not in user_options:
        st.session_state.user_email = user_options[0]

    def format_user_option(em):
        row = users_df[users_df["email"] == em].iloc[0]
        return f"🎭 {row['name']} — [{row['role'].upper()}]"

    selected_user_email = st.selectbox(
        "🔄 Aktív Felhasználó / Szerepkör Váltó:",
        options=user_options,
        index=user_options.index(st.session_state.user_email),
        format_func=format_user_option
    )
    if selected_user_email != st.session_state.user_email:
        st.session_state.user_email = selected_user_email
        st.rerun()

current_user = users_df[users_df["email"] == st.session_state.user_email].iloc[0]
current_role = current_user["role"]
current_role_level = ROLE_HIERARCHY.get(current_role, 1)
daily_expected = float(current_user["weekly_capacity"]) / 5.0

with top_c2:
    fmt_map = {
        "decimal": "🔢 Tizedes (2.5 óra)",
        "hhmm": "⌚ Óra:Perc (02:30)",
        "percent": "📊 Napi % (31.3%)"
    }
    st.session_state.time_format = st.radio(
        "⏱️ Időformátum:",
        options=list(fmt_map.keys()),
        format_func=lambda k: fmt_map[k],
        horizontal=True
    )

with top_c3:
    status_badge = "🟢 Google Sheets Live" if st.session_state.get("gsheets_connected") else "🟣 Demó Mód"
    st.markdown(f"<div style='padding-top:12px;'><span class='badge badge-admin'>{status_badge}</span> <span class='badge badge-fixed'>📱 PWA Mobil-kész</span></div>", unsafe_allow_html=True)

with st.sidebar:
    initials = "".join([p[0].upper() for p in str(current_user["name"]).split()[:2]])
    role_cls = "role-admin" if current_role == "Admin" else ("role-pm" if current_role == "Projektgazda" else "role-emp")
    st.markdown(f"""
    <div class="saas-card" style="padding:14px;">
        <div style="display:flex; align-items:center;">
            <div class="avatar-circle" style="background-color:#2563EB;">{initials}</div>
            <div>
                <div style="font-weight:700; font-size:1rem; color:#0f172a;">{current_user['name']}</div>
                <div style="font-size:0.78rem; color:#64748b;">{current_user['title']} • {current_user['department']}</div>
                <span class="badge {role_cls}" style="margin-top:4px;">{current_role}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    today_dt = datetime.now()
    mon_dt = today_dt - timedelta(days=today_dt.weekday())
    sun_dt = mon_dt + timedelta(days=6)
    my_week_logs = logs_df[(logs_df["email"] == current_user["email"]) & (logs_df["date"] >= mon_dt.strftime("%Y-%m-%d")) & (logs_df["date"] <= sun_dt.strftime("%Y-%m-%d"))]
    week_logged_sum = my_week_logs["hours"].sum() if not my_week_logs.empty else 0.0
    week_cap = float(current_user["weekly_capacity"])
    cap_pct = min(100.0, (week_logged_sum / week_cap * 100.0)) if week_cap > 0 else 0.0

    st.markdown("##### 📅 Saját heti kapacitás")
    st.progress(cap_pct / 100.0)
    st.caption(f"Rögzítve: **{format_duration(week_logged_sum, st.session_state.time_format, daily_expected)}** / {week_cap:.0f} óra ({cap_pct:.0f}%)")

    with st.expander("📲 Telepítés Mobil Appként (PWA)"):
        st.markdown("""
        **Android (Chrome):**
        1. Koppints a jobb felső **⋮ (három pont)** menüre.
        2. Válaszd a **„Hozzáadás a kezdőképernyőhöz”** opciót.
        
        **iPhone / iPad (Safari):**
        1. Koppints alul a **Megosztás** ikonra.
        2. Válaszd a **„Főképernyőhöz adás”** opciót.
        """)

    st.divider()
    if st.button("🚪 Kijelentkezés", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# ==============================================================================
# SEGÉDFÜGGVÉNYEK
# ==============================================================================
def get_user_accessible_projects(email_addr):
    if projects_df.empty:
        return pd.DataFrame()
    active_p = projects_df[projects_df["status"] == "Aktív"].copy()
    def is_assigned(row):
        if row["project_type"] == "Admin" or str(row["assigned_to"]).strip() == "*":
            return True
        assigned_list = [x.strip().lower() for x in str(row["assigned_to"]).split(",")]
        return email_addr.lower() in assigned_list
    return active_p[active_p.apply(is_assigned, axis=1)].copy()

def render_project_burn_card(proj_row, logs_data, fmt_mode, daily_exp=8.0):
    pid = proj_row["id"]
    ptype = proj_row["project_type"]
    p_logs = logs_data[logs_data["project_id"] == pid] if not logs_data.empty else pd.DataFrame()
    total_logged = p_logs["hours"].sum() if not p_logs.empty else 0.0
    badge_cls = "badge-fixed" if ptype == "Fixed" else ("badge-retainer" if ptype == "Retainer" else "badge-admin")
    badge_txt = TYPE_LABELS.get(ptype, ptype)
    tags_html = "".join([f"<span class='proj-pill'>{t.strip()}</span>" for t in str(proj_row.get("tags", "")).split(",") if t.strip()])

    if ptype == "Fixed":
        budget = float(proj_row["budget_hours"]) if float(proj_row["budget_hours"]) > 0 else 1.0
        auto_pct = (total_logged / budget) * 100.0
        manual_pct = float(proj_row.get("manual_completion", 0.0))
        bar_color = "#10B981" if auto_pct < 75 else ("#F59E0B" if auto_pct <= 95 else "#EF4444")
        width_pct = min(100.0, auto_pct)
        override_note = f" • 🛠️ Szakmai készültség: <b>{manual_pct:.0f}%</b>" if manual_pct > 0 else ""

        st.markdown(f"""
        <div class="saas-card">
            <div class="saas-card-header">
                <div>
                    <span style="font-weight:700; font-size:1.02rem; color:#0f172a;">{proj_row['name']}</span>
                    <span class="badge {badge_cls}" style="margin-left:6px;">{badge_txt}</span>
                </div>
                <div style="font-size:0.82rem; color:#475569;">Határidő: <b>{proj_row['deadline']}</b></div>
            </div>
            <div style="margin-bottom:6px;">{tags_html}</div>
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; font-size:0.82rem; color:#334155;">
                <span>Ledolgozott: <b>{format_duration(total_logged, fmt_mode, daily_exp)}</b> / Keret: <b>{format_duration(budget, fmt_mode, daily_exp)}</b></span>
                <span>Időarányos: <b>{auto_pct:.1f}%</b>{override_note}</span>
            </div>
            <div class="progress-track">
                <div class="progress-fill" style="width:{width_pct:.1f}%; background-color:{bar_color};"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    elif ptype == "Retainer":
        curr_month = datetime.now().strftime("%Y-%m")
        m_logs = p_logs[p_logs["date"].str.startswith(curr_month)] if not p_logs.empty else pd.DataFrame()
        month_hours = m_logs["hours"].sum() if not m_logs.empty else 0.0
        ind_cap = float(proj_row.get("monthly_retainer_hours", 0.0))
        ind_txt = f" (Indikatív havi: {format_duration(ind_cap, fmt_mode, daily_exp)})" if ind_cap > 0 else " (Korlátlan)"

        st.markdown(f"""
        <div class="saas-card">
            <div class="saas-card-header">
                <div>
                    <span style="font-weight:700; font-size:1.02rem; color:#0f172a;">{proj_row['name']}</span>
                    <span class="badge {badge_cls}" style="margin-left:6px;">♾️ {badge_txt}</span>
                </div>
                <div style="font-size:0.82rem; color:#6b21a8; font-weight:600;">Folyamatos megbízás</div>
            </div>
            <div style="margin-bottom:6px;">{tags_html}</div>
            <div style="font-size:0.82rem; color:#334155;">
                📅 Havi ráfordítás ({curr_month}): <b>{format_duration(month_hours, fmt_mode, daily_exp)}</b>{ind_txt}
                &nbsp;|&nbsp; Összesített: <b>{format_duration(total_logged, fmt_mode, daily_exp)}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ==============================================================================
# FŐ NAVIGÁCIÓS FÜLEK
# ==============================================================================
main_tabs_labels = ["⏱️ Saját Munkaidő (Dolgozói nézet)"]
if current_role_level >= 2:
    main_tabs_labels.append("📂 Projektgazda & Csapat")
if current_role_level >= 3:
    main_tabs_labels.append("🏢 Vállalati Admin")

main_tabs = st.tabs(main_tabs_labels)

# ==============================================================================
# MODUL 1: DOLGOZÓI NÉZET
# ==============================================================================
with main_tabs[0]:
    my_accessible_projs = get_user_accessible_projects(current_user["email"])
    nav_c1, nav_c2, nav_c3 = st.columns([1.4, 2.3, 2.3])
    with nav_c1:
        selected_ref_date = st.date_input("📅 Kiválasztott nap / hét:", datetime.now(), key="emp_ref_date")
    
    start_of_week = selected_ref_date - timedelta(days=selected_ref_date.weekday())
    week_dates = [(start_of_week + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    day_names_short = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]

    sel_date_str = selected_ref_date.strftime("%Y-%m-%d")
    day_logged = logs_df[(logs_df["email"] == current_user["email"]) & (logs_df["date"] == sel_date_str)]["hours"].sum() if not logs_df.empty else 0.0
    week_logged = logs_df[(logs_df["email"] == current_user["email"]) & (logs_df["date"].isin(week_dates))]["hours"].sum() if not logs_df.empty else 0.0

    with nav_c2:
        day_status_icon = "✅ Elérve" if day_logged >= daily_expected else "⏳ Folyamatban"
        st.metric(label=f"Napi rögzített ({sel_date_str}) — {day_status_icon}", value=format_duration(day_logged, st.session_state.time_format, daily_expected), delta=f"Elvárt napi: {format_duration(daily_expected, st.session_state.time_format, daily_expected)}")
    with nav_c3:
        wk_cap = float(current_user["weekly_capacity"])
        wk_status_icon = "✅ Teljesítve" if week_logged >= wk_cap else "📈 Heti egyenleg"
        st.metric(label=f"Heti összesen ({week_dates[0][5:]} – {week_dates[6][5:]}) — {wk_status_icon}", value=format_duration(week_logged, st.session_state.time_format, daily_expected), delta=f"Heti keret: {wk_cap:.0f} óra")

    view_tab1, view_tab2, view_tab3, view_tab4 = st.tabs(["📱 1. Napi & Mobil Gyorsrögzítő", "📊 2. Heti Mátrix (Grid)", "🧱 3. Naptár / Időblokk", "📈 4. Projektek & Analitika"])

    with view_tab1:
        proj_choices = my_accessible_projs["id"].tolist()
        def fmt_proj_label(pid):
            pr = my_accessible_projs[my_accessible_projs["id"] == pid].iloc[0]
            tag = "FIX" if pr["project_type"] == "Fixed" else ("RETAINER" if pr["project_type"] == "Retainer" else "ADMIN")
            return f"[{tag}] {pr['name']}"

        st.markdown('<div class="quick-tap-box">', unsafe_allow_html=True)
        st.markdown("##### ⚡ Mobil Gyorsrögzítő (1 érintéssel a kiválasztott napra)")
        q_col1, q_col2 = st.columns([2, 3])
        with q_col1:
            quick_pid = st.selectbox("Projekt kiválasztása:", options=proj_choices, format_func=fmt_proj_label, key="quick_mobile_proj")
        with q_col2:
            st.caption(f"Koppints egy gombra az azonnali rögzítéshez ({sel_date_str}):")
            b_cols = st.columns(4)
            quick_presets = [("➕ 0.5 ó", 0.5), ("➕ 1 óra", 1.0), ("➕ 2 óra", 2.0), ("✅ 4 óra", 4.0)]
            for idx_q, (btn_label, hrs_q) in enumerate(quick_presets):
                if b_cols[idx_q].button(btn_label, key=f"qbtn_{idx_q}", use_container_width=True):
                    new_log_id = int(logs_df["id"].max() + 1) if not logs_df.empty else 1
                    quick_entry = pd.DataFrame([{"id": new_log_id, "email": current_user["email"], "project_id": int(quick_pid), "date": sel_date_str, "hours": float(hrs_q), "notes": "📱 Mobil gyorsrögzítés"}])
                    save_table("logs", pd.concat([logs_df, quick_entry], ignore_index=True))
                    st.toast(f"Rögzítve: {hrs_q} óra!", icon="✅")
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        dl_col1, dl_col2 = st.columns([1.2, 1.8])
        with dl_col1:
            st.markdown(f"#### ➕ Részletes tétel rögzítése ({sel_date_str})")
            st.caption("Beírhatsz **tizedes órát** (`2.5`), **óra:percet** (`02:30`) vagy **napi %-ot** (`31.25%`).")
            with st.form("daily_log_add_form", clear_on_submit=True):
                sel_pid = st.selectbox("Projekt / Admin tevékenység:", options=proj_choices, format_func=fmt_proj_label)
                raw_time_str = st.text_input("Időtartam (pl. 2.5 vagy 02:30 vagy 25%):", value="1.5")
                note_txt = st.text_input("Megjegyzés / Elvégzett feladat:", placeholder="Pl. Ügyfélegyeztetés, elemzés...")
                if st.form_submit_button("💾 Munkaidő mentése", use_container_width=True, type="primary"):
                    parsed_hrs = parse_duration_input(raw_time_str, daily_expected)
                    if parsed_hrs is None or parsed_hrs <= 0:
                        st.error("Érvénytelen időformátum! Használj pl. '2.5', '02:30' vagy '25%' értéket.")
                    else:
                        new_log_id = int(logs_df["id"].max() + 1) if not logs_df.empty else 1
                        new_entry = pd.DataFrame([{"id": new_log_id, "email": current_user["email"], "project_id": int(sel_pid), "date": sel_date_str, "hours": float(parsed_hrs), "notes": note_txt.strip()}])
                        save_table("logs", pd.concat([logs_df, new_entry], ignore_index=True))
                        st.success(f"Rögzítve: {format_duration(parsed_hrs, st.session_state.time_format, daily_expected)}")
                        st.rerun()

        with dl_col2:
            st.markdown(f"#### 📋 Napi bejegyzések ({sel_date_str})")
            day_entries = logs_df[(logs_df["email"] == current_user["email"]) & (logs_df["date"] == sel_date_str)].copy()
            if day_entries.empty:
                st.info("Erre a napra még nincs rögzített munkaidő.")
            else:
                day_merged = pd.merge(day_entries, projects_df, left_on="project_id", right_on="id", suffixes=("_log", "_proj"))
                for _, item in day_merged.iterrows():
                    pt = item["project_type"]
                    b_cls = "badge-fixed" if pt == "Fixed" else ("badge-retainer" if pt == "Retainer" else "badge-admin")
                    c1, c2 = st.columns([4.2, 1])
                    with c1:
                        st.markdown(f"""
                        <div class="saas-card" style="padding:12px 16px; margin-bottom:8px; border-left: 4px solid {item['color']};">
                            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
                                <div>
                                    <span style="font-weight:700; color:#0f172a;">{item['name']}</span>
                                    <span class="badge {b_cls}" style="margin-left:6px;">{TYPE_LABELS.get(pt, pt)}</span>
                                </div>
                                <span style="font-weight:700; font-size:0.95rem; color:#1e293b;">
                                    {format_duration(item['hours'], st.session_state.time_format, daily_expected)}
                                </span>
                            </div>
                            <div style="font-size:0.82rem; color:#475569; margin-top:4px;">💬 {item['notes'] if item['notes'] else '<i>Nincs megjeg
