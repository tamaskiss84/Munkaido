# -*- coding: utf-8 -*-
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# Oldal beállítása
st.set_page_config(page_title="Munkaidő App", layout="wide")

# Kapcsolódás a Google Sheets-hez
conn = st.connection("gsheets", type=GSheetsConnection)

# --- ADATOK BEOLVASÁSA ---
def get_data(sheet_name):
    # A ttl=0 biztosítja, hogy ne a gyorsítótárból, hanem élőben olvasson
    return conn.read(worksheet=sheet_name, ttl=0)

# --- BEJELENTKEZÉS ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("📱 Munkaidő Belépés")
    u_email = st.text_input("E-mail")
    u_pass = st.text_input("Jelszó", type="password")
    
    if st.button("Belépés"):
        users_df = get_data("users")
        # Ellenőrizzük a felhasználót
        user_match = users_df[(users_df['email'] == u_email) & (users_df['password'].astype(str) == str(u_pass))]
        
        if not user_match.empty:
            st.session_state.logged_in = True
            st.session_state.user_email = user_match.iloc[0]['email']
            st.session_state.user_role = user_match.iloc[0]['role']
            st.rerun()
        else:
            st.error("Hibás belépési adatok!")
    st.stop()

# --- VEZETŐI OLDAL ---
if st.session_state.user_role == "Vezető":
    st.title("Vezetői Dashboard")
    t1, t2 = st.tabs(["Új Projekt", "Kimutatások"])

    with t1:
        st.subheader("Projekt hozzáadása")
        all_users = get_data("users")
        workers = all_users[all_users['role'] == "Dolgozó"]['email'].tolist()
        
        with st.form("proj_form"):
            p_name = st.text_input("Projekt neve")
            p_target = st.number_input("Tervezett órák", min_value=1)
            p_worker = st.selectbox("Dolgozó", workers)
            
            if st.form_submit_button("Mentés"):
                # 1. Meglévő projektek letöltése
                current_projects = get_data("projects")
                # 2. Új sor hozzáadása
                new_id = int(current_projects['id'].max() + 1) if not current_projects.empty else 1
                new_row = pd.DataFrame([{"id": new_id, "name": p_name, "target_hours": p_target, "assigned_to": p_worker}])
                updated_df = pd.concat([current_projects, new_row], ignore_index=True)
                # 3. VISSZAÍRÁS A GOOGLE SHEETS-BE
                conn.update(worksheet="projects", data=updated_df)
                st.success(f"A '{p_name}' projekt sikeresen mentve!")

# --- 2. DOLGOZÓI DASHBOARD (Google Sheets javítás) ---
else:
    st.header("📅 Heti munkarendem")
    
    # 1. Adatok beolvasása a Google Sheets-ből
    projects_all = get_data("projects")
    
    # 2. Szűrés SQL helyett Pandassal (ez javítja az AttributeError-t)
    if not projects_all.empty:
        my_projects_df = projects_all[projects_all['assigned_to'] == st.session_state.user_email]
    else:
        my_projects_df = pd.DataFrame(columns=['id', 'name', 'assigned_to'])

    project_list = my_projects_df['name'].tolist() if not my_projects_df.empty else ["Nincs projekt"]

    # Hét napjainak kiszámítása
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    days = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek"]
    dates = [(start_of_week + timedelta(days=i)) for i in range(5)]

    # Vizualizáció: 5 oszlop a napoknak
    cols = st.columns(5)
    logs_all = get_data("logs")

    for i, col in enumerate(cols):
        current_date = dates[i].strftime("%Y-%m-%d")
        with col:
            st.markdown(f"**{days[i]}**")
            st.caption(current_date)
            
            # Napi órák kiszámítása szűréssel
            if not logs_all.empty:
                daily_sum = logs_all[(logs_all['email'] == st.session_state.user_email) & 
                                     (logs_all['date'] == current_date)]['hours'].sum()
            else:
                daily_sum = 0
            
            if daily_sum >= 8:
                st.success(f"{daily_sum} óra")
            elif daily_sum > 0:
                st.warning(f"{daily_sum} óra")
            else:
                st.error("0 óra")
# Kijelentkezés gomb az alján
if st.sidebar.button("Kijelentkezés"):
    st.session_state.logged_in = False
    st.rerun()
