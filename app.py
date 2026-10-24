# -*- coding: utf-8 -*-
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# Oldal konfiguráció (mobilbarát elrendezés)
st.set_page_config(page_title="Projekt Munkaidő App", page_icon="⏱️", layout="wide")

# Kapcsolódás a Google Sheets-hez
conn = st.connection("gsheets", type=GSheetsConnection)

# --- SEGÉDFÜGGVÉNYEK ADATKEZELÉSHEZ ---
def get_data(sheet_name):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        return df.dropna(how="all")
    except Exception as e:
        st.error(f"Hiba a(z) '{sheet_name}' munkalap olvasásakor: {e}")
        return pd.DataFrame()

def save_data(sheet_name, df):
    conn.update(worksheet=sheet_name, data=df)

# --- WORKFLOW & SESSION STATE INICIALIZÁLÁSA ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_email = ""
    st.session_state.user_role = ""

# ==========================================
# 1. BEJELENTKEZÉS ÉS JELSZÓ GENERÁLÁS
# ==========================================
if not st.session_state.logged_in:
    st.title("📱 Munkaidő Nyilvántartó")
    
    tab_login, tab_pw = st.tabs(["🔑 Bejelentkezés", "🛠️ Jelszó beállítása / Módosítása"])
    
    with tab_login:
        st.subheader("Belépés")
        u_email = st.text_input("E-mail cím", key="login_email").strip()
        u_pass = st.text_input("Jelszó", type="password", key="login_pass").strip()
        
        if st.button("Belépés", use_container_width=True):
            users_df = get_data("users")
            if not users_df.empty and 'email' in users_df.columns:
                users_df['email'] = users_df['email'].astype(str).str.strip()
                users_df['password'] = users_df['password'].fillna("").astype(str).str.strip()
                # Pontos karakter-összehasonlítás (.0 levágása, ha a Sheets számnak nézné a jelszót)
                users_df['password'] = users_df['password'].apply(lambda x: x[:-2] if x.endswith('.0') else x)
                
                user_match = users_df[(users_df['email'].str.lower() == u_email.lower()) & (users_df['password'] == u_pass)]
                
                if not user_match.empty:
                    if u_pass == "":
                        st.warning("Még nincs beállítva jelszavad! Kérlek, használd a 'Jelszó beállítása' fület!")
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user_email = user_match.iloc[0]['email']
                        st.session_state.user_role = user_match.iloc[0]['role']
                        st.rerun()
                else:
                    st.error("Hibás e-mail cím vagy jelszó!")
            else:
                st.error("A 'users' tábla üres vagy nem érhető el.")

    with tab_pw:
        st.subheader("Saját jelszó generálása / megváltoztatása")
        st.info("Ha a vezető felvette az e-mail címedet, itt állíthatsz be magadnak új jelszót.")
        pw_email = st.text_input("Regisztrált E-mail címed", key="pw_email").strip()
        old_pw = st.text_input("Jelenlegi jelszó (hagyd üresen, ha most lépsz be először)", type="password").strip()
        new_pw = st.text_input("Új jelszó", type="password").strip()
        new_pw_conf = st.text_input("Új jelszó megerősítése", type="password").strip()
        
        if st.button("Jelszó mentése", use_container_width=True):
            if not new_pw or new_pw != new_pw_conf:
                st.error("Az új jelszavak nem egyeznek, vagy üresen hagytad a mezőt!")
            else:
                users_df = get_data("users")
                users_df['email_clean'] = users_df['email'].astype(str).str.strip().str.lower()
                users_df['pw_clean'] = users_df['password'].fillna("").astype(str).str.strip()
                users_df['pw_clean'] = users_df['pw_clean'].apply(lambda x: x[:-2] if x.endswith('.0') else x)
                
                user_idx = users_df[users_df['email_clean'] == pw_email.lower()].index
                
                if len(user_idx) == 0:
                    st.error("Ez az e-mail cím nincs a rendszerben! Kérd meg a vezetőt, hogy vegyen fel.")
                else:
                    idx = user_idx[0]
                    current_saved_pw = users_df.loc[idx, 'pw_clean']
                    if current_saved_pw != "" and current_saved_pw != old_pw:
                        st.error("A jelenlegi jelszó hibás!")
                    else:
                        users_df.loc[idx, 'password'] = str(new_pw)
                        users_df = users_df.drop(columns=['email_clean', 'pw_clean'])
                        save_data("users", users_df)
                        st.success("Jelszó sikeresen beállítva! Most már átléphetsz a Bejelentkezés fülre.")
    st.stop()

# ==========================================
# OLDALSÁV (KÖZÖS ELEMEK)
# ==========================================
st.sidebar.title("👤 Profil")
st.sidebar.write(f"**E-mail:** {st.session_state.user_email}")
st.sidebar.write(f"**Szerepkör:** {st.session_state.user_role}")
if st.sidebar.button("🚪 Kijelentkezés", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# Adatok betöltése a közös munkához
users_df = get_data("users")
projects_df = get_data("projects")
logs_df = get_data("logs")

# Típuskonverziók az adatok tisztaságáért
if not projects_df.empty:
    projects_df['id'] = pd.to_numeric(projects_df['id'], errors='coerce').fillna(0).astype(int)
    projects_df['target_hours'] = pd.to_numeric(projects_df['target_hours'], errors='coerce').fillna(0.0)
if not logs_df.empty:
    logs_df['project_id'] = pd.to_numeric(logs_df['project_id'], errors='coerce').fillna(0).astype(int)
    logs_df['hours'] = pd.to_numeric(logs_df['hours'], errors='coerce').fillna(0.0)

# ==========================================
# 2. VEZETŐI DASHBOARD
# ==========================================
if st.session_state.user_role == "Vezető":
    st.title("👔 Vezetői Dashboard")
    
    t_proj, t_users, t_stats = st.tabs(["📂 Projektek & Nyilvántartás", "👥 Dolgozók & Szerepkörök", "📊 Statisztikák"])
    
    # --- 2.1 PROJEKTEK KEZELÉSE ---
    with t_proj:
        col_form, col_table = st.columns([1, 2])
        
        with col_form:
            st.subheader("➕ Új projekt kiosztása")
            worker_emails = users_df['email'].dropna().unique().tolist() if not users_df.empty else []
            
            with st.form("new_proj_form"):
                p_name = st.text_input("Projekt neve")
                p_target = st.number_input("Tervezett óraszám", min_value=1.0, step=1.0, value=40.0)
                p_worker = st.selectbox("Felelős dolgozó", worker_emails if worker_emails else ["Nincs dolgozó"])
                
                if st.form_submit_button("Projekt létrehozása", use_container_width=True):
                    if p_name and p_worker != "Nincs dolgozó":
                        new_id = int(projects_df['id'].max() + 1) if not projects_df.empty else 1
                        new_row = pd.DataFrame([{
                            "id": new_id,
                            "name": p_name,
                            "target_hours": float(p_target),
                            "assigned_to": p_worker
                        }])
                        updated_projs = pd.concat([projects_df, new_row], ignore_index=True)
                        save_data("projects", updated_projs)
                        st.success(f"'{p_name}' projekt létrehozva (ID: {new_id})!")
                        st.rerun()
                    else:
                        st.error("Kérlek, adj meg projektnevet és válassz dolgozót!")

        with col_table:
            st.subheader("📋 Projektenkénti nyilvántartás")
            if not projects_df.empty:
                # Tényleges órák hozzászámítása a logs táblából
                if not logs_df.empty:
                    actual_totals = logs_df.groupby('project_id')['hours'].sum().reset_index()
                    actual_totals.rename(columns={'hours': 'actual_hours'}, inplace=True)
                    merged_projs = pd.merge(projects_df, actual_totals, left_on='id', right_on='project_id', how='left')
                    merged_projs['actual_hours'] = merged_projs['actual_hours'].fillna(0.0)
                else:
                    merged_projs = projects_df.copy()
                    merged_projs['actual_hours'] = 0.0

                # Szűrési lehetőségek
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    filter_worker = st.selectbox("Szűrés dolgozóra", ["Összes"] + merged_projs['assigned_to'].unique().tolist())
                with f_col2:
                    filter_proj = st.text_input("Szűrés projekt nevére")
                
                display_df = merged_projs.copy()
                if filter_worker != "Összes":
                    display_df = display_df[display_df['assigned_to'] == filter_worker]
                if filter_proj:
                    display_df = display_df[display_df['name'].str.contains(filter_proj, case=False, na=False)]
                
                display_df = display_df[['id', 'name', 'assigned_to', 'target_hours', 'actual_hours']]
                display_df.columns = ['Projekt ID', 'Projekt Neve', 'Felelős Dolgozó', 'Tervezett Óra', 'Tényleges Óra']
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("Még nincsenek projektek rögzítve.")

    # --- 2.2 DOLGOZÓK ÉS SZEREPKÖRÖK ---
    with t_users:
        col_u1, col_u2 = st.columns(2)
        
        with col_u1:
            st.subheader("📧 Új felhasználó felvétele")
            with st.form("add_user_form"):
                new_email = st.text_input("Dolgozó e-mail címe").strip()
                new_role = st.selectbox("Kezdő szerepkör", ["Dolgozó", "Vezető"])
                init_pw = st.text_input("Kezdeti jelszó (hagyd üresen, ha a dolgozó generálja magának)")
                
                if st.form_submit_button("Hozzáadás", use_container_width=True):
                    if new_email:
                        if not users_df.empty and new_email.lower() in users_df['email'].astype(str).str.lower().values:
                            st.error("Ez az e-mail cím már szerepel a rendszerben!")
                        else:
                            new_u = pd.DataFrame([{"email": new_email, "password": str(init_pw), "role": new_role}])
                            updated_u = pd.concat([users_df, new_u], ignore_index=True)
                            save_data("users", updated_u)
                            st.success(f"{new_email} hozzáadva a rendszerhez!")
                            st.rerun()
        
        with col_u2:
            st.subheader("🔄 Szerepkör módosítása")
            if not users_df.empty:
                with st.form("role_mod_form"):
                    sel_u = st.selectbox("Válassz felhasználót", users_df['email'].tolist())
                    mod_role = st.selectbox("Új szerepkör", ["Dolgozó", "Vezető"])
                    if st.form_submit_button("Szerepkör frissítése", use_container_width=True):
                        users_df.loc[users_df['email'] == sel_u, 'role'] = mod_role
                        save_data("users", users_df)
                        st.success(f"{sel_u} új szerepköre: {mod_role}")
                        st.rerun()
                
                st.write("**Jelenlegi felhasználók:**")
                st.dataframe(users_df[['email', 'role']].rename(columns={'email': 'E-mail', 'role': 'Szerepkör'}), use_container_width=True, hide_index=True)

    # --- 2.3 STATISZTIKÁK (NAPI, NEGYEDÉVES, ÉVES) ---
    with t_stats:
        st.subheader("📈 Kimutatások és Elemzések")
        if not projects_df.empty:
            # 1. Egy dolgozóra jutó projektek száma
            st.markdown("#### 👤 Egy dolgozóra jutó projektek száma")
            proj_per_worker = projects_df.groupby('assigned_to')['id'].count().reset_index()
            proj_per_worker.columns = ['Dolgozó', 'Kiosztott projektek (db)']
            st.dataframe(proj_per_worker, use_container_width=True, hide_index=True)
            
        if not logs_df.empty and not projects_df.empty:
            full_df = pd.merge(logs_df, projects_df, left_on='project_id', right_on='id', how='inner')
            full_df['date_dt'] = pd.to_datetime(full_df['date'])
            full_df['Év'] = full_df['date_dt'].dt.year.astype(str)
            full_df['Negyedév'] = full_df['date_dt'].dt.to_period('Q').astype(str)
            
            st.divider()
            # 2. Tervezett vs Tényleges óraszámok
            st.markdown("#### 🎯 Projektek: Tervezett vs. Tényleges óraszám")
            p_comp = full_df.groupby('name').agg({'hours': 'sum', 'target_hours': 'first'}).reset_index()
            p_comp.rename(columns={'name': 'Projekt', 'hours': 'Tényleges Óra', 'target_hours': 'Tervezett Óra'}, inplace=True)
            st.bar_chart(p_comp.set_index('Projekt')[['Tervezett Óra', 'Tényleges Óra']])
            
            st.divider()
            # 3. Negyedéves és Éves összesítők
            c_stat1, c_stat2 = st.columns(2)
            with c_stat1:
                st.markdown("#### 📅 Negyedéves összesítő (Órák projektenként)")
                q_pivot = full_df.groupby(['Negyedév', 'name'])['hours'].sum().unstack().fillna(0)
                st.dataframe(q_pivot, use_container_width=True)
                st.bar_chart(q_pivot)
                
            with c_stat2:
                st.markdown("#### 📆 Éves összesítő (Órák projektenként)")
                y_pivot = full_df.groupby(['Év', 'name'])['hours'].sum().unstack().fillna(0)
                st.dataframe(y_pivot, use_container_width=True)
                st.bar_chart(y_pivot)

            st.divider()
            # 4. Napi munkaidő statisztika
            st.markdown("#### ⏱️ Napi munkaidő alakulása dolgozónként")
            daily_w = full_df.groupby(['date', 'email'])['hours'].sum().unstack().fillna(0)
            st.line_chart(daily_w)
            
            # CSV Export
            csv_data = full_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Teljes riport letöltése (CSV)", data=csv_data, file_name="munkaido_statisztika.csv", mime="text/csv")
        else:
            st.info("Még nincs elég rögzített munkaóra a részletes statisztikákhoz.")

# ==========================================
# 3. DOLGOZÓI DASHBOARD
# ==========================================
else:
    st.title("👷 Dolgozói Dashboard")
    
    # Saját projektek kiszűrése
    if not projects_df.empty:
        my_projs = projects_df[projects_df['assigned_to'] == st.session_state.user_email].copy()
    else:
        my_projs = pd.DataFrame(columns=['id', 'name', 'target_hours', 'assigned_to'])

    # --- 3.1 HETI NAPTÁR ÉS 8 SLOTOS RÖGZÍTŐ ---
    st.subheader("📅 Heti Naptár és Munkaidő Rögzítés")
    
    col_nav1, col_nav2 = st.columns([2, 2])
    with col_nav1:
        ref_date = st.date_input("Válassz hetet (bármelyik napját):", datetime.now())
    with col_nav2:
        include_weekend = st.checkbox("Hétvégi napok (Szombat-Vasárnap) megjelenítése munkanapként", value=False)
        
    start_of_week = ref_date - timedelta(days=ref_date.weekday())
    day_names = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]
    active_days_count = 7 if include_weekend else 5
    
    # Heti áttekintő kártyák
    week_cols = st.columns(active_days_count)
    week_dates = []
    
    for i in range(active_days_count):
        d_str = (start_of_week + timedelta(days=i)).strftime("%Y-%m-%d")
        week_dates.append(d_str)
        with week_cols[i]:
            st.markdown(f"**{day_names[i]}**")
            st.caption(d_str)
            
            day_sum = 0.0
            if not logs_df.empty:
                day_sum = logs_df[(logs_df['email'] == st.session_state.user_email) & (logs_df['date'] == d_str)]['hours'].sum()
            
            if day_sum == 8.0:
                st.success(f"{day_sum} / 8 óra")
            elif day_sum > 8.0:
                st.warning(f"{day_sum} / 8 óra (Túllépés!)")
            elif day_sum > 0:
                st.info(f"{day_sum} / 8 óra")
            else:
                st.error("0 / 8 óra")

    st.divider()

    # --- NAPI 8 SLOTOS BEVITELI ÍV ---
    if my_projs.empty:
        st.warning("Jelenleg nincs rád kiosztva egyetlen projekt sem. Kérd meg a vezetőt a kiosztásra!")
    else:
        selected_day_idx = st.selectbox(
            "👉 Válaszd ki a szerkesztendő napot a héten:", 
            range(active_days_count), 
            format_func=lambda x: f"{day_names[x]} ({week_dates[x]})"
        )
        target_date_str = week_dates[selected_day_idx]
        
        st.markdown(f"#### 📝 Munkaidő slotok kitöltése: **{day_names[selected_day_idx]} ({target_date_str})**")
        st.caption("A napi munkaidő 8 órából áll. Egy napra több projektet is beállíthatsz a 8 slotban. Mentéskor az aznapi korábbi bejegyzéseid felülíródnak az itt megadottakkal.")
        
        # Meglévő adatok visszatöltése az adott napra
        existing_day_logs = pd.DataFrame()
        if not logs_df.empty:
            existing_day_logs = logs_df[(logs_df['email'] == st.session_state.user_email) & (logs_df['date'] == target_date_str)].reset_index(drop=True)
            
        proj_options = ["-- Üres slot --"] + my_projs['name'].tolist()
        
        with st.form("daily_8_slots_form"):
            slot_selections = []
            # 8 slot megjelenítése 2 oszlopban a mobilbarát és átlátható nézetért
            scol1, scol2 = st.columns(2)
            
            for s in range(8):
                target_col = scol1 if s < 4 else scol2
                with target_col:
                    st.markdown(f"**{s+1}. Slot**")
                    c_p, c_h = st.columns([3, 2])
                    
                    # Alapértelmezett értékek, ha már volt mentés erre a napra
                    default_proj_idx = 0
                    default_hr = 0.0
                    if s < len(existing_day_logs):
                        saved_pid = existing_day_logs.loc[s, 'project_id']
                        saved_hr = float(existing_day_logs.loc[s, 'hours'])
                        matched_p = my_projs[my_projs['id'] == saved_pid]['name'].tolist()
                        if matched_p and matched_p[0] in proj_options:
                            default_proj_idx = proj_options.index(matched_p[0])
                            default_hr = saved_hr
                            
                    with c_p:
                        sel_p = st.selectbox(f"Projekt #{s+1}", proj_options, index=default_proj_idx, key=f"slot_p_{s}_{target_date_str}", label_visibility="collapsed")
                    with c_h:
                        sel_h = st.number_input(f"Óra #{s+1}", min_value=0.0, max_value=8.0, step=0.5, value=default_hr, key=f"slot_h_{s}_{target_date_str}", label_visibility="collapsed")
                    
                    slot_selections.append((sel_p, sel_h))
                    
            if st.form_submit_button("💾 Napi 8 slot mentése és összesítése", use_container_width=True):
                valid_entries = []
                total_day_hours = 0.0
                
                for p_name, h_val in slot_selections:
                    if p_name != "-- Üres slot --" and h_val > 0:
                        pid = int(my_projs[my_projs['name'] == p_name]['id'].iloc[0])
                        valid_entries.append({
                            "email": st.session_state.user_email,
                            "project_id": pid,
                            "date": target_date_str,
                            "hours": float(h_val)
                        })
                        total_day_hours += float(h_val)
                
                # Korábbi aznapi logok törlése és az új 8 slot beírása
                if not logs_df.empty:
                    cleaned_logs = logs_df[~((logs_df['email'] == st.session_state.user_email) & (logs_df['date'] == target_date_str))]
                else:
                    cleaned_logs = pd.DataFrame(columns=['email', 'project_id', 'date', 'hours'])
                    
                new_logs_df = pd.DataFrame(valid_entries)
                updated_logs = pd.concat([cleaned_logs, new_logs_df], ignore_index=True)
                save_data("logs", updated_logs)
                
                if total_day_hours > 8.0:
                    st.warning(f"Mentve! Figyelem: A napi összesített munkaidőd ({total_day_hours} óra) meghaladja a 8 órát!")
                else:
                    st.success(f"Sikeres mentés! Napi összesített munkaidő: {total_day_hours} óra.")
                st.rerun()

    st.divider()

    # --- 3.2 SAJÁT PROJEKTTÁBLA ÉS SZŰRŐ ---
    st.subheader("📂 Rám kiosztott projektek állása")
    if not my_projs.empty:
        if not logs_df.empty:
            # Projekt összesített tényleges órái
            proj_totals = logs_df.groupby('project_id')['hours'].sum().reset_index().rename(columns={'hours': 'actual_total'})
            # Saját ledolgozott órák az adott projekten
            my_Logs_sum = logs_df[logs_df['email'] == st.session_state.user_email].groupby('project_id')['hours'].sum().reset_index().rename(columns={'hours': 'my_hours'})
            
            my_projs = pd.merge(my_projs, proj_totals, left_on='id', right_on='project_id', how='left')
            my_projs = pd.merge(my_projs, my_Logs_sum, left_on='id', right_on='project_id', how='left')
            my_projs['actual_total'] = my_projs['actual_total'].fillna(0.0)
            my_projs['my_hours'] = my_projs['my_hours'].fillna(0.0)
        else:
            my_projs['actual_total'] = 0.0
            my_projs['my_hours'] = 0.0
            
        search_p = st.text_input("🔍 Szűrés a saját projektjeim között (név alapján):")
        if search_p:
            my_projs = my_projs[my_projs['name'].str.contains(search_p, case=False, na=False)]
            
        show_my_p = my_projs[['id', 'name', 'target_hours', 'my_hours', 'actual_total']]
        show_my_p.columns = ['Projekt ID', 'Projekt Neve', 'Tervezett Óraszám', 'Saját Ledolgozott Óra', 'Projekt Összes Tényleges Óra']
        st.dataframe(show_my_p, use_container_width=True, hide_index=True)
