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

# --- DOLGOZÓI OLDAL ---
else:
    st.title("Dolgozói Dashboard")
    
    # Adatok lekérése
    projects_df = get_data("projects")
    my_projs = projects_df[projects_df['assigned_to'] == st.session_state.user_email]
    
    if my_projs.empty:
        st.warning("Nincs hozzád rendelt projekt.")
    else:
        with st.form("work_form"):
            st.subheader("Munkaidő rögzítése")
            sel_proj = st.selectbox("Válassz projektet", my_projs['name'].tolist())
            hours = st.number_input("Ledolgozott órák (pl. 0.5 vagy 2)", min_value=0.5, max_value=8.0, step=0.5)
            date_now = datetime.now().strftime("%Y-%m-%d")
            
            if st.form_submit_button("Küldés"):
                # 1. Meglévő logok letöltése
                current_logs = get_data("logs")
                proj_id = my_projs[my_projs['name'] == sel_proj]['id'].values[0]
                
                # 2. Új log sor
                new_log = pd.DataFrame([{
                    "email": st.session_state.user_email,
                    "project_id": int(proj_id),
                    "date": date_now,
                    "hours": float(hours)
                }])
                
                updated_logs = pd.concat([current_logs, new_log], ignore_index=True)
                # 3. VISSZAÍRÁS A GOOGLE SHEETS-BE
                conn.update(worksheet="logs", data=updated_logs)
                st.balloons()
                st.success("A munkaóra rögzítve a Google Táblázatban!")

# Kijelentkezés gomb az alján
if st.sidebar.button("Kijelentkezés"):
    st.session_state.logged_in = False
    st.rerun()
