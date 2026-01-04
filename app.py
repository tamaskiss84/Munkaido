# -*- coding: utf-8 -*-
import streamlit as st
...
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

# --- ADATBÁZIS KEZELÉS ---
def init_db():
    conn = sqlite3.connect('munkido.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (email TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, 
                  target_hours REAL, assigned_to TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, 
                  project_id INTEGER, date TEXT, hours REAL)''')
    # Alapértelmezett admin (ha még nincs)
    c.execute("INSERT OR IGNORE INTO users VALUES ('admin@ceg.hu', 'admin123', 'Vezető')")
    conn.commit()
    conn.close()

init_db()

# --- SEGÉDFÜGGVÉNYEK ---
def get_db_connection():
    return sqlite3.connect('munkido.db')

# --- BEJELENTKEZÉS ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("📱 Munkaidő Nyilvántartó")
    email = st.text_input("E-mail")
    password = st.text_input("Jelszó", type="password")
    
    if st.button("Belépés"):
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password)).fetchone()
        conn.close()
        if user:
            st.session_state.logged_in = True
            st.session_state.user_email = user[0]
            st.session_state.user_role = user[2]
            st.rerun()
        else:
            st.error("Hibás adatok!")
    st.stop()

# --- DASHBOARD LOGIKA ---
st.sidebar.title(f"Üdv, {st.session_state.user_email}!")
st.sidebar.write(f"Szerepkör: {st.session_state.user_role}")

if st.sidebar.button("Kijelentkezés"):
    st.session_state.logged_in = False
    st.rerun()

# --- 1. VEZETŐI DASHBOARD ---
if st.session_state.user_role == "Vezető":
    tab1, tab2, tab3 = st.tabs(["Projektek kezelése", "Dolgozók", "Statisztika"])

    with tab1:
        st.subheader("Új projekt létrehozása")
        conn = get_db_connection()
        workers = [row[0] for row in conn.execute("SELECT email FROM users").fetchall()]
        
        p_name = st.text_input("Projekt neve")
        p_hours = st.number_input("Tervezett óraszám", min_value=1)
        p_worker = st.selectbox("Felelős dolgozó", workers)
        
        if st.button("Projekt mentése"):
            conn.execute("INSERT INTO projects (name, target_hours, assigned_to) VALUES (?,?,?)", 
                         (p_name, p_hours, p_worker))
            conn.commit()
            st.success("Projekt hozzáadva!")
        
        st.divider()
        st.subheader("Aktív projektek állása")
        df_p = pd.read_sql_query("""
            SELECT p.id, p.name, p.target_hours, p.assigned_to, SUM(l.hours) as actual_hours 
            FROM projects p LEFT JOIN logs l ON p.id = l.project_id 
            GROUP BY p.id""", conn)
        st.dataframe(df_p, use_container_width=True)
        conn.close()

    with tab2:
        st.subheader("Új dolgozó hozzáadása")
        new_email = st.text_input("Új dolgozó e-mail címe")
        if st.button("Hozzáadás"):
            conn = get_db_connection()
            conn.execute("INSERT OR IGNORE INTO users (email, password, role) VALUES (?,?,?)", 
                         (new_email, "1234", "Dolgozó"))
            conn.commit()
            conn.close()
            st.info("Hozzáadva! Ideiglenes jelszó: 1234")

    # --- VEZETŐI STATISZTIKA (tab3 kiegészítése) ---
    with tab3:
        st.subheader("📊 Projektek és Időszakok Elemzése")
        
        conn = get_db_connection()
        # Minden adat lekérése a riportokhoz
        df_all = pd.read_sql_query("""
            SELECT l.date, l.hours, p.name as project_name, p.target_hours, l.email as worker
            FROM logs l
            JOIN projects p ON l.project_id = p.id
        """, conn)
        conn.close()

        if not df_all.empty:
            # Dátum konvertálása és időszakok képzése
            df_all['date'] = pd.to_datetime(df_all['date'])
            df_all['Év'] = df_all['date'].dt.year
            df_all['Negyedév'] = df_all['date'].dt.to_period('Q').astype(str)
            df_all['Hónap'] = df_all['date'].dt.to_period('M').astype(str)

            # 1. Projekt alapú összehasonlítás (Tervezett vs Tényleges)
            st.write("### Projekt Teljesítés (Tervezett vs. Tényleges órák)")
            proj_stats = df_all.groupby('project_name').agg({
                'hours': 'sum',
                'target_hours': 'first'
            }).reset_index()
            
            # Grafikon: Bar chart a különbségről
            st.bar_chart(proj_stats.set_index('project_name')[['hours', 'target_hours']])

            # 2. Időszaki szűrés (Negyedéves / Éves)
            col1, col2 = st.columns(2)
            with col1:
                period = st.selectbox("Összesítés időszaka", ["Negyedéves", "Éves"])
            
            group_col = 'Negyedév' if period == "Negyedéves" else 'Év'
            
            period_stats = df_all.groupby([group_col, 'project_name'])['hours'].sum().unstack().fillna(0)
            
            st.write(f"### {period} munkaóra összesítő projektenként")
            st.line_chart(period_stats)

            # 3. Dolgozói statisztika
            st.write("### Dolgozónkénti terhelés")
            worker_stats = df_all.groupby('worker')['hours'].sum().reset_index()
            st.dataframe(worker_stats.rename(columns={'worker': 'Dolgozó', 'hours': 'Összes ledolgozott óra'}), use_container_width=True)
            
            # Exportálási lehetőség
            csv = df_all.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="Riport letöltése CSV-ben",
                data=csv,
                file_name=f'munkido_riport_{datetime.now().strftime("%Y%m%d")}.csv',
                mime='text/csv',
            )
        else:
            st.info("Még nincsenek adatok a statisztikákhoz.")

# --- 2. DOLGOZÓI DASHBOARD (Vizuális Naptár) ---
else:
    st.header("📅 Heti munkarendem")
    
    conn = get_db_connection()
    # Csak a dolgozóhoz rendelt projektek lekérése
    my_projects_df = pd.read_sql_query(
        "SELECT id, name FROM projects WHERE assigned_to=?", 
        (st.session_state.user_email,), conn
    )
    project_list = my_projects_df['name'].tolist() if not my_projects_df.empty else ["Nincs projekt"]

    # Hét napjainak kiszámítása
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    days = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek"]
    dates = [(start_of_week + timedelta(days=i)) for i in range(5)]

    # Vizualizáció: 5 oszlop a napoknak
    cols = st.columns(5)

    for i, col in enumerate(cols):
        current_date = dates[i].strftime("%Y-%m-%d")
        with col:
            st.markdown(f"**{days[i]}**")
            st.caption(current_date)
            
            # Meglévő órák lekérése erre a napra
            daily_logs = conn.execute(
                "SELECT SUM(hours) FROM logs WHERE email=? AND date=?", 
                (st.session_state.user_email, current_date)
            ).fetchone()[0] or 0
            
            # Színkódolt visszajelzés
            if daily_logs >= 8:
                st.success(f"{daily_logs} óra")
            elif daily_logs > 0:
                st.warning(f"{daily_logs} óra")
            else:
                st.error("0 óra")

    st.divider()

    # Adatbevitel szekció
    st.subheader("Órák rögzítése")
    with st.form("entry_form"):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            selected_proj = st.selectbox("Projekt kiválasztása", project_list)
        with c2:
            selected_day = st.selectbox("Nap", days)
            target_date = dates[days.index(selected_day)].strftime("%Y-%m-%d")
        with c3:
            hours_to_add = st.number_input("Óraszám", min_value=0.5, max_value=8.0, step=0.5)
        
        if st.form_submit_button("Rögzítés a naptárba"):
            if selected_proj != "Nincs projekt":
                p_id = my_projects_df[my_projects_df['name'] == selected_proj]['id'].values[0]
                
                # Ellenőrizzük, ne lépje túl a napi 8 órát összesen
                current_total = conn.execute(
                    "SELECT SUM(hours) FROM logs WHERE email=? AND date=?", 
                    (st.session_state.user_email, target_date)
                ).fetchone()[0] or 0
                
                if current_total + hours_to_add > 8.5: # 0.5 ráhagyás a rugalmasságért
                    st.error(f"Hiba: Ezzel a bejegyzéssel túllépnéd a napi munkaidőkeretet ezen a napon ({target_date})!")
                else:
                    conn.execute(
                        "INSERT INTO logs (email, project_id, date, hours) VALUES (?,?,?,?)", 
                        (st.session_state.user_email, int(p_id), target_date, hours_to_add)
                    )
                    conn.commit()
                    st.success(f"Mentve: {selected_proj} - {hours_to_add} óra")
                    st.rerun()

    # Mai napi részletes lista
    st.subheader("Napi bontás (mai adatok)")
    today_str = today.strftime("%Y-%m-%d")
    today_details = pd.read_sql_query("""
        SELECT p.name as Projekt, l.hours as Óra 
        FROM logs l JOIN projects p ON l.project_id = p.id 
        WHERE l.email=? AND l.date=?""", conn, params=(st.session_state.user_email, today_str))
    
    if not today_details.empty:
        st.table(today_details)
    else:
        st.info("Mára még nincs rögzített munkaóra.")

    conn.close()


