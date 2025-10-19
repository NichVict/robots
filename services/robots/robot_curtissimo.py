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
import os
import json
import time
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# -----------------------------
# CONFIGURAÇÕES
# -----------------------------
st.set_page_config(page_title="📈 CURTÍSSIMO PRAZO - COMPRA E VENDA", layout="wide")

TZ = ZoneInfo("Europe/Lisbon")
HORARIO_INICIO_PREGAO = datetime.time(14, 0, 0)
HORARIO_FIM_PREGAO    = datetime.time(21, 0, 0)

INTERVALO_VERIFICACAO = 120  # intervalo menor, operação mais curta
TEMPO_ACUMULADO_MAXIMO = 900  # 15 minutos
LOG_MAX_LINHAS = 800
PERSIST_DEBOUNCE_SECONDS = 45

# =============================
# PERSISTÊNCIA (SUPABASE)
# =============================
SUPABASE_URL = st.secrets["supabase_url_curtissimo"]
SUPABASE_KEY = st.secrets["supabase_key_curtissimo"]
TABLE = "kv_state_curtissimo"
STATE_KEY = "curtissimo_v1"
LOCAL_STATE_FILE = "session_data/state_curtissimo.json"

# =============================
# UTILITÁRIAS
# =============================
def agora_lx():
    return datetime.datetime.now(TZ)

def _persist_now():
    snapshot = st.session_state.copy()
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    payload = {"k": STATE_KEY, "v": snapshot}
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    try:
        requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
    except Exception as e:
        st.sidebar.warning(f"Erro ao salvar Supabase: {e}")
    os.makedirs("session_data", exist_ok=True)
    with open(LOCAL_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    st.session_state["__last_save_ts"] = agora_lx().timestamp()

def salvar_estado_duravel(force=False):
    if force:
        _persist_now()
        return
    last = st.session_state.get("__last_save_ts", 0)
    if (agora_lx().timestamp() - last) > PERSIST_DEBOUNCE_SECONDS:
        _persist_now()

def carregar_estado_duravel():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?k=eq.{STATE_KEY}&select=v"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200 and r.json():
            st.session_state.update(r.json()[0]["v"])
            st.sidebar.info("☁️ Estado carregado da nuvem!")
            return
    except Exception:
        pass
    if os.path.exists(LOCAL_STATE_FILE):
        try:
            with open(LOCAL_STATE_FILE, "r", encoding="utf-8") as f:
                st.session_state.update(json.load(f))
            st.sidebar.info("💾 Estado local carregado.")
        except Exception:
            pass

def inicializar_estado():
    defaults = {
        "ativos": [], "historico_alertas": [], "log_monitoramento": [],
        "tempo_acumulado": {}, "em_contagem": {}, "status": {},
        "__last_save_ts": None, "pausado": False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

inicializar_estado()
carregar_estado_duravel()

# =============================
# FUNÇÕES DE ALERTA
# =============================
def enviar_alerta_curtissimo(ticker, preco_alvo, preco_atual, operacao):
    """Envia alerta via e-mail e Telegram."""
    remetente = st.secrets["email_sender"]
    senha = st.secrets["gmail_app_password"]
    destinatario = st.secrets["email_recipient_curtissimo"]
    token_tg = st.secrets["telegram_token"]
    chat_id = st.secrets["telegram_chat_id_curtissimo"]

    assunto = f"⚡ CURTÍSSIMO PRAZO: {operacao.upper()} em {ticker}"
    corpo_html = f"""
    <html>
      <body style="font-family:Arial,sans-serif; background-color:#0b1220; color:#e5e7eb; padding:20px;">
        <h2 style="color:#3b82f6;">⚡ ALERTA CURTÍSSIMO PRAZO</h2>
        <p><b>Ticker:</b> {ticker}</p>
        <p><b>Operação:</b> {operacao.upper()}</p>
        <p><b>Preço alvo:</b> R$ {preco_alvo:.2f}</p>
        <p><b>Preço atual:</b> R$ {preco_atual:.2f}</p>
        <p style="color:#9ca3af; font-size:12px;">Alerta automático gerado pelo robô Curtíssimo Prazo.</p>
      </body>
    </html>
    """

    # Envio de e-mail
    try:
        msg = MIMEMultipart()
        msg["From"], msg["To"], msg["Subject"] = remetente, destinatario, assunto
        msg.attach(MIMEText(corpo_html, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(remetente, senha)
            s.send_message(msg)
        st.session_state.log_monitoramento.append("📧 E-mail enviado com sucesso.")
    except Exception as e:
        st.session_state.log_monitoramento.append(f"⚠️ Erro e-mail: {e}")

    # Envio Telegram
    async def send_tg():
        try:
            bot = Bot(token=token_tg)
            await bot.send_message(chat_id=chat_id, text=f"{assunto}\nPreço alvo: {preco_alvo}\nPreço atual: {preco_atual}")
        except Exception as e:
            st.session_state.log_monitoramento.append(f"⚠️ Erro Telegram: {e}")

    asyncio.run(send_tg())

# =============================
# INTERFACE
# =============================
st.title("⚡ CURTÍSSIMO PRAZO — MONITORAMENTO RÁPIDO")
st.caption("Rastreador de ativos para operações de curtíssimo prazo (intervalos de minutos).")

st.sidebar.header("⚙️ Configurações")
st.sidebar.checkbox("⏸️ Pausar monitoramento", key="pausado")

if st.sidebar.button("🧹 Limpar estado"):
    st.session_state.clear()
    inicializar_estado()
    salvar_estado_duravel(force=True)
    st.sidebar.success("Estado limpo!")

st.sidebar.header("📜 Histórico de Alertas")
if st.session_state.historico_alertas:
    for alerta in reversed(st.session_state.historico_alertas):
        st.sidebar.write(f"**{alerta['ticker']}** — {alerta['hora']}")
        st.sidebar.caption(f"{alerta['operacao'].upper()} | Alvo: {alerta['preco_alvo']:.2f} | Atual: {alerta['preco_atual']:.2f}")
else:
    st.sidebar.info("Nenhum alerta ainda.")

# =============================
# PRINCIPAL
# =============================
st.subheader("🧩 Adicionar ativo")
col1, col2, col3 = st.columns(3)
with col1:
    ticker = st.text_input("Ticker (ex: PETR4)").upper()
with col2:
    operacao = st.selectbox("Operação", ["compra", "venda"])
with col3:
    preco = st.number_input("Preço alvo", min_value=0.01, step=0.01)

if st.button("➕ Adicionar ativo"):
    if ticker:
        st.session_state.ativos.append({"ticker": ticker, "operacao": operacao, "preco": preco})
        st.session_state.status[ticker] = "🟢 Monitorando"
        salvar_estado_duravel(force=True)
        st.success(f"Ticker {ticker} adicionado.")

# =============================
# LOOP DE MONITORAMENTO
# =============================
now = agora_lx()
if st.session_state.pausado:
    st.warning("⏸️ Monitoramento pausado.")
else:
    st.subheader("📊 Status Atual")
    data = []
    for ativo in st.session_state.ativos:
        t = ativo["ticker"]
        preco_alvo = ativo["preco"]
        operacao = ativo["operacao"]
        try:
            p = Ticker(f"{t}.SA").price.get(f"{t}.SA", {}).get("regularMarketPrice")
        except Exception:
            p = None
        preco_atual = float(p) if p else "-"
        data.append({
            "Ticker": t,
            "Operação": operacao,
            "Preço Alvo": f"R$ {preco_alvo:.2f}",
            "Preço Atual": f"R$ {preco_atual}" if preco_atual != "-" else "-",
            "Status": st.session_state.status.get(t, "🟢 Monitorando")
        })

        condicao = (
            (operacao == "compra" and preco_atual >= preco_alvo) or
            (operacao == "venda" and preco_atual <= preco_alvo)
        )

        if condicao:
            st.warning(f"⚡ {t} atingiu o alvo de {operacao.upper()}!")
            enviar_alerta_curtissimo(t, preco_alvo, preco_atual, operacao)
            st.session_state.status[t] = "🚀 Disparado"
            st.session_state.historico_alertas.append({
                "hora": now.strftime("%Y-%m-%d %H:%M:%S"),
                "ticker": t,
                "operacao": operacao,
                "preco_alvo": preco_alvo,
                "preco_atual": preco_atual
            })
            salvar_estado_duravel(force=True)
    st.dataframe(pd.DataFrame(data), use_container_width=True)

# =============================
# KEEP-ALIVE
# =============================
if not st.session_state.get("ultimo_ping_keepalive") or (
    (agora_lx() - datetime.datetime.fromisoformat(st.session_state.get("ultimo_ping_keepalive", agora_lx().isoformat()))).total_seconds() > 900
):
    try:
        requests.get("https://curtissimo.streamlit.app", timeout=5)
        st.session_state["ultimo_ping_keepalive"] = agora_lx().isoformat()
        salvar_estado_duravel()
    except Exception:
        pass

# =============================
# AUTOREFRESH
# =============================
st_autorefresh(interval=60_000, key="curtissimo-refresh")

