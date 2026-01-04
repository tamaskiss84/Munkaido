# -*- coding: utf-8 -*-
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

# Oldal konfiguráció (mobilbarát nézet)
st.set_page_config(page_title="Munkaidő App", layout="wide")

# --- KAPCSOLÓDÁS A GOOGLE SHEETS-HEZ ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data(sheet_name):
    # Adatok beolvasása (gyorsítótár nélkül, hogy mindig friss legyen)
    return conn.read(worksheet=sheet_name, ttl=0)

# --- BEJELENTKEZÉS KEZELÉSE ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("📱 Munkaidő Belépés")
    email_input = st.text_input("E-mail")
    pass_input = st.text_input("Jelszó", type="password")
    
    if st.button("Belépés"):
        users_df = get_data("users")
        user = users_df[(users_df['email'] == email_input) & (users_df['password'] == str(pass_input))]
        
        if not user.empty:
            st.session_state.logged_in = True
            st.session_state.user_email = user.iloc[0]['email']
            st.session_state.user_role = user.iloc[0]['role']
            st.rerun()
        else:
            st.error("Hibás e-mail vagy jelszó!")
    st.stop()

# --- OLDALSÁV (KIJELENTKEZÉS) ---
st.sidebar.write(f"Szia, **{st.session_state.user_email}**!")
st.sidebar.info(f"Jogkör: {st.session_state.user_role}")
if st.sidebar.button("Kijelentkezés"):
    st.session_state.logged_in = False
    st.rerun()

# --- VEZETŐI FUNKCIÓK ---
if st.session_state.user_role == "Vezető":
    tab1, tab2, tab3 = st.tabs(["Projektek", "Dolgozók", "Statisztika"])

    with tab1:
        st.subheader("Új projekt kiírása")
        users_df = get_data("users")
        worker_list = users_df[users_df['role'] == 'Dolgozó']['email'].tolist()
        
        with st.form("new_project"):
            p_name = st.text_input("Projekt neve")
            p_hours = st.number_input("Tervezett óraszám", min_value=1)
            p_worker = st.selectbox("Hozzárendelt dolgozó", worker_list)
            if st.form_submit_button("Mentés a Google Táblázatba"):
                projects_df = get_data("projects")
                new_id = projects_df['id'].max() + 1 if not projects_df.empty else 1
                new_data = pd.DataFrame([{"id": new_id, "name": p_name, "target_hours": p_hours, "assigned_to": p_worker}])
                updated_df = pd.concat([projects_df, new_data], ignore_index=True)
                conn.update(worksheet="projects", data=updated_df)
                st.success("Projekt mentve!")

    with tab3:
        st.subheader("Összesített kimutatás")
        logs_df = get_data("logs")
        projs_df = get_data("projects")
        if not logs_df.empty:
            merged = logs_df.merge(projs_df, left_on="project_id", right_on="id")
            stats = merged.groupby("name")["hours"].sum()
            st.bar_chart(stats)
            st.dataframe(merged)

# --- DOLGOZÓI FUNKCIÓK ---
else:
    st.header("📅 Heti munkaidőm")
    
    # Adatok betöltése
    projects_df = get_data("projects")
    my_projs = projects_df[projects_df['assigned_to'] == st.session_state.user_email]
    
    # Napi rács (Grid)
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    days_list = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek"]
    
    col_days = st.columns(5)
    for i, c in enumerate(col_days):
        day_date = (start_of_week + timedelta(days=i)).strftime("%Y-%m-%d")
        c.metric(days_list[i], day_date)

    st.divider()
    
    with st.form("log_work"):
        p_select = st.selectbox("Projekt", my_projs['name'].tolist())
        d_select = st.selectbox("Melyik napon dolgoztál?", days_list)
        h_input = st.slider("Óraszám", 0.5, 8.0, 1.0, step=0.5)
        
        if st.form_submit_button("Munkaidő beküldése"):
            target_date = (start_of_week + timedelta(days=days_list.index(d_select))).strftime("%Y-%m-%d")
            p_id = my_projs[my_projs['name'] == p_select]['id'].values[0]
            
            logs_df = get_data("logs")
            new_log = pd.DataFrame([{"email": st.session_state.user_email, "project_id": p_id, "date": target_date, "hours": h_input}])
            updated_logs = pd.concat([logs_df, new_log], ignore_index=True)
            conn.update(worksheet="logs", data=updated_logs)
            st.balloons()
            st.success("Adatok szinkronizálva a Google Táblázattal!")

