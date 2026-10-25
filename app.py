# -*- coding: utf-8 -*-
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re

# ==============================================================================
# 0. KONFIGURÁCIÓ ÉS ENTERPRISE UI/UX STYLING (CSS)
# ==============================================================================
st.set_page_config(
    page_title="Chronos Enterprise | Munkaidő & Projekt Controlling",
    page_icon="⏱️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* Alap kártyák és konténerek */
    .saas-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 18px 20px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
        margin-bottom: 16px;
    }
    .saas-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }
    /* Szerepkör és Projekttípus Jelvények (Pills/Badges) */
    .badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }
    .badge-fixed { background-color: #dbeafe; color: #1e40af; }
    .badge-retainer { background-color: #f3e8ff; color: #6b21a8; }
    .badge-admin { background-color: #f1f5f9; color: #475569; }
    
    .role-admin { background-color: #fee2e2; color: #991b1b; }
    .role-pm { background-color: #fef3c7; color: #92400e; }
    .role-emp { background-color: #dcfce7; color: #166534; }

    /* Projekt Tag-ek */
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

    /* Avatar monogram */
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

    /* Progress & Burn Bar */
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
        transition: width 0.3s ease;
    }

    /* Időblokk (Timeblock) vizuális sáv */
    .timeblock-container {
        display: flex;
        width: 100%;
        height: 34px;
        background-color: #f1f5f9;
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #cbd5e1;
        margin-bottom: 8px;
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
</style>
""", unsafe_allow_html=True)

# Színhierarchia konstansok
TYPE_COLORS = {
    "Fixed": "#2563EB",     # Enterprise Kék
    "Retainer": "#7C3AED",  # Átalánydíjas Lila/Türkiz
    "Admin": "#64748B"      # Palaszürke
}

TYPE_LABELS = {
    "Fixed": "Fix keretes projekt",
    "Retainer": "Átalánydíjas (Retainer)",
    "Admin": "Belső / Adminisztratív"
}

ROLE_HIERARCHY = {
    "Dolgozó": 1,
    "Projektgazda": 2,
    "Admin": 3
}

# ==============================================================================
# 1. IDŐFORMÁTUM KONVERTEREK (Tizedes <-> Óra:Perc <-> Napi %)
# ==============================================================================
def format_duration(hours_float, mode="decimal", daily_target=8.0):
    """Megjeleníti a tizedes órákat a választott formátumban."""
    try:
        h = float(hours_float)
    except (ValueError, TypeError):
        h = 0.0

    if mode == "hhmm":
        total_minutes = int(round(h * 60))
        hrs = total_minutes // 60
        mins = total_minutes % 60
        return f"{hrs:02d}:{mins:02d}"
    elif mode == "percent":
        pct = (h / daily_target) * 100.0 if daily_target > 0 else 0.0
        return f"{pct:.1f}%"
    else:
        return f"{h:.2f} óra"

def parse_duration_input(val_str, daily_target=8.0):
    """Értelmezi a '2.5', '2,5', '02:30' vagy '31.25%' formátumú bevitelt."""
    if isinstance(val_str, (int, float)):
        return max(0.0, float(val_str))
    s = str(val_str).strip()
    if not s:
        return 0.0

    try:
        # 1. Százalékos formátum (pl. 31.25% vagy 50 %)
        if s.endswith("%"):
            pct_val = float(s[:-1].replace(",", ".").strip())
            return round((pct_val / 100.0) * daily_target, 2)
        # 2. Óra:Perc formátum (pl. 02:30 vagy 2:15)
        if ":" in s:
            parts = s.split(":")
            hrs = float(parts[0].strip() or 0)
            mins = float(parts[1].strip() or 0)
            return round(hrs + (mins / 60.0), 2)
        # 3. Tizedes óra (pl. 2.5 vagy 2,5)
        clean_s = re.sub(r"[^\d.,-]", "", s).replace(",", ".")
        return round(max(0.0, float(clean_s)), 2) if clean_s else 0.0
    except Exception:
        return None

# ==============================================================================
# 2. DEMÓ ADATOK ÉS ADATBÁZIS (GOOGLE SHEETS + FALLBACK) RÉTEG
# ==============================================================================
def get_seed_data():
    """Életszerű magyar demó adatok a három szerepkörhöz és három projekttípushoz."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    d_str = lambda offset: (monday + timedelta(days=offset)).strftime("%Y-%m-%d")
    last_month_str = (monday - timedelta(days=25)).strftime("%Y-%m-%d")

    users = pd.DataFrame([
        {"email": "kiss.tamas@ceg.hu", "password": "123", "name": "Kiss Tamás", "role": "Admin", "title": "Ügyvezető Igazgató", "department": "Menedzsment", "weekly_capacity": 40},
        {"email": "nagy.eszter@ceg.hu", "password": "123", "name": "Nagy Eszter", "role": "Projektgazda", "title": "Senior Projektmenedzser", "department": "Digitális Üzletág", "weekly_capacity": 40},
        {"email": "kovacs.dori@ceg.hu", "password": "123", "name": "Kovács Dóra", "role": "Dolgozó", "title": "Full-Stack Fejlesztő", "department": "Fejlesztés", "weekly_capacity": 40},
        {"email": "szabo.bence@ceg.hu", "password": "123", "name": "Szabó Bence", "role": "Dolgozó", "title": "UI/UX Designer", "department": "Design Csapat", "weekly_capacity": 40},
        {"email": "varga.mate@ceg.hu", "password": "123", "name": "Varga Máté", "role": "Dolgozó", "title": "Rendszermérnök", "department": "Infrastruktúra", "weekly_capacity": 32},
    ])

    projects = pd.DataFrame([
        # 1. Fix keretes projektek
        {"id": 1, "name": "ERP Rendszer Migráció", "project_type": "Fixed", "budget_hours": 120.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "2026-12-15", "status": "Aktív", "color": "#2563EB", "owner_email": "nagy.eszter@ceg.hu", "assigned_to": "kovacs.dori@ceg.hu,varga.mate@ceg.hu,nagy.eszter@ceg.hu", "tags": "Backend,Kritikus,Q4"},
        {"id": 2, "name": "Mobilbanki App UI Redesign", "project_type": "Fixed", "budget_hours": 60.0, "monthly_retainer_hours": 0.0, "manual_completion": 85.0, "deadline": "2026-11-20", "status": "Aktív", "color": "#0284C7", "owner_email": "nagy.eszter@ceg.hu", "assigned_to": "szabo.bence@ceg.hu,kovacs.dori@ceg.hu,nagy.eszter@ceg.hu", "tags": "Figma,Mobile,Ügyfél"},
        {"id": 3, "name": "E-kereskedelmi Audit", "project_type": "Fixed", "budget_hours": 25.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "2026-10-30", "status": "Aktív", "color": "#DC2626", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "kovacs.dori@ceg.hu,kiss.tamas@ceg.hu", "tags": "Audit,Sürgős"},
        # 2. Átalánydíjas (Retainer) projektek
        {"id": 4, "name": "Átalánydíjas IT és Üzleti Tanácsadás", "project_type": "Retainer", "budget_hours": 0.0, "monthly_retainer_hours": 40.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#7C3AED", "owner_email": "nagy.eszter@ceg.hu", "assigned_to": "kovacs.dori@ceg.hu,varga.mate@ceg.hu,nagy.eszter@ceg.hu,kiss.tamas@ceg.hu", "tags": "Retainer,SLA,Havi"},
        {"id": 5, "name": "24/7 DevOps & Felhő Üzemeltetés", "project_type": "Retainer", "budget_hours": 0.0, "monthly_retainer_hours": 30.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#0D9488", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "varga.mate@ceg.hu,kovacs.dori@ceg.hu", "tags": "AWS,Support"},
        # 3. Belső / Adminisztratív kategóriák (Globális: assigned_to = '*')
        {"id": 6, "name": "Adminisztráció & Napi Operáció", "project_type": "Admin", "budget_hours": 0.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#64748B", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "*", "tags": "Belső,Nem elszámolható"},
        {"id": 7, "name": "Belső Megbeszélés & Sprint Planning", "project_type": "Admin", "budget_hours": 0.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#475569", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "*", "tags": "Meeting,Scrum"},
        {"id": 8, "name": "Oktatás, Képzés & Kutatás", "project_type": "Admin", "budget_hours": 0.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#94A3B8", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "*", "tags": "L&D,Fejlődés"},
        {"id": 9, "name": "Szabadság / Távollét", "project_type": "Admin", "budget_hours": 0.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0, "deadline": "-", "status": "Aktív", "color": "#CBD5E1", "owner_email": "kiss.tamas@ceg.hu", "assigned_to": "*", "tags": "HR,Szabadság"},
    ])

    logs = pd.DataFrame([
        # Kovács Dóra heti logjai
        {"id": 101, "email": "kovacs.dori@ceg.hu", "project_id": 1, "date": d_str(0), "hours": 5.5, "notes": "Adatbázis séma migrációs szkriptek írása"},
        {"id": 102, "email": "kovacs.dori@ceg.hu", "project_id": 4, "date": d_str(0), "hours": 1.5, "notes": "Ügyfél architektúra egyeztetés"},
        {"id": 103, "email": "kovacs.dori@ceg.hu", "project_id": 7, "date": d_str(0), "hours": 1.0, "notes": "Hétindító Sprint Planning"},
        {"id": 104, "email": "kovacs.dori@ceg.hu", "project_id": 1, "date": d_str(1), "hours": 6.0, "notes": "API végpontok refaktorálása"},
        {"id": 105, "email": "kovacs.dori@ceg.hu", "project_id": 2, "date": d_str(1), "hours": 2.0, "notes": "Komponens könyvtár integráció"},
        {"id": 106, "email": "kovacs.dori@ceg.hu", "project_id": 3, "date": d_str(2), "hours": 7.5, "notes": "Biztonsági sérülékenység vizsgálat"},
        {"id": 107, "email": "kovacs.dori@ceg.hu", "project_id": 6, "date": d_str(2), "hours": 0.5, "notes": "Heti adminisztráció"},
        # Szabó Bence heti logjai
        {"id": 108, "email": "szabo.bence@ceg.hu", "project_id": 2, "date": d_str(0), "hours": 7.0, "notes": "Mobilbanki prototípus képernyők"},
        {"id": 109, "email": "szabo.bence@ceg.hu", "project_id": 7, "date": d_str(0), "hours": 1.0, "notes": "Design review"},
        {"id": 110, "email": "szabo.bence@ceg.hu", "project_id": 2, "date": d_str(1), "hours": 8.0, "notes": "Felhasználói tesztelés kiértékelés"},
        {"id": 111, "email": "szabo.bence@ceg.hu", "project_id": 8, "date": d_str(2), "hours": 4.0, "notes": "Design System workshop"},
        # Varga Máté és Nagy Eszter logjai (aktuális + előző hónap a trendekhez és készültséghez)
        {"id": 112, "email": "varga.mate@ceg.hu", "project_id": 4, "date": d_str(0), "hours": 6.0, "notes": "Hálózati topológia tanácsadás"},
        {"id": 113, "email": "varga.mate@ceg.hu", "project_id": 5, "date": d_str(1), "hours": 7.5, "notes": "Kubernetes cluster frissítés"},
        {"id": 114, "email": "nagy.eszter@ceg.hu", "project_id": 1, "date": d_str(0), "hours": 4.0, "notes": "Projekt státusz és mérföldkő kontroll"},
        {"id": 115, "email": "nagy.eszter@ceg.hu", "project_id": 4, "date": d_str(1), "hours": 5.0, "notes": "Havi SLA riportálás ügyfélnek"},
        {"id": 116, "email": "nagy.eszter@ceg.hu", "project_id": 6, "date": d_str(1), "hours": 2.0, "notes": "Erőforrás tervezés"},
        # Korábbi tételek a burn-barok szemléltetéséhez
        {"id": 117, "email": "kovacs.dori@ceg.hu", "project_id": 1, "date": last_month_str, "hours": 72.0, "notes": "Alaprendszer fejlesztés I. fázis"},
        {"id": 118, "email": "szabo.bence@ceg.hu", "project_id": 2, "date": last_month_str, "hours": 34.0, "notes": "Drótvázak és UI kit"},
        {"id": 119, "email": "kovacs.dori@ceg.hu", "project_id": 3, "date": last_month_str, "hours": 17.0, "notes": "Kódbázis átvilágítás"},
    ])
    return users, projects, logs

def normalize_schemas(users_df, projects_df, logs_df):
    """Biztosítja a visszafelé kompatibilitást a korábbi egyszerű táblázatokkal."""
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

        # Ha még nincsenek Admin vagy Retainer elemek a régi táblában, hozzáfűzzük az alapokat
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
    """Kapcsolódik a Google Sheets-hez; ha nem érhető el vagy üres, memóriában is működik."""
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
            # Ha teljesen üres volt a tábla, beírjuk a demó adatokat
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
    """Menti a táblát a Session State-be és szinkronizálja a Google Sheets-szel."""
    st.session_state[f"{sheet_name}_df"] = df.copy()
    if st.session_state.get("gsheets_connected", False):
        try:
            st.session_state.gsheets_conn.update(worksheet=sheet_name, data=df)
        except Exception as e:
            st.toast(f"Google Sheets szinkronizációs figyelmeztetés ({sheet_name}): {e}", icon="⚠️")

init_data_store()

# ==============================================================================
# 3. HITELESÍTÉS, DEMÓ SZEREPKÖR-VÁLTÓ ÉS GLOBÁLIS FEJLÉC
# ==============================================================================
if "logged_in" not in st.session_state:
    # Alapértelmezetten beléptetjük a demó Projektgazdát vagy Admint az azonnali tesztelhetőségért
    st.session_state.logged_in = True
    st.session_state.user_email = st.session_state.users_df.iloc[0]["email"]
    st.session_state.time_format = "decimal"

users_df = st.session_state.users_df
projects_df = st.session_state.projects_df
logs_df = st.session_state.logs_df

# Opcionális klasszikus Login képernyő, ha a felhasználó kijelentkezik
if not st.session_state.logged_in:
    col_l1, col_l2, col_l3 = st.columns([1, 1.5, 1])
    with col_l2:
        st.title("⏱️ Chronos Enterprise")
        st.caption("Vállalati munkaidő-nyilvántartó és projekt-controlling rendszer")
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

# --- FELSŐ ENTERPRISE CONTROL BAR (Demó Szerepkör/Felhasználó Váltó & Időformátum) ---
top_c1, top_c2, top_c3 = st.columns([2.2, 2.2, 1.6])

with top_c1:
    user_options = users_df["email"].tolist()
    if st.session_state.user_email not in user_options:
        st.session_state.user_email = user_options[0]

    def format_user_option(em):
        row = users_df[users_df["email"] == em].iloc[0]
        return f"🎭 {row['name']} — [{row['role'].upper()}] ({row['title']})"

    selected_user_email = st.selectbox(
        "🔄 Aktív Felhasználó / RBAC Szerepkör Tesztelő (Azonnali váltás):",
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
        "decimal": "🔢 Tizedes óra (2.50 óra)",
        "hhmm": "⌚ Óra:Perc (02:30)",
        "percent": "📊 Napi % (31.3%)"
    }
    st.session_state.time_format = st.radio(
        "⏱️ Időformátum megjelenítése:",
        options=list(fmt_map.keys()),
        format_func=lambda k: fmt_map[k],
        horizontal=True
    )

with top_c3:
    st.write("")
    status_badge = "🟢 Google Sheets Live" if st.session_state.get("gsheets_connected") else "🟣 In-Memory Demó Mód"
    st.markdown(f"<div style='text-align:right; padding-top:8px;'><span class='badge badge-admin'>{status_badge}</span></div>", unsafe_allow_html=True)

st.divider()

# --- OLDALSÁV (Profil Kártya & Gyors Kapacitás Indikátor) ---
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

    # Heti saját kapacitás gyors-indikátor
    today_dt = datetime.now()
    mon_dt = today_dt - timedelta(days=today_dt.weekday())
    sun_dt = mon_dt + timedelta(days=6)
    
    my_week_logs = logs_df[
        (logs_df["email"] == current_user["email"]) &
        (logs_df["date"] >= mon_dt.strftime("%Y-%m-%d")) &
        (logs_df["date"] <= sun_dt.strftime("%Y-%m-%d"))
    ]
    week_logged_sum = my_week_logs["hours"].sum() if not my_week_logs.empty else 0.0
    week_cap = float(current_user["weekly_capacity"])
    cap_pct = min(100.0, (week_logged_sum / week_cap * 100.0)) if week_cap > 0 else 0.0

    st.markdown("##### 📅 Saját heti kapacitás")
    st.progress(cap_pct / 100.0)
    st.caption(f"Rögzítve ezen a héten: **{format_duration(week_logged_sum, st.session_state.time_format, daily_expected)}** / {week_cap:.0f} óra ({cap_pct:.0f}%)")

    st.divider()
    st.markdown("##### 🔐 Jogosultsági öröklődés")
    st.markdown(f"""
    - {'✅' if current_role_level >= 1 else '❌'} **Dolgozói modul** *(Saját időrögzítés)*
    - {'✅' if current_role_level >= 2 else '🔒'} **Projektgazda modul** *(Projektek & Csapat)*
    - {'✅' if current_role_level >= 3 else '🔒'} **Admin modul** *(Cégszintű & Beállítások)*
    """)
    
    if st.button("🚪 Kijelentkezés", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# ==============================================================================
# SEGÉDFÜGGVÉNYEK: PROJEKT SZŰRÉS ÉS BURN-BAR KOMPONENS
# ==============================================================================
def get_user_accessible_projects(email_addr):
    """Visszaadja a dolgozóhoz rendelt Aktív projekteket + az összes globális Admin kategóriát."""
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
    """Megjeleníti a projekt kártyát készültségi sávval (Fixed) vagy havi trenddel (Retainer)."""
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
        effective_pct = manual_pct if manual_pct > 0 else auto_pct

        # Színskála: zöld < 75%, sárga 75-95%, piros > 95%
        bar_color = "#10B981" if auto_pct < 75 else ("#F59E0B" if auto_pct <= 95 else "#EF4444")
        width_pct = min(100.0, auto_pct)
        override_note = f" • 🛠️ Szakmai készültség (felülbírált): <b>{manual_pct:.0f}%</b>" if manual_pct > 0 else ""

        st.markdown(f"""
        <div class="saas-card">
            <div class="saas-card-header">
                <div>
                    <span style="font-weight:700; font-size:1.05rem; color:#0f172a;">{proj_row['name']}</span>
                    <span class="badge {badge_cls}" style="margin-left:8px;">{badge_txt}</span>
                </div>
                <div style="font-size:0.85rem; color:#475569;">Határidő: <b>{proj_row['deadline']}</b></div>
            </div>
            <div style="margin-bottom:6px;">{tags_html}</div>
            <div style="display:flex; justify-content:space-between; font-size:0.82rem; color:#334155;">
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
        ind_txt = f" (Indikatív havi keret: {format_duration(ind_cap, fmt_mode, daily_exp)})" if ind_cap > 0 else " (Korlátlan keret)"

        st.markdown(f"""
        <div class="saas-card">
            <div class="saas-card-header">
                <div>
                    <span style="font-weight:700; font-size:1.05rem; color:#0f172a;">{proj_row['name']}</span>
                    <span class="badge {badge_cls}" style="margin-left:8px;">♾️ {badge_txt}</span>
                </div>
                <div style="font-size:0.85rem; color:#6b21a8; font-weight:600;">Folyamatos megbízás</div>
            </div>
            <div style="margin-bottom:6px;">{tags_html}</div>
            <div style="font-size:0.84rem; color:#334155;">
                📅 Aktuális havi ráfordítás ({curr_month}): <b>{format_duration(month_hours, fmt_mode, daily_exp)}</b>{ind_txt}
                &nbsp;|&nbsp; Összesített eddigi: <b>{format_duration(total_logged, fmt_mode, daily_exp)}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ==============================================================================
# FŐ NAVIGÁCIÓS FÜLEK (RBAC ÖRÖKLŐDÉSSEL)
# ==============================================================================
main_tabs_labels = ["⏱️ Saját Munkaidő & Analitika (Dolgozói nézet)"]
if current_role_level >= 2:
    main_tabs_labels.append("📂 Projektgazda & Csapat Irányítópult")
if current_role_level >= 3:
    main_tabs_labels.append("🏢 Vállalati Admin & Globális Beállítások")

main_tabs = st.tabs(main_tabs_labels)

# ==============================================================================
# MODUL 1: DOLGOZÓI NÉZET (Minden szerepkör számára elérhető)
# ==============================================================================
with main_tabs[0]:
    my_accessible_projs = get_user_accessible_projects(current_user["email"])
    
    # Dátum / Hét választó sáv
    nav_c1, nav_c2, nav_c3 = st.columns([1.5, 2.5, 2])
    with nav_c1:
        selected_ref_date = st.date_input("📅 Kiválasztott dátum / hét:", datetime.now(), key="emp_ref_date")
    
    start_of_week = selected_ref_date - timedelta(days=selected_ref_date.weekday())
    week_dates = [(start_of_week + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    day_names_short = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]

    # Napi és heti kapacitás-indikátor kártyák
    sel_date_str = selected_ref_date.strftime("%Y-%m-%d")
    day_logged = logs_df[(logs_df["email"] == current_user["email"]) & (logs_df["date"] == sel_date_str)]["hours"].sum() if not logs_df.empty else 0.0
    week_logged = logs_df[(logs_df["email"] == current_user["email"]) & (logs_df["date"].isin(week_dates))]["hours"].sum() if not logs_df.empty else 0.0

    with nav_c2:
        day_status_icon = "✅ Elérve" if day_logged >= daily_expected else "⏳ Folyamatban"
        st.metric(
            label=f"Napi rögzített idő ({sel_date_str}) — {day_status_icon}",
            value=format_duration(day_logged, st.session_state.time_format, daily_expected),
            delta=f"Elvárt napi: {format_duration(daily_expected, st.session_state.time_format, daily_expected)}"
        )
    with nav_c3:
        wk_cap = float(current_user["weekly_capacity"])
        wk_status_icon = "✅ Teljesítve" if week_logged >= wk_cap else "📈 Heti egyenleg"
        st.metric(
            label=f"Heti összesített ({week_dates[0]} – {week_dates[6]}) — {wk_status_icon}",
            value=format_duration(week_logged, st.session_state.time_format, daily_expected),
            delta=f"Heti keret: {wk_cap:.0f} óra"
        )

    # Nézetváltó fülek a többformátumú munkarögzítéshez
    view_tab1, view_tab2, view_tab3, view_tab4 = st.tabs([
        "📝 1. Napi részletes nézet (Daily Log)",
        "📊 2. Heti mátrix nézet (Timesheet Grid)",
        "🧱 3. Naptár / Időblokk nézet (Timeblock)",
        "📈 4. Saját Projektek & Időmegoszlás"
    ])

    # --------------------------------------------------------------------------
    # 1.1 NAPI RÉSZLETES NÉZET (DAILY LOG)
    # --------------------------------------------------------------------------
    with view_tab1:
        dl_col1, dl_col2 = st.columns([1.2, 1.8])
        
        with dl_col1:
            st.markdown(f"#### ➕ Új tétel rögzítése ({sel_date_str})")
            st.caption("Beírhatsz **tizedes órát** (`2.5`), **óra:percet** (`02:30`) vagy **napi %-ot** (`31.25%`).")
            
            with st.form("daily_log_add_form", clear_on_submit=True):
                proj_choices = my_accessible_projs["id"].tolist()
                def fmt_proj_label(pid):
                    pr = my_accessible_projs[my_accessible_projs["id"] == pid].iloc[0]
                    tag = "FIX" if pr["project_type"] == "Fixed" else ("RETAINER" if pr["project_type"] == "Retainer" else "ADMIN")
                    return f"[{tag}] {pr['name']}"

                sel_pid = st.selectbox("Projekt / Admin tevékenység:", options=proj_choices, format_func=fmt_proj_label)
                raw_time_str = st.text_input("Időtartam (pl. 2.5 vagy 02:30 vagy 25%):", value="1.0")
                note_txt = st.text_input("Megjegyzés / Elvégzett feladat leírása:", placeholder="Pl. Sprint planning vagy API fejlesztés...")
                
                if st.form_submit_button("💾 Munkaidő mentése", use_container_width=True, type="primary"):
                    parsed_hrs = parse_duration_input(raw_time_str, daily_expected)
                    if parsed_hrs is None or parsed_hrs <= 0:
                        st.error("Érvénytelen időformátum! Használj pl. '2.5', '02:30' vagy '25%' értéket.")
                    else:
                        new_log_id = int(logs_df["id"].max() + 1) if not logs_df.empty else 1
                        new_entry = pd.DataFrame([{
                            "id": new_log_id,
                            "email": current_user["email"],
                            "project_id": int(sel_pid),
                            "date": sel_date_str,
                            "hours": float(parsed_hrs),
                            "notes": note_txt.strip()
                        }])
                        updated_logs = pd.concat([logs_df, new_entry], ignore_index=True)
                        save_table("logs", updated_logs)
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
                    c1, c2 = st.columns([4.5, 1])
                    with c1:
                        st.markdown(f"""
                        <div class="saas-card" style="padding:12px 16px; margin-bottom:8px; border-left: 4px solid {item['color']};">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <div>
                                    <span style="font-weight:700; color:#0f172a;">{item['name']}</span>
                                    <span class="badge {b_cls}" style="margin-left:6px;">{TYPE_LABELS.get(pt, pt)}</span>
                                </div>
                                <span style="font-weight:700; font-size:0.95rem; color:#1e293b;">
                                    {format_duration(item['hours'], st.session_state.time_format, daily_expected)}
                                </span>
                            </div>
                            <div style="font-size:0.82rem; color:#475569; margin-top:4px;">💬 {item['notes'] if item['notes'] else '<i>Nincs megjegyzés</i>'}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with c2:
                        if st.button("🗑️ Törlés", key=f"del_log_{item['id_log']}", use_container_width=True):
                            cleaned = logs_df[logs_df["id"] != item["id_log"]]
                            save_table("logs", cleaned)
                            st.rerun()

    # --------------------------------------------------------------------------
    # 1.2 HETI MÁTRIX NÉZET (WEEKLY TIMESHEET GRID)
    # --------------------------------------------------------------------------
    with view_tab2:
        st.markdown("#### ⌨️ Heti Mátrix Táblázat (Gyors billentyűzetes rögzítés)")
        st.caption(
            f"A cellákba közvetlenül írhatsz **tizedes órát** (`2.5`), **óra:percet** (`02:30`) vagy **százalékot** (`50%`). "
            f"Jelenlegi megjelenítési mód: **{fmt_map[st.session_state.time_format]}**."
        )

        # Mátrix felépítése: Sorok = Elérhető projektek + Admin kategóriák, Oszlopok = H-V
        matrix_rows = []
        user_wk_logs = logs_df[(logs_df["email"] == current_user["email"]) & (logs_df["date"].isin(week_dates))]

        for _, proj in my_accessible_projs.iterrows():
            pid = proj["id"]
            row_dict = {
                "Projekt ID": pid,
                "Kategória": TYPE_LABELS.get(proj["project_type"], proj["project_type"]),
                "Projekt / Tevékenység": proj["name"]
            }
            row_total_hrs = 0.0
            for idx, d_iso in enumerate(week_dates):
                col_label = f"{day_names_short[idx][:2]} ({d_iso[5:]})"
                cell_sum = user_wk_logs[(user_wk_logs["project_id"] == pid) & (user_wk_logs["date"] == d_iso)]["hours"].sum() if not user_wk_logs.empty else 0.0
                row_total_hrs += cell_sum
                row_dict[col_label] = format_duration(cell_sum, st.session_state.time_format, daily_expected) if cell_sum > 0 else ""
            row_dict["Heti Összesen"] = format_duration(row_total_hrs, st.session_state.time_format, daily_expected)
            matrix_rows.append(row_dict)

        matrix_df = pd.DataFrame(matrix_rows)
        day_col_names = [f"{day_names_short[i][:2]} ({week_dates[i][5:]})" for i in range(7)]

        edited_matrix = st.data_editor(
            matrix_df,
            disabled=["Projekt ID", "Kategória", "Projekt / Tevékenység", "Heti Összesen"],
            hide_index=True,
            use_container_width=True,
            key=f"weekly_grid_{week_dates[0]}_{st.session_state.time_format}"
        )

        # Napi oszlop-összesítő sáv megjelenítése a mátrix alatt
        summary_cols = st.columns(8)
        summary_cols[0].markdown("**Napi összesen:**")
        for idx, d_iso in enumerate(week_dates):
            d_tot = user_wk_logs[user_wk_logs["date"] == d_iso]["hours"].sum() if not user_wk_logs.empty else 0.0
            color_hex = "#16a34a" if d_tot == daily_expected else ("#d97706" if d_tot > 0 else "#94a3b8")
            summary_cols[idx + 1].markdown(
                f"<span style='color:{color_hex}; font-weight:700;'>{day_names_short[idx][:2]}: {format_duration(d_tot, st.session_state.time_format, daily_expected)}</span>",
                unsafe_allow_html=True
            )

        if st.button("💾 Heti mátrix módosításainak mentése", type="primary"):
            # Megtartjuk a meglévő megjegyzéseket, ha a napi projekt-összeg nem változott, egyébként frissítjük a cellát
            remaining_logs = logs_df[~((logs_df["email"] == current_user["email"]) & (logs_df["date"].isin(week_dates)))].copy()
            new_grid_entries = []
            next_id = int(logs_df["id"].max() + 1) if not logs_df.empty else 1

            for _, r in edited_matrix.iterrows():
                pid = int(r["Projekt ID"])
                for idx, col_label in enumerate(day_col_names):
                    d_iso = week_dates[idx]
                    val_raw = str(r[col_label]).strip()
                    hrs_val = parse_duration_input(val_raw, daily_expected) if val_raw else 0.0
                    if hrs_val and hrs_val > 0:
                        # Korábbi megjegyzés megőrzése, ha volt
                        prev_notes = user_wk_logs[(user_wk_logs["project_id"] == pid) & (user_wk_logs["date"] == d_iso)]["notes"].tolist()
                        merged_note = "; ".join([n for n in prev_notes if n]) if prev_notes else "Heti mátrix rögzítés"
                        new_grid_entries.append({
                            "id": next_id,
                            "email": current_user["email"],
                            "project_id": pid,
                            "date": d_iso,
                            "hours": float(hrs_val),
                            "notes": merged_note
                        })
                        next_id += 1

            updated_all_logs = pd.concat([remaining_logs, pd.DataFrame(new_grid_entries)], ignore_index=True)
            save_table("logs", updated_all_logs)
            st.success("A heti mátrix adatai sikeresen szinkronizálva!")
            st.rerun()

    # --------------------------------------------------------------------------
    # 1.3 NAPTÁR / IDŐBLOKK NÉZET (TIMEBLOCK VIEW)
    # --------------------------------------------------------------------------
    with view_tab3:
        st.markdown("#### 🧱 Vizuális Napi Időblokk Nézet (Arányos napi megoszlás)")
        st.caption(f"A sávok szélessége arányosan mutatja az adott napi munkaidő-felhasználást a napi **{daily_expected:.1f} órás** kapacitáshoz mérten.")

        wk_logs_merged = pd.merge(
            user_wk_logs, projects_df, left_on="project_id", right_on="id", how="inner"
        ) if not user_wk_logs.empty else pd.DataFrame()

        for idx, d_iso in enumerate(week_dates):
            d_df = wk_logs_merged[wk_logs_merged["date"] == d_iso] if not wk_logs_merged.empty else pd.DataFrame()
            d_sum = d_df["hours"].sum() if not d_df.empty else 0.0
            base_denom = max(daily_expected, d_sum, 1.0)

            st.markdown(f"**{day_names_short[idx]} ({d_iso})** — Összesen: `{format_duration(d_sum, st.session_state.time_format, daily_expected)}`")
            
            if d_df.empty:
                st.markdown("""
                <div class="timeblock-container">
                    <div class="timeblock-segment" style="width:100%; background-color:#e2e8f0; color:#64748b;">
                        Nincs rögzített időblokk
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                segments_html = ""
                for _, seg in d_df.iterrows():
                    w_pct = (float(seg["hours"]) / base_denom) * 100.0
                    seg_color = seg["color"] if seg.get("color") else TYPE_COLORS.get(seg["project_type"], "#2563EB")
                    label_str = f"{seg['name']} ({format_duration(seg['hours'], st.session_state.time_format, daily_expected)})"
                    segments_html += f'<div class="timeblock-segment" style="width:{w_pct:.2f}%; background-color:{seg_color};" title="{label_str}">{label_str}</div>'
                
                if d_sum < daily_expected:
                    rem_pct = ((daily_expected - d_sum) / base_denom) * 100.0
                    segments_html += f'<div class="timeblock-segment" style="width:{rem_pct:.2f}%; background-color:#f1f5f9; color:#64748b;">Szabad: {format_duration(daily_expected - d_sum, st.session_state.time_format, daily_expected)}</div>'

                st.markdown(f'<div class="timeblock-container">{segments_html}</div>', unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # 1.4 SAJÁT PROJEKTEK ÁLLÁSA & MUNKAIDŐ-MEGOSZLÁS DIAGRAMOK
    # --------------------------------------------------------------------------
    with view_tab4:
        an_col1, an_col2 = st.columns([1.1, 1.3])

        with an_col1:
            st.markdown("#### 🍩 Saját Munkaidő-megoszlás")
            period_choice = st.radio(
                "Időszak:",
                ["Napi", "Heti", "Havi"],
                horizontal=True,
                key="emp_chart_period"
            )
            my_all_logs = logs_df[logs_df["email"] == current_user["email"]].copy()
            if not my_all_logs.empty:
                if period_choice == "Napi":
                    filtered_l = my_all_logs[my_all_logs["date"] == sel_date_str]
                elif period_choice == "Heti":
                    filtered_l = my_all_logs[my_all_logs["date"].isin(week_dates)]
                else:
                    curr_ym = selected_ref_date.strftime("%Y-%m")
                    filtered_l = my_all_logs[my_all_logs["date"].str.startswith(curr_ym)]

                if not filtered_l.empty:
                    m_chart = pd.merge(filtered_l, projects_df, left_on="project_id", right_on="id")
                    m_chart["Kategória"] = m_chart["project_type"].map(TYPE_LABELS)
                    grp = m_chart.groupby("Kategória")["hours"].sum().reset_index()

                    fig_donut = px.pie(
                        grp, values="hours", names="Kategória", hole=0.58,
                        color="Kategória",
                        color_discrete_map={
                            TYPE_LABELS["Fixed"]: TYPE_COLORS["Fixed"],
                            TYPE_LABELS["Retainer"]: TYPE_COLORS["Retainer"],
                            TYPE_LABELS["Admin"]: TYPE_COLORS["Admin"]
                        }
                    )
                    fig_donut.update_layout(margin=dict(t=15, b=15, l=15, r=15), height=300, legend=dict(orientation="h", y=-0.15))
                    st.plotly_chart(fig_donut, use_container_width=True)
                else:
                    st.info("A kiválasztott időszakban nincs rögzített adat.")
            else:
                st.info("Még nincs rögzített munkaidőd.")

        with an_col2:
            st.markdown("#### 🎯 Hozzám rendelt aktív projektek állása")
            client_projs = my_accessible_projs[my_accessible_projs["project_type"].isin(["Fixed", "Retainer"])]
            if client_projs.empty:
                st.info("Nincs hozzád rendelt ügyfélprojekt.")
            else:
                for _, pr in client_projs.iterrows():
                    render_project_burn_card(pr, logs_df, st.session_state.time_format, daily_expected)


# ==============================================================================
# MODUL 2: PROJEKTGAZDA (PM) ÉS CSAPAT IRÁNYÍTÓPULT (RBAC >= 2)
# ==============================================================================
if current_role_level >= 2:
    with main_tabs[1]:
        pm_sub1, pm_sub2, pm_sub3 = st.tabs([
            "👥 Csapat & Munkatárs Profilok (Utilization)",
            "📂 Projektek Kezelése & Készültségi Fok",
            "📊 Csapat Analitika (Projekt vs. Retainer vs. Admin)"
        ])

        # ----------------------------------------------------------------------
        # 2.1 FELHASZNÁLÓI PROFILOK ÉS MINI-DASHBOARD KÁRTYÁK
        # ----------------------------------------------------------------------
        with pm_sub1:
            st.markdown("#### 👥 Munkatárs Profilok és Heti Kihasználtsági Mutatók (Utilization Rate)")
            st.caption(
                f"Vizsgált hét: **{week_dates[0]} – {week_dates[6]}**. "
                "A kihasználtsági sáv (Utilization Rate) megmutatja az **Ügyfélprojektek (Fix + Átalánydíjas)** és a **Nem elszámolható / Admin** órák arányát."
            )

            f_dept = st.selectbox("Szűrés részleg / csapat szerint:", ["Összes részleg"] + users_df["department"].unique().tolist())
            staff_df = users_df if f_dept == "Összes részleg" else users_df[users_df["department"] == f_dept]

            profile_cols = st.columns(2)
            wk_logs_all = logs_df[logs_df["date"].isin(week_dates)] if not logs_df.empty else pd.DataFrame()
            wk_merged_all = pd.merge(wk_logs_all, projects_df, left_on="project_id", right_on="id") if not wk_logs_all.empty else pd.DataFrame()

            for idx, (_, u_row) in enumerate(staff_df.iterrows()):
                u_em = u_row["email"]
                u_cap = float(u_row["weekly_capacity"])
                u_daily_exp = u_cap / 5.0
                u_logs = wk_merged_all[wk_merged_all["email"] == u_em] if not wk_merged_all.empty else pd.DataFrame()

                tot_wk_hrs = u_logs["hours"].sum() if not u_logs.empty else 0.0
                client_hrs = u_logs[u_logs["project_type"].isin(["Fixed", "Retainer"])]["hours"].sum() if not u_logs.empty else 0.0
                admin_hrs = u_logs[u_logs["project_type"] == "Admin"]["hours"].sum() if not u_logs.empty else 0.0

                billable_util_pct = (client_hrs / tot_wk_hrs * 100.0) if tot_wk_hrs > 0 else 0.0
                admin_util_pct = (admin_hrs / tot_wk_hrs * 100.0) if tot_wk_hrs > 0 else 0.0

                # Aktív projektek címkéi ezen a héten
                active_p_names = u_logs["name"].unique().tolist() if not u_logs.empty else []
                pills_html = "".join([f"<span class='proj-pill'>{pn}</span>" for pn in active_p_names]) if active_p_names else "<span style='color:#94a3b8; font-size:0.78rem;'>Még nincs rögzített projekt a héten</span>"

                u_initials = "".join([p[0].upper() for p in str(u_row["name"]).split()[:2]])
                r_cls = "role-admin" if u_row["role"] == "Admin" else ("role-pm" if u_row["role"] == "Projektgazda" else "role-emp")
                avatar_bg = "#2563EB" if u_row["role"] == "Dolgozó" else ("#7C3AED" if u_row["role"] == "Projektgazda" else "#DC2626")

                with profile_cols[idx % 2]:
                    st.markdown(f"""
                    <div class="saas-card">
                        <div class="saas-card-header">
                            <div style="display:flex; align-items:center;">
                                <div class="avatar-circle" style="background-color:{avatar_bg};">{u_initials}</div>
                                <div>
                                    <div style="font-weight:700; font-size:1.05rem; color:#0f172a;">{u_row['name']}</div>
                                    <div style="font-size:0.8rem; color:#64748b;">{u_row['title']} • <b>{u_row['department']}</b></div>
                                </div>
                            </div>
                            <span class="badge {r_cls}">{u_row['role']}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.82rem; margin-top:10px; color:#334155;">
                            <span>Heti státusz: <b>{format_duration(tot_wk_hrs, st.session_state.time_format, u_daily_exp)}</b> / {u_cap:.0f} óra</span>
                            <span>Kihasználtság: <b style="color:#2563EB;">{billable_util_pct:.0f}% Ügyfél</b> | <b style="color:#64748B;">{admin_util_pct:.0f}% Admin</b></span>
                        </div>
                        <div class="progress-track" style="display:flex; height:10px; margin:8px 0 12px 0;">
                            <div style="width:{billable_util_pct:.1f}%; background-color:#2563EB;" title="Ügyfélprojektek"></div>
                            <div style="width:{admin_util_pct:.1f}%; background-color:#94A3B8;" title="Adminisztráció"></div>
                        </div>
                        <div style="font-size:0.78rem; color:#475569; margin-bottom:4px;"><b>Aktív heti projektek:</b></div>
                        <div>{pills_html}</div>
                    </div>
                    """, unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # 2.2 PROJEKTEK LÉTREHOZÁSA, TESTRESZABÁSA ÉS MANUÁLIS KÉSZÜLTSÉG
        # ----------------------------------------------------------------------
        with pm_sub2:
            pm_c1, pm_c2 = st.columns([1.15, 1.85])

            with pm_c1:
                st.markdown("#### ➕ Új Projekt Létrehozása / Meglévő Szerkesztése")
                edit_mode = st.radio("Művelet:", ["Új projekt indítása", "Meglévő projekt módosítása / Archiválása"], horizontal=True)

                if edit_mode == "Új projekt indítása":
                    with st.form("pm_create_proj_form"):
                        p_name = st.text_input("Projekt megnevezése:")
                        p_type = st.selectbox("Projekttípus:", ["Fixed", "Retainer", "Admin"], format_func=lambda x: TYPE_LABELS[x])
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            p_budget = st.number_input("Fix órakeret (Fixed esetén):", min_value=0.0, value=80.0, step=5.0)
                        with col_b2:
                            p_retainer = st.number_input("Havi indikatív óra (Retainer):", min_value=0.0, value=0.0, step=5.0)
                        p_deadline = st.text_input("Határidő (YYYY-MM-DD vagy '-'):", value="2026-12-31")
                        p_tags = st.text_input("Egyedi címkék (vesszővel elválasztva):", value="Ügyfél,Q4")
                        p_color = st.color_picker("Projekt színkódja:", value="#2563EB")
                        assigned_emps = st.multiselect("Hozzárendelt csapattagok:", options=users_df["email"].tolist(), default=[current_user["email"]])

                        if st.form_submit_button("🚀 Projekt létrehozása", use_container_width=True, type="primary"):
                            if not p_name.strip():
                                st.error("A projekt neve kötelező!")
                            else:
                                new_pid = int(projects_df["id"].max() + 1) if not projects_df.empty else 1
                                assigned_str = "*" if p_type == "Admin" else ",".join(assigned_emps)
                                new_p_row = pd.DataFrame([{
                                    "id": new_pid,
                                    "name": p_name.strip(),
                                    "project_type": p_type,
                                    "budget_hours": float(p_budget) if p_type == "Fixed" else 0.0,
                                    "monthly_retainer_hours": float(p_retainer) if p_type == "Retainer" else 0.0,
                                    "manual_completion": 0.0,
                                    "deadline": p_deadline.strip() if p_type == "Fixed" else "-",
                                    "status": "Aktív",
                                    "color": p_color,
                                    "owner_email": current_user["email"],
                                    "assigned_to": assigned_str,
                                    "tags": p_tags.strip()
                                }])
                                save_table("projects", pd.concat([projects_df, new_p_row], ignore_index=True))
                                st.success(f"'{p_name}' sikeresen létrehozva!")
                                st.rerun()
                else:
                    sel_edit_pid = st.selectbox(
                        "Válaszd ki a szerkesztendő projektet:",
                        options=projects_df["id"].tolist(),
                        format_func=lambda i: f"#{i} - {projects_df[projects_df['id'] == i].iloc[0]['name']}"
                    )
                    curr_p = projects_df[projects_df["id"] == sel_edit_pid].iloc[0]
                    with st.form("pm_edit_proj_form"):
                        e_name = st.text_input("Projekt neve:", value=curr_p["name"])
                        e_status = st.selectbox("Státusz:", ["Aktív", "Archivált"], index=0 if curr_p["status"] == "Aktív" else 1)
                        e_budget = st.number_input("Fix órakeret (budget_hours):", min_value=0.0, value=float(curr_p["budget_hours"]), step=5.0)
                        e_manual_pct = st.slider(
                            "🛠️ Szakmai készültségi fok felülbírálata (0% = automatikus számítás):",
                            min_value=0, max_value=100, value=int(float(curr_p.get("manual_completion", 0.0)))
                        )
                        e_tags = st.text_input("Címkék (Tags):", value=str(curr_p.get("tags", "")))
                        curr_assigned = [x.strip() for x in str(curr_p["assigned_to"]).split(",") if x.strip() in users_df["email"].values]
                        e_assigned = st.multiselect("Csapattagok:", options=users_df["email"].tolist(), default=curr_assigned)

                        if st.form_submit_button("💾 Módosítások mentése", use_container_width=True, type="primary"):
                            idx_p = projects_df[projects_df["id"] == sel_edit_pid].index[0]
                            projects_df.loc[idx_p, "name"] = e_name.strip()
                            projects_df.loc[idx_p, "status"] = e_status
                            projects_df.loc[idx_p, "budget_hours"] = float(e_budget)
                            projects_df.loc[idx_p, "manual_completion"] = float(e_manual_pct)
                            projects_df.loc[idx_p, "tags"] = e_tags.strip()
                            if curr_p["project_type"] != "Admin":
                                projects_df.loc[idx_p, "assigned_to"] = ",".join(e_assigned)
                            save_table("projects", projects_df)
                            st.success("Projekt adatai frissítve!")
                            st.rerun()

            with pm_c2:
                st.markdown("#### 📊 Projekt Portfólió Készültségi & Burn Monitor")
                filter_ptype = st.radio("Szűrés típusra:", ["Összes ügyfélprojekt", "Fixed", "Retainer"], horizontal=True)
                p_view = projects_df[projects_df["status"] == "Aktív"].copy()
                if filter_ptype == "Összes ügyfélprojekt":
                    p_view = p_view[p_view["project_type"].isin(["Fixed", "Retainer"])]
                else:
                    p_view = p_view[p_view["project_type"] == filter_ptype]

                for _, pr in p_view.iterrows():
                    render_project_burn_card(pr, logs_df, st.session_state.time_format, daily_expected)

        # ----------------------------------------------------------------------
        # 2.3 CSAPAT VIZUÁLIS ANALITIKA
        # ----------------------------------------------------------------------
        with pm_sub3:
            st.markdown("#### 📈 Munkaidő-megoszlás: Fix Projekt vs. Átalánydíjas vs. Nem elszámolható / Admin")
            if not logs_df.empty and not projects_df.empty:
                full_an = pd.merge(logs_df, projects_df, left_on="project_id", right_on="id")
                full_an = pd.merge(full_an, users_df[["email", "name", "department"]], on="email", how="left", suffixes=("_proj", "_user"))
                full_an["Kategória"] = full_an["project_type"].map({
                    "Fixed": "1. Fix keretes projektek",
                    "Retainer": "2. Átalánydíjas tanácsadás (Retainer)",
                    "Admin": "3. Nem elszámolható / Admin"
                })

                ch_c1, ch_c2 = st.columns(2)
                with ch_c1:
                    st.markdown("##### 📊 Munkatársankénti óramegoszlás (Stacked Bar)")
                    emp_grp = full_an.groupby(["name_user", "Kategória"])["hours"].sum().reset_index()
                    fig_bar = px.bar(
                        emp_grp, x="name_user", y="hours", color="Kategória",
                        barmode="stack",
                        labels={"name_user": "Munkatárs", "hours": "Rögzített órák"},
                        color_discrete_map={
                            "1. Fix keretes projektek": TYPE_COLORS["Fixed"],
                            "2. Átalánydíjas tanácsadás (Retainer)": TYPE_COLORS["Retainer"],
                            "3. Nem elszámolható / Admin": TYPE_COLORS["Admin"]
                        }
                    )
                    fig_bar.update_layout(height=360, margin=dict(t=20, b=20, l=20, r=20), legend=dict(orientation="h", y=-0.25))
                    st.plotly_chart(fig_bar, use_container_width=True)

                with ch_c2:
                    st.markdown("##### 🍩 Cég / Csapat szintű elszámolhatósági arány")
                    cat_grp = full_an.groupby("Kategória")["hours"].sum().reset_index()
                    fig_pie = px.pie(
                        cat_grp, values="hours", names="Kategória", hole=0.55,
                        color="Kategória",
                        color_discrete_map={
                            "1. Fix keretes projektek": TYPE_COLORS["Fixed"],
                            "2. Átalánydíjas tanácsadás (Retainer)": TYPE_COLORS["Retainer"],
                            "3. Nem elszámolható / Admin": TYPE_COLORS["Admin"]
                        }
                    )
                    fig_pie.update_layout(height=360, margin=dict(t=20, b=20, l=20, r=20), legend=dict(orientation="h", y=-0.25))
                    st.plotly_chart(fig_pie, use_container_width=True)


# ==============================================================================
# MODUL 3: VÁLLALATI ADMIN & GLOBÁLIS BEÁLLÍTÁSOK (RBAC == 3)
# ==============================================================================
if current_role_level >= 3:
    with main_tabs[2]:
        adm_tab1, adm_tab2, adm_tab3 = st.tabs([
            "🏛️ Globális Admin / Overhead Kategóriák",
            "🔐 Felhasználók & RBAC Jogosultságkezelés",
            "📥 Cégszintű Controlling & CSV Export"
        ])

        with adm_tab1:
            ac1, ac2 = st.columns([1, 1.5])
            with ac1:
                st.markdown("#### ➕ Új Globális Admin / Overhead Kategória")
                st.caption("Ezek a kategóriák minden dolgozó számára automatikusan megjelennek a napi és heti rögzítőben.")
                with st.form("admin_cat_form"):
                    cat_name = st.text_input("Kategória neve (pl. Betegszabadság, Céges rendezvény):")
                    cat_tags = st.text_input("Címkék:", value="Belső,Nem elszámolható")
                    if st.form_submit_button("Kategória hozzáadása", use_container_width=True, type="primary"):
                        if cat_name.strip():
                            new_cid = int(projects_df["id"].max() + 1) if not projects_df.empty else 1
                            new_cat = pd.DataFrame([{
                                "id": new_cid, "name": cat_name.strip(), "project_type": "Admin",
                                "budget_hours": 0.0, "monthly_retainer_hours": 0.0, "manual_completion": 0.0,
                                "deadline": "-", "status": "Aktív", "color": "#64748B",
                                "owner_email": current_user["email"], "assigned_to": "*", "tags": cat_tags
                            }])
                            save_table("projects", pd.concat([projects_df, new_cat], ignore_index=True))
                            st.success("Globális admin kategória létrehozva!")
                            st.rerun()
            with ac2:
                st.markdown("#### 📋 Jelenlegi Globális Admin / Overhead Kategóriák")
                adm_projs = projects_df[projects_df["project_type"] == "Admin"][["id", "name", "status", "tags"]]
                st.dataframe(adm_projs, use_container_width=True, hide_index=True)

        with adm_tab2:
            uc1, uc2 = st.columns([1, 1.6])
            with uc1:
                st.markdown("#### 👤 Új Munkatárs Felvétele / RBAC Módosítás")
                with st.form("admin_user_form"):
                    u_em_in = st.text_input("E-mail cím:")
                    u_nm_in = st.text_input("Teljes név:")
                    u_rl_in = st.selectbox("RBAC Szerepkör:", ["Dolgozó", "Projektgazda", "Admin"])
                    u_ti_in = st.text_input("Beosztás (Title):", value="Szoftverfejlesztő")
                    u_dp_in = st.text_input("Csapat / Részleg:", value="Fejlesztés")
                    u_cp_in = st.number_input("Heti elvárt óraszám:", min_value=8, max_value=60, value=40, step=4)

                    if st.form_submit_button("💾 Felhasználó mentése / Frissítése", use_container_width=True, type="primary"):
                        if u_em_in.strip():
                            existing_idx = users_df[users_df["email"].str.lower() == u_em_in.strip().lower()].index
                            if len(existing_idx) > 0:
                                i = existing_idx[0]
                                users_df.loc[i, ["name", "role", "title", "department", "weekly_capacity"]] = [
                                    u_nm_in.strip(), u_rl_in, u_ti_in.strip(), u_dp_in.strip(), int(u_cp_in)
                                ]
                            else:
                                new_u_row = pd.DataFrame([{
                                    "email": u_em_in.strip(), "password": "123", "name": u_nm_in.strip(),
                                    "role": u_rl_in, "title": u_ti_in.strip(), "department": u_dp_in.strip(),
                                    "weekly_capacity": int(u_cp_in)
                                }])
                                users_df = pd.concat([users_df, new_u_row], ignore_index=True)
                            save_table("users", users_df)
                            st.success("Felhasználói adatok és jogosultságok mentve!")
                            st.rerun()
            with uc2:
                st.markdown("#### 👥 Teljes Felhasználói és Jogosultsági Lista")
                st.dataframe(
                    users_df[["name", "email", "role", "title", "department", "weekly_capacity"]],
                    use_container_width=True, hide_index=True
                )

        with adm_tab3:
            st.markdown("#### 📊 Cégszintű Controlling Adattábla és Export")
            if not logs_df.empty:
                export_df = pd.merge(logs_df, projects_df[["id", "name", "project_type", "budget_hours"]], left_on="project_id", right_on="id", suffixes=("_log", "_proj"))
                export_df = pd.merge(export_df, users_df[["email", "name", "department", "role"]], on="email", how="left", suffixes=("_proj", "_user"))
                st.dataframe(
                    export_df[["date", "name_user", "department", "name_proj", "project_type", "hours", "notes"]],
                    use_container_width=True, hide_index=True
                )
                csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📥 Teljes Vállalati Munkaidő Riport Letöltése (CSV / Excel)",
                    data=csv_bytes,
                    file_name=f"chronos_enterprise_riport_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    type="primary"
                )
