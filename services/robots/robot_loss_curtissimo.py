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
st.set_page_config(page_title="🛑 LOSS CURTÍSSIMO - ENCERRAMENTO (STOP)", layout="wide")

TZ = ZoneInfo("Europe/Lisbon")
HORARIO_INICIO_PREGAO = datetime.time(14, 0, 0)
HORARIO_FIM_PREGAO    = datetime.time(21, 0, 0)

INTERVALO_VERIFICACAO = 120       # checagem mais frequente no curtíssimo
TEMPO_ACUMULADO_MAXIMO = 900      # 15 minutos em zona de STOP
LOG_MAX_LINHAS = 800
PERSIST_DEBOUNCE_SECONDS = 45

PALETTE = [
    "#ef4444", "#3b82f6", "#f59e0b", "#10b981", "#8b5cf6",
    "#06b6d4", "#84cc16", "#f97316", "#ec4899", "#22c55e"
]

# =============================
# PERSISTÊNCIA (SUPABASE via REST API + LOCAL JSON)
# =============================
SUPABASE_URL = st.secrets["supabase_url_loss_curtissimo"]
SUPABASE_KEY = st.secrets["supabase_key_loss_curtissimo"]
TABLE = "kv_state_losscurtissimo"
STATE_KEY = "loss_curtissimo_v1"
LOCAL_STATE_FILE = "session_data/state_loss_curtissimo.json"

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
        "ultimo_ping_keepalive": st.session_state.get("ultimo_ping_keepalive", None),
        "ultima_data_abertura_enviada": st.session_state.get("ultima_data_abertura_enviada", None),
        "disparos": st.session_state.get("disparos", {}),
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
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if r.status_code not in (200, 201, 204):
            st.sidebar.error(f"Erro ao salvar estado remoto: {r.text}")
    except Exception as e:
        st.sidebar.warning(f"Erro Supabase: {e}")

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
    last = st.session_state.get("__last_save_ts") or 0
    if (agora_lx().timestamp() - last) >= PERSIST_DEBOUNCE_SECONDS:
        _persist_now()

def carregar_estado_duravel():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?k=eq.{STATE_KEY}&select=v"
    remoto_ok = False
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200 and r.json():
            estado = r.json()[0]["v"]
            for k, v in estado.items():
                st.session_state[k] = v
            st.sidebar.info("☁️ Estado carregado da nuvem!")
            remoto_ok = True
    except Exception:
        pass

    if not remoto_ok and os.path.exists(LOCAL_STATE_FILE):
        try:
            with open(LOCAL_STATE_FILE, "r", encoding="utf-8") as f:
                estado = json.load(f)
            for k, v in estado.items():
                st.session_state[k] = v
            st.sidebar.info("💾 Estado local carregado.")
        except Exception:
            pass

def inicializar_estado():
    defaults = {
        "ativos": [], "historico_alertas": [], "log_monitoramento": [],
        "tempo_acumulado": {}, "em_contagem": {}, "status": {},
        "ultimo_update_tempo": {}, "disparos": {},
        "__last_save_ts": None, "pausado": False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

inicializar_estado()
carregar_estado_duravel()

# -----------------------------
# FUNÇÕES AUXILIARES
# -----------------------------
def enviar_notificacao_stop(dest, assunto, corpo_html, remetente, senha, token_tg, chat_id, texto_tg=None):
    # E-mail (HTML)
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
            st.session_state.log_monitoramento.append("📧 E-mail STOP enviado.")
        except Exception as e:
            st.session_state.log_monitoramento.append(f"⚠️ Erro e-mail STOP: {e}")

    # Telegram
    async def send_tg():
        try:
            if token_tg and chat_id:
                bot = Bot(token=token_tg)
                await bot.send_message(
                    chat_id=chat_id,
                    text=(texto_tg or assunto),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
        except Exception as e:
            st.session_state.log_monitoramento.append(f"⚠️ Erro Telegram STOP: {e}")
    asyncio.run(send_tg())

def formatar_mensagem_stop(ticker_symbol, preco_alvo, preco_atual, operacao):
    tk = ticker_symbol.replace(".SA", "")
    # Operação anterior (a ser encerrada)
    anterior = "COMPRA" if operacao == "venda" else "VENDA A DESCOBERTO"

    texto_tg = (
        f"🛑 <b>ENCERRAMENTO (STOP) ATIVADO!</b>\n\n"
        f"<b>Ticker:</b> {tk}\n"
        f"<b>Operação anterior:</b> {anterior}\n"
        f"<b>Encerrar via:</b> {operacao.upper()}\n\n"
        f"<b>STOP:</b> R$ {preco_alvo:.2f}\n"
        f"<b>Preço atual:</b> R$ {preco_atual:.2f}\n\n"
        f"📊 <a href='https://br.tradingview.com/symbols/{tk}'>Abrir gráfico</a>\n"
        f"<em>Mensagem confidencial — 1milhão Invest.</em>"
    )

    corpo_html = f"""
    <html>
      <body style="font-family:Arial,sans-serif; background-color:#0b1220; color:#e5e7eb; padding:20px;">
        <h2 style="color:#ef4444;">🛑 ENCERRAMENTO (STOP) — CURTÍSSIMO</h2>
        <p><b>Ticker:</b> {tk}</p>
        <p><b>Operação anterior:</b> {anterior}</p>
        <p><b>Encerrar via:</b> {operacao.upper()}</p>
        <p><b>STOP:</b> R$ {preco_alvo:.2f}</p>
        <p><b>Preço atual:</b> R$ {preco_atual:.2f}</p>
        <p>📊 <a href="https://br.tradingview.com/symbols/{tk}" style="color:#60a5fa;">Ver gráfico</a></p>
        <hr style="border:1px solid #ef4444; margin:20px 0;">
        <p style="font-size:11px; color:#9ca3af;">
          Alerta de ENCERRAMENTO (STOP) — Carteira Curtíssimo Prazo. Uso exclusivo e confidencial.
        </p>
      </body>
    </html>
    """.strip()
    return texto_tg, corpo_html

# YahooQuery com retry
@st.cache_data(ttl=5)
@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30),
       retry=retry_if_exception_type(requests.exceptions.HTTPError))
def obter_preco_atual(ticker_symbol):
    tk = Ticker(ticker_symbol)
    try:
        p = tk.price.get(ticker_symbol, {}).get("regularMarketPrice")
        if p is not None:
            return float(p)
    except Exception:
        pass
    try:
        preco_atual = tk.history(period="1d")["close"].iloc[-1]
        return float(preco_atual)
    except Exception:
        return "-"

# -----------------------------
# REGRAS DE PREGÃO
# -----------------------------
def dentro_pregao(dt):
    t = dt.time()
    return HORARIO_INICIO_PREGAO <= t <= HORARIO_FIM_PREGAO

def segundos_ate_abertura(dt):
    abre = dt.replace(hour=HORARIO_INICIO_PREGAO.hour, minute=0, second=0, microsecond=0)
    fecha = dt.replace(hour=HORARIO_FIM_PREGAO.hour, minute=0, second=0, microsecond=0)
    if dt < abre:
        return int((abre - dt).total_seconds()), abre
    elif dt > fecha:
        prox = abre + datetime.timedelta(days=1)
        return int((prox - dt).total_seconds()), prox
    else:
        return 0, abre

def notificar_abertura_pregao_uma_vez_por_dia():
    now = agora_lx()
    data_atual = now.date()
    ultima = st.session_state.get("ultima_data_abertura_enviada")
    if ultima == str(data_atual):
        return
    try:
        tok = st.secrets.get("telegram_token", "").strip()
        chat = st.secrets.get("telegram_chat_id_losscurtissimo", "").strip()
        if tok and chat:
            bot = Bot(token=tok)
            asyncio.run(bot.send_message(chat_id=chat, text="🛑 LOSS CURTÍSSIMO ativo — Pregão Aberto!"))
            st.session_state.log_monitoramento.append(f"{now.strftime('%H:%M:%S')} | 📣 Pregão Aberto (LOSS CURTÍSSIMO)")
        else:
            st.session_state.log_monitoramento.append(f"{now.strftime('%H:%M:%S')} | ⚠️ Telegram não configurado.")
    except Exception as e:
        st.session_state.log_monitoramento.append(f"{now.strftime('%H:%M:%S')} | ⚠️ Erro Telegram: {e}")
    st.session_state["ultima_data_abertura_enviada"] = str(data_atual)
    salvar_estado_duravel(force=True)

# -----------------------------
# INTERFACE E SIDEBAR
# -----------------------------
st.sidebar.header("⚙️ Configurações")
st.sidebar.checkbox("⏸️ Pausar monitoramento", key="pausado")

if st.sidebar.button("🧹 Limpar Tabela/Estado"):
    st.session_state.clear()
    inicializar_estado()
    salvar_estado_duravel(force=True)
    st.sidebar.success("✅ Estado reiniciado.")

st.sidebar.header("📜 Histórico de Encerramentos")
if st.session_state.historico_alertas:
    for alerta in reversed(st.session_state.historico_alertas):
        st.sidebar.write(f"**{alerta['ticker']}** — {alerta['hora']}")
        st.sidebar.caption(f"STOP: {alerta['preco_alvo']:.2f} | Atual: {alerta['preco_atual']:.2f}")
else:
    st.sidebar.info("Nenhum encerramento ainda.")

# -----------------------------
# PRINCIPAL
# -----------------------------
st.title("🛑 LOSS CURTÍSSIMO — ENCERRAMENTO (STOP)")
st.caption("Encerra posições da carteira de curtíssimo prazo quando o preço permanece na zona de STOP por 15 minutos.")

col1, col2 = st.columns(2)
with col1:
    ticker = st.text_input("Ticker (ex: PETR4)").upper()
with col2:
    preco = st.number_input("STOP (preço alvo)", min_value=0.01, step=0.01)

if st.button("➕ Adicionar STOP"):
    if ticker:
        ativo = {"ticker": ticker, "operacao": "venda/compra no STOP", "preco": preco}
        st.session_state.ativos.append(ativo)
        st.session_state.tempo_acumulado[ticker] = 0
        st.session_state.em_contagem[ticker] = False
        st.session_state.status[ticker] = "🟢 Monitorando"
        st.success(f"STOP de {ticker} adicionado.")
        salvar_estado_duravel(force=True)

# -----------------------------
# LOOP DE MONITORAMENTO (LOSS CURTÍSSIMO)
# -----------------------------
now = agora_lx()

st.subheader("📊 Status dos STOPs")
if st.session_state.ativos:
    data_rows = []
    for ativo in list(st.session_state.ativos):
        t = ativo["ticker"]
        preco_alvo = ativo["preco"]
        tk_full = f"{t}.SA"

        # preço atual
        try:
            p = obter_preco_atual(tk_full)
        except Exception:
            p = "-"
        preco_atual = p if p != "-" else "-"

        # status visual
        data_rows.append({
            "Ticker": t,
            "STOP (alvo)": f"R$ {preco_alvo:.2f}",
            "Preço Atual": f"R$ {preco_atual:.2f}" if preco_atual != "-" else "-",
            "Status": st.session_state.status.get(t, "🟢 Monitorando")
        })

    st.dataframe(pd.DataFrame(data_rows), use_container_width=True)

# ciclo
sleep_segundos = 60
if st.session_state.pausado:
    st.info("⏸️ Monitoramento pausado.")
else:
    if dentro_pregao(now):
        notificar_abertura_pregao_uma_vez_por_dia()

        tickers_para_remover = []
        for ativo in list(st.session_state.ativos):
            t = ativo["ticker"]
            preco_alvo = ativo["preco"]
            tk_full = f"{t}.SA"

            try:
                preco_atual = obter_preco_atual(tk_full)
            except Exception as e:
                st.session_state.log_monitoramento.append(f"{now.strftime('%H:%M:%S')} | Erro {t}: {e}")
                continue

            if preco_atual == "-" or preco_atual is None:
                continue

            # Regras de STOP (igual às versões LOSS):
            # Considera STOP ativo quando preço_atual <= alvo (encerrar compra) ou >= alvo (encerrar venda a descoberto).
            condicao = (preco_atual <= preco_alvo) or (preco_atual >= preco_alvo)

            if condicao:
                st.session_state.status[t] = "🟡 Em contagem"
                if not st.session_state.em_contagem.get(t, False):
                    st.session_state.em_contagem[t] = True
                    st.session_state.ultimo_update_tempo[t] = now.isoformat()
                    st.session_state.tempo_acumulado[t] = 0
                    st.session_state.log_monitoramento.append(
                        f"{now.strftime('%H:%M:%S')} | ⚠️ {t} entrou no STOP ({preco_alvo:.2f})."
                    )
                    salvar_estado_duravel(force=True)
                else:
                    # acumula tempo real
                    ultimo = st.session_state.ultimo_update_tempo.get(t)
                    try:
                        dt_ultimo = datetime.datetime.fromisoformat(ultimo) if isinstance(ultimo, str) else ultimo
                        if dt_ultimo.tzinfo is None:
                            dt_ultimo = dt_ultimo.replace(tzinfo=TZ)
                    except Exception:
                        dt_ultimo = now
                    delta = max((now - dt_ultimo).total_seconds(), 0)
                    st.session_state.tempo_acumulado[t] = float(st.session_state.tempo_acumulado.get(t, 0)) + float(delta)
                    st.session_state.ultimo_update_tempo[t] = now.isoformat()
                    st.session_state.log_monitoramento.append(
                        f"{now.strftime('%H:%M:%S')} | ⌛ {t}: {int(st.session_state.tempo_acumulado[t])}s (+{int(delta)}s)"
                    )
                    salvar_estado_duravel(force=True)

                # Disparo se tempo acumulado >= 15 min
                if st.session_state.tempo_acumulado[t] >= TEMPO_ACUMULADO_MAXIMO and st.session_state.status.get(t) != "🚀 Encerrado":
                    st.session_state.status[t] = "🚀 Encerrado"

                    texto_tg, corpo_html = formatar_mensagem_stop(tk_full, preco_alvo, preco_atual, operacao="venda" if preco_atual <= preco_alvo else "compra")
                    enviar_notificacao_stop(
                        dest=st.secrets["email_recipient_losscurtissimo"],
                        assunto=f"🛑 STOP — CURTÍSSIMO: {t}",
                        corpo_html=corpo_html,
                        remetente=st.secrets["email_sender"],
                        senha=st.secrets["gmail_app_password"],
                        token_tg=st.secrets["telegram_token"],
                        chat_id=st.secrets["telegram_chat_id_losscurtissimo"],
                        texto_tg=texto_tg
                    )

                    st.session_state.historico_alertas.append({
                        "hora": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "ticker": t,
                        "preco_alvo": preco_alvo,
                        "preco_atual": preco_atual
                    })
                    st.session_state.disparos.setdefault(t, []).append((now.isoformat(), float(preco_atual)))
                    tickers_para_remover.append(t)
                    salvar_estado_duravel(force=True)

            else:
                if st.session_state.em_contagem.get(t, False):
                    st.session_state.em_contagem[t] = False
                    st.session_state.tempo_acumulado[t] = 0
                    st.session_state.status[t] = "🔴 Fora do STOP"
                    st.session_state.ultimo_update_tempo[t] = None
                    st.session_state.log_monitoramento.append(f"{now.strftime('%H:%M:%S')} | ❌ {t} saiu da zona de STOP.")
                    salvar_estado_duravel(force=True)

        if tickers_para_remover:
            st.session_state.ativos = [a for a in st.session_state.ativos if a["ticker"] not in tickers_para_remover]
            for t in tickers_para_remover:
                st.session_state.tempo_acumulado.pop(t, None)
                st.session_state.em_contagem.pop(t, None)
                st.session_state.ultimo_update_tempo.pop(t, None)
            st.success(f"✅ Encerrados: {', '.join(tickers_para_remover)}")
            salvar_estado_duravel(force=True)

        sleep_segundos = INTERVALO_VERIFICACAO
    else:
        faltam, prox = segundos_ate_abertura(now)
        components.html(f"""
        <div style="background:#0b1220;border:1px solid #1f2937;
             border-radius:10px;padding:12px;margin-top:10px;
             color:white;">
            ⏸️ Pregão fechado. Reabre em 
            <b style="color:#60a5fa;">{datetime.timedelta(seconds=faltam)}</b>
            (às <span style="color:#60a5fa;">{prox.strftime('%H:%M')}</span>).
        </div>""", height=70)

        # keep-alive
        try:
            APP_URL = "https://losscurtissimo.streamlit.app"
            ultimo = st.session_state.get("ultimo_ping_keepalive")
            if isinstance(ultimo, str):
                ultimo = datetime.datetime.fromisoformat(ultimo)
            if not ultimo or (now - ultimo).total_seconds() > 900:
                requests.get(APP_URL, timeout=5)
                st.session_state["ultimo_ping_keepalive"] = now.isoformat()
                salvar_estado_duravel()
        except Exception as e:
            st.session_state.log_monitoramento.append(f"{now.strftime('%H:%M:%S')} | ⚠️ Keep-alive: {e}")
        sleep_segundos = 300

# -----------------------------
# GRÁFICO (histórico simples)
# -----------------------------
fig = go.Figure()
for t, pontos in st.session_state.get("disparos", {}).items():
    if pontos:
        xs = [datetime.datetime.fromisoformat(x[0]) if isinstance(x[0], str) else x[0] for x in pontos]
        ys = [float(x[1]) for x in pontos]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers+lines", name=f"{t} (stops)",
                                 line=dict(width=2), marker=dict(symbol="star", size=10)))
fig.update_layout(title="⭐ Registros de STOP (Curtíssimo)", template="plotly_dark")
st.plotly_chart(fig, use_container_width=True)

# -----------------------------
# AUTOREFRESH
# -----------------------------
st_autorefresh(interval=60_000, key="loss-curtissimo-refresh")

