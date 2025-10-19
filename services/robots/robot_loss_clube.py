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
from streamlit_autorefresh import st_autorefresh
import time
import streamlit.components.v1 as components

# -----------------------------
# CONFIGURAÇÕES
# -----------------------------
st.set_page_config(page_title="LOSS CLUBE - ENCERRAMENTO (STOP)", layout="wide")

TZ = ZoneInfo("Europe/Lisbon")
HORARIO_INICIO_PREGAO = datetime.time(14, 0, 0)
HORARIO_FIM_PREGAO    = datetime.time(21, 0, 0)

INTERVALO_VERIFICACAO = 300
TEMPO_ACUMULADO_MAXIMO = 1500
LOG_MAX_LINHAS = 1000
PERSIST_DEBOUNCE_SECONDS = 60

PALETTE = [
    "#ef4444", "#3b82f6", "#f59e0b", "#10b981", "#8b5cf6",
    "#06b6d4", "#84cc16", "#f97316", "#ec4899", "#22c55e"
]

# =============================
# PERSISTÊNCIA (SUPABASE via REST API + LOCAL JSON)
# =============================
SUPABASE_URL = st.secrets["supabase_url_lossclube"]
SUPABASE_KEY = st.secrets["supabase_key_lossclube"]
TABLE = "kv_state_lossclube"
STATE_KEY = "loss_clube_v1"
LOCAL_STATE_FILE = "session_data/state_loss_clube.json"


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
                st.session_state[k] = v
            st.sidebar.info("💾 Estado carregado do local (fallback)!")
            origem = "📁 Local"
        except Exception as e:
            st.sidebar.error(f"Erro no fallback local: {e}")

    st.session_state["origem_estado"] = origem

def inicializar_estado():
    defaults = {
        "ativos": [], "historico_alertas": [], "log_monitoramento": [],
        "tempo_acumulado": {}, "em_contagem": {}, "status": {},
        "__last_save_ts": None, "__carregado_ok__": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

inicializar_estado()
carregar_estado_duravel()

# -----------------------------
# FUNÇÕES DE ALERTA
# -----------------------------
def enviar_notificacao_stop(dest, assunto, corpo_html, remetente, senha, token_tg, chat_id):
    if senha and dest:
        try:
            msg = MIMEMultipart()
            msg["From"] = remetente
            msg["To"] = dest
            msg["Subject"] = assunto
            msg.attach(MIMEText(corpo_html, "html"))

            with smtplib.SMTP("smtp.gmail.com", 587) as s:
                s.starttls()
                s.login(remetente, senha)
                s.send_message(msg)
            st.session_state.log_monitoramento.append("📧 E-mail de STOP enviado com sucesso.")
        except Exception as e:
            st.session_state.log_monitoramento.append(f"⚠️ Erro e-mail STOP: {e}")

    async def send_tg():
        try:
            if token_tg and chat_id:
                bot = Bot(token=token_tg)
                await bot.send_message(chat_id=chat_id, text=f"{assunto}\n\n{corpo_html}", parse_mode="HTML")
        except Exception as e:
            st.session_state.log_monitoramento.append(f"⚠️ Erro Telegram STOP: {e}")
    asyncio.run(send_tg())

def formatar_mensagem_stop(ticker, preco_alvo, preco_atual):
    corpo_html = f"""
    <html>
      <body style="font-family:Arial,sans-serif; background-color:#0b1220; color:#f87171; padding:20px;">
        <h2>🔻 ENCERRAMENTO (STOP) ATIVADO!</h2>
        <p><b>Ticker:</b> {ticker}</p>
        <p><b>Preço STOP:</b> R$ {preco_alvo:.2f}</p>
        <p><b>Preço Atual:</b> R$ {preco_atual:.2f}</p>
        <hr style="border:1px solid #ef4444; margin:20px 0;">
        <p style="font-size:11px; line-height:1.4; color:#9ca3af;">
          Este alerta representa um ponto de ENCERRAMENTO da posição aberta.<br>
          Uso exclusivo da carteira CLUBE (1milhão Invest).<br>
          Mensagem confidencial. Proibida a divulgação ou retransmissão.
        </p>
      </body>
    </html>
    """
    return corpo_html

def notificar_stop_loss_clube(ticker, preco_alvo, preco_atual):
    remetente = st.secrets["email_sender"]
    senha = st.secrets["gmail_app_password"]
    destinatario = st.secrets["email_recipient_lossclube"]
    token_tg = st.secrets["telegram_token"]
    chat_id = st.secrets["telegram_chat_id_lossclube"]

    assunto = f"🔻 STOP (CLUBE): {ticker}"
    corpo_html = formatar_mensagem_stop(ticker, preco_alvo, preco_atual)
    enviar_notificacao_stop(destinatario, assunto, corpo_html, remetente, senha, token_tg, chat_id)
    st.session_state.historico_alertas.append({
        "hora": agora_lx().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": ticker,
        "preco_alvo": preco_alvo,
        "preco_atual": preco_atual
    })
    salvar_estado_duravel(force=True)

# -----------------------------
# INTERFACE
# -----------------------------
st.title("🔻 LOSS CLUBE — ENCERRAMENTO (STOP)")
st.caption("Monitora ativos da carteira CLUBE e envia alertas quando atingem o preço de STOP definido.")

st.sidebar.header("⚙️ Configurações")
st.sidebar.checkbox("⏸️ Pausar monitoramento", key="pausado")
salvar_estado_duravel()

if st.sidebar.button("🧹 Limpar estado"):
    st.session_state.clear()
    inicializar_estado()
    salvar_estado_duravel(force=True)
    st.sidebar.success("Estado limpo!")

st.sidebar.header("📜 Histórico de Stops")
if st.session_state.historico_alertas:
    for alerta in reversed(st.session_state.historico_alertas):
        st.sidebar.write(f"**{alerta['ticker']}** — {alerta['hora']}")
        st.sidebar.caption(f"STOP: R$ {alerta['preco_alvo']:.2f} | Atual: {alerta['preco_atual']:.2f}")
else:
    st.sidebar.info("Nenhum STOP registrado ainda.")

# -----------------------------
# PRINCIPAL
# -----------------------------
st.subheader("🧩 Monitoramento de Stops")
col1, col2 = st.columns(2)
with col1:
    ticker = st.text_input("Ticker (ex: PETR4)").upper()
with col2:
    preco = st.number_input("Preço STOP", min_value=0.01, step=0.01)

if st.button("➕ Adicionar ativo"):
    if ticker:
        st.session_state.ativos.append({"ticker": ticker, "preco": preco})
        st.session_state.status[ticker] = "🟢 Monitorando"
        salvar_estado_duravel(force=True)
        st.success(f"Ticker {ticker} adicionado para monitoramento.")

st.subheader("📊 Status Atual")
if st.session_state.ativos:
    data = []
    for ativo in st.session_state.ativos:
        t = ativo["ticker"]
        preco_alvo = ativo["preco"]
        try:
            p = Ticker(f"{t}.SA").price.get(f"{t}.SA", {}).get("regularMarketPrice")
        except Exception:
            p = None
        preco_atual = float(p) if p else "-"
        data.append({
            "Ticker": t,
            "Preço STOP": f"R$ {preco_alvo:.2f}",
            "Preço Atual": f"R$ {preco_atual}" if preco_atual != "-" else "-",
            "Status": st.session_state.status.get(t, "🟢 Monitorando")
        })

        if preco_atual != "-" and preco_atual <= preco_alvo:
            st.warning(f"🔻 {t} atingiu o preço STOP! Encerrando operação.")
            notificar_stop_loss_clube(t, preco_alvo, preco_atual)
            st.session_state.status[t] = "🔴 STOP Ativado"
            salvar_estado_duravel(force=True)
    st.dataframe(pd.DataFrame(data), use_container_width=True)
else:
    st.info("Nenhum ativo em monitoramento.")

# -----------------------------
# KEEP-ALIVE
# -----------------------------
now = agora_lx()
if not st.session_state.get("ultimo_ping_keepalive") or (
    (now - datetime.datetime.fromisoformat(st.session_state.get("ultimo_ping_keepalive", now.isoformat()))).total_seconds() > 900
):
    try:
        requests.get("https://lossclube.streamlit.app", timeout=5)
        st.session_state["ultimo_ping_keepalive"] = now.isoformat()
        salvar_estado_duravel()
    except Exception:
        pass

# -----------------------------
# AUTOREFRESH
# -----------------------------
st_autorefresh(interval=60_000, key="lossclube-refresh")

