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
    last_m = (monday - timedelta(days=25)).strftime("%Y-%m
