# -*- coding: utf-8 -*-
import streamlit as st
from yahooquery import Ticker
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
import asyncio
from telegram import Bot
import pandas as pd
import plotly.graph_objects as go
from zoneinfo import ZoneInfo
import re
import uuid
import streamlit.components.v1 as components
import json
import os
from streamlit_autorefresh import st_autorefresh
import time

# -----------------------------
# CONFIGURAÇÕES
# -----------------------------
st.set_page_config(page_title="📈 CLUBE - COMPRA E VENDA", layout="wide")

TZ = ZoneInfo("Europe/Lisbon")
HORARIO_INICIO_PREGAO = datetime.time(14, 0, 0)
HORARIO_FIM_PREGAO    = datetime.time(21, 0, 0)

INTERVALO_VERIFICACAO = 300
TEMPO_ACUMULADO_MAXIMO = 1500
LOG_MAX_LINHAS = 1000
PERSIST_DEBOUNCE_SECONDS = 60

PALETTE = [
    "#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
    "#06b6d4", "#84cc16", "#f97316", "#ec4899", "#22c55e"
]

# =============================
# PERSISTÊNCIA (SUPABASE via REST API + LOCAL JSON)
# =============================
SUPABASE_URL = st.secrets["supabase_url_clube"]
SUPABASE_KEY = st.secrets["supabase_key_clube"]
TABLE = "kv_state_clube"
STATE_KEY = "clube_przo_v1"
LOCAL_STATE_FILE = "session_data/state_clube.json"


def agora_lx():
    return datetime.datetime.now(TZ)

def _estado_snapshot():
    snapshot = {
        "ativos": st.session_state.get("ativos", []),
        "historico_alertas": st.session_state.get("historico_alertas", []),
        "log_monitoramento": st.session_state.get("log_monitoramento", []),
        "tempo_acumulado": st.session_state.get("tempo_acumulado", {}),
        "em_contagem": st.session_state.get("em_contagem", {}),
        "status": st.session_state.get("status", {}),
        "ultimo_update_tempo": st.session_state.get("ultimo_update_tempo", {}),
        "pausado": st.session_state.get("pausado", False),
        "ultimo_estado_pausa": st.session_state.get("ultimo_estado_pausa", None),
        "ultimo_ping_keepalive": st.session_state.get("ultimo_ping_keepalive", None),
        "ultima_data_abertura_enviada": st.session_state.get("ultima_data_abertura_enviada", None),
    }

    precos_historicos_serial = {}
    for ticker, dados in st.session_state.get("precos_historicos", {}).items():
        precos_historicos_serial[ticker] = [
            (dt.isoformat() if isinstance(dt, datetime.datetime) else dt, preco)
            for dt, preco in dados
        ]
    snapshot["precos_historicos"] = precos_historicos_serial

    disparos_serial = {}
    for ticker, pontos in st.session_state.get("disparos", {}).items():
        disparos_serial[ticker] = [
            (dt.isoformat() if isinstance(dt, datetime.datetime) else dt, preco)
            for dt, preco in pontos
        ]
    snapshot["disparos"] = disparos_serial
    return snapshot

def _persist_now():
    snapshot = _estado_snapshot()
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    payload = {"k": STATE_KEY, "v": snapshot}
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        if r.status_code not in (200, 201, 204):
            st.sidebar.error(f"Erro ao salvar estado remoto: {r.text}")
    except Exception as e:
        st.sidebar.error(f"Erro ao salvar estado remoto: {e}")

    try:
        os.makedirs("session_data", exist_ok=True)
        with open(LOCAL_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.sidebar.warning(f"⚠️ Erro ao salvar local: {e}")

    st.session_state["__last_save_ts"] = agora_lx().timestamp()

def salvar_estado_duravel(force: bool = False):
    if force:
        _persist_now()
        return
    last = st.session_state.get("__last_save_ts")
    now_ts = agora_lx().timestamp()
    if not last or (now_ts - last) >= PERSIST_DEBOUNCE_SECONDS:
        _persist_now()

def carregar_estado_duravel():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?k=eq.{STATE_KEY}&select=v"
    remoto_ok = False
    origem = "❌ Nenhum"

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and r.json():
            estado = r.json()[0]["v"]
            for k, v in estado.items():
                if k == "precos_historicos":
                    precos_reconv = {}
                    for t, dados in v.items():
                        reconv = [(datetime.datetime.fromisoformat(dt) if isinstance(dt, str) else dt, p) for dt, p in dados]
                        precos_reconv[t] = reconv
                    st.session_state[k] = precos_reconv
                elif k == "disparos":
                    disparos_reconv = {}
                    for t, pontos in v.items():
                        reconv = [(datetime.datetime.fromisoformat(pt) if isinstance(pt, str) else pt, p) for pt, p in pontos]
                        disparos_reconv[t] = reconv
                    st.session_state[k] = disparos_reconv
                else:
                    st.session_state[k] = v
            st.sidebar.info("Conectado na nuvem! ✅")
            remoto_ok = True
            origem = "☁️ Supabase"
        else:
            st.sidebar.info("ℹ️ Nenhum estado remoto ainda.")
    except Exception as e:
        st.sidebar.error(f"Erro ao carregar estado remoto: {e}")

    if not remoto_ok and os.path.exists(LOCAL_STATE_FILE):
        try:
            with open(LOCAL_STATE_FILE, "r", encoding="utf-8") as f:
                estado = json.load(f)
            for k, v in estado.items():
                if k == "precos_historicos":
                    precos_reconv = {}
                    for t, dados in v.items():
                        reconv = [(datetime.datetime.fromisoformat(dt) if isinstance(dt, str) else dt, p) for dt, p in dados]
                        precos_reconv[t] = reconv
                    st.session_state[k] = precos_reconv
                elif k == "disparos":
                    disparos_reconv = {}
                    for t, pontos in v.items():
                        reconv = [(datetime.datetime.fromisoformat(pt) if isinstance(pt, str) else pt, p) for pt, p in pontos]
                        disparos_reconv[t] = reconv
                    st.session_state[k] = disparos_reconv
                else:
                    st.session_state[k] = v
            st.sidebar.info("💾 Estado carregado do local (fallback)!")
            origem = "📁 Local"
        except Exception as e:
            st.sidebar.error(f"Erro no fallback local: {e}")

    for t in st.session_state.get("tempo_acumulado", {}):
        if st.session_state.tempo_acumulado.get(t, 0) > 0 and not st.session_state.ultimo_update_tempo.get(t):
            st.session_state.ultimo_update_tempo[t] = agora_lx().isoformat()

    st.session_state["origem_estado"] = origem
    st.session_state["__carregado_ok__"] = (origem in ("☁️ Supabase", "📁 Local"))

def apagar_estado_remoto():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?k=eq.{STATE_KEY}"
    try:
        requests.delete(url, headers=headers, timeout=15)
    except Exception as e:
        st.sidebar.error(f"Erro ao apagar estado remoto: {e}")

def ensure_color_map():
    if "ticker_colors" not in st.session_state:
        st.session_state.ticker_colors = {}

def inicializar_estado():
    defaults = {
        "ativos": [], "historico_alertas": [], "log_monitoramento": [],
        "tempo_acumulado": {}, "em_contagem": {}, "status": {},
        "precos_historicos": {}, "ultimo_update_tempo": {},
        "pausado": False, "ultimo_estado_pausa": None,
        "disparos": {}, "__last_save_ts": None,
        "__carregado_ok__": False, "ultima_data_abertura_enviada": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    ensure_color_map()

inicializar_estado()
carregar_estado_duravel()

# (demais funções, monitoramento e interface — permanecem iguais ao seu script original)
# ... (o conteúdo completo do seu arquivo original continua daqui)

