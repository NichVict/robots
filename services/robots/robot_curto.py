# services/robots/robot_curto.py
# -*- coding: utf-8 -*-
import time
import datetime
from zoneinfo import ZoneInfo
from core.state import carregar_estado_duravel, salvar_estado_duravel, apagar_estado_duravel
from core.prices import obter_preco_atual
from core.notifications import enviar_alerta
from core.logger import log
import builtins

# ==================================================
# 💬 LOGGING EM TEMPO REAL (Render-friendly)
# ==================================================
print = lambda *args, **kwargs: builtins.print(*args, **kwargs, flush=True)

# ==================================================
# ⚙️ CONFIGURAÇÕES
# ==================================================
STATE_KEY = "curto_przo_v1"  # ✅ Mantém o mesmo nome usado na interface e core.config
TZ = ZoneInfo("Europe/Lisbon")
HORARIO_INICIO_PREGAO = datetime.time(3, 0, 0)
HORARIO_FIM_PREGAO = datetime.time(23, 59, 0)
INTERVALO_VERIFICACAO = 180      # 3 minutos
TEMPO_ACUMULADO_MAXIMO = 480     # 8 minutos

# Limites de segurança para evitar inchaço de logs
LOG_MAX = 800
ALERTAS_MAX = 200
PRECOS_MAX_POR_TICKER = 500

# ==================================================
# 🕒 FUNÇÕES DE TEMPO
# ==================================================
def agora_lx():
    return datetime.datetime.now(TZ)

def dentro_pregao(dt):
    t = dt.time()
    return HORARIO_INICIO_PREGAO <= t <= HORARIO_FIM_PREGAO

def formatar_duracao(segundos):
    return str(datetime.timedelta(seconds=int(segundos)))

# ==================================================
# 🧹 SANITIZAÇÃO DE ESTADO
# ==================================================
def sanitize_estado(estado):
    """
    Mantém apenas dados coerentes com os ativos atuais.
    Remove tickers antigos, limpa logs e garante consistência.
    """
    if not isinstance(estado, dict):
        return {
            "ativos": [], "tempo_acumulado": {}, "em_contagem": {}, "status": {},
            "historico_alertas": [], "precos_historicos": {}, "disparos": {},
            "log_monitoramento": []
        }

    ativos = estado.get("ativos", []) or []
    ativos_set = {a["ticker"] for a in ativos if isinstance(a, dict) and a.get("ticker")}

    # Corrige status (sem emoji)
    status = {}
    for t, s in (estado.get("status") or {}).items():
        s_low = str(s).lower()
        if "dispar" in s_low:
            status[t] = "disparado"
        elif "contagem" in s_low:
            status[t] = "em_contagem"
        elif "monitor" in s_low:
            status[t] = "monitorando"
        else:
            status[t] = "monitorando" if t in ativos_set else None
    status = {t: v for t, v in status.items() if t in ativos_set and v is not None}

    tempo = {t: float(estado.get("tempo_acumulado", {}).get(t, 0)) for t in ativos_set}
    em_cont = {t: bool(estado.get("em_contagem", {}).get(t, False)) for t in ativos_set}

    precos_hist = {}
    for t in ativos_set:
        linhas = (estado.get("precos_historicos", {}).get(t) or [])
        if linhas:
            precos_hist[t] = linhas[-PRECOS_MAX_POR_TICKER:]

    disparos = {}
    for t in ativos_set:
        pts = (estado.get("disparos", {}).get(t) or [])
        if pts:
            disparos[t] = pts[-50:]

    logs = estado.get("log_monitoramento", []) or []
    if ativos_set:
        logs_filtrados = []
        for l in logs[-LOG_MAX:]:
            if any(t in l for t in ativos_set) or "Robô" in l or "Estado salvo" in l:
                logs_filtrados.append(l)
        logs = logs_filtrados[-LOG_MAX:]
    else:
        logs = logs[-LOG_MAX:]

    hist = []
    for h in (estado.get("historico_alertas") or [])[-ALERTAS_MAX:]:
        if h.get("ticker") in ativos_set:
            hist.append(h)
    hist = hist[-ALERTAS_MAX:]

    return {
        "ativos": list(ativos),
        "tempo_acumulado": tempo,
        "em_contagem": em_cont,
        "status": status,
        "historico_alertas": hist,
        "precos_historicos": precos_hist,
        "disparos": disparos,
        "log_monitoramento": logs,
    }

# ==================================================
# 🚀 INICIALIZAÇÃO
# ==================================================
log("Robô CURTO iniciado.", "🤖")

estado = carregar_estado_duravel(STATE_KEY) or {}
estado.setdefault("ativos", [])
estado.setdefault("tempo_acumulado", {})
estado.setdefault("em_contagem", {})
estado.setdefault("status", {})
estado.setdefault("historico_alertas", [])
estado.setdefault("precos_historicos", {})
estado.setdefault("disparos", {})
estado.setdefault("log_monitoramento", [])

log(f"{len(estado['ativos'])} ativos carregados.", "📦")
log("=" * 60, "—")

# ==================================================
# 🔁 LOOP PRINCIPAL
# ==================================================
while True:
    now = agora_lx()

    try:
        remoto = carregar_estado_duravel(STATE_KEY) or {}
        ativos_remotos = remoto.get("ativos", []) or []
        estado["ativos"] = ativos_remotos
    except Exception as e:
        log(f"Erro ao recarregar estado remoto: {e}", "⚠️")

    ativos = estado["ativos"]
    if not ativos:
        time.sleep(INTERVALO_VERIFICACAO)
        continue

    if dentro_pregao(now):
        log(f"Monitorando {len(ativos)} ativos...", "🟢")

        for ativo in list(ativos):
            ticker = ativo["ticker"]
            preco_alvo = float(ativo["preco"])
            operacao = ativo["operacao"]
            tk_full = f"{ticker}.SA" if not ticker.endswith(".SA") else ticker

            try:
                preco_atual = obter_preco_atual(tk_full)
                if isinstance(preco_atual, dict):
                    preco_atual = preco_atual.get("preco") or preco_atual.get("last") or preco_atual.get("price")
                if not isinstance(preco_atual, (int, float)) or preco_atual <= 0:
                    log(f"Preço inválido para {ticker}. Pulando...", "⚠️")
                    continue
            except Exception as e:
                log(f"Erro ao obter preço de {ticker}: {e}", "⚠️")
                continue

            condicao = (
                (operacao == "compra" and preco_atual >= preco_alvo) or
                (operacao == "venda"  and preco_atual <= preco_alvo)
            )

            estado["status"].setdefault(ticker, "monitorando")

            if condicao:
                estado["status"][ticker] = "em_contagem"

                if not estado["em_contagem"].get(ticker, False):
                    estado["em_contagem"][ticker] = True
                    estado["tempo_acumulado"][ticker] = 0
                    log(f"{ticker} atingiu o alvo ({preco_alvo:.2f}). Iniciando contagem...", "⚠️")
                else:
                    estado["tempo_acumulado"][ticker] = float(estado["tempo_acumulado"].get(ticker, 0)) + INTERVALO_VERIFICACAO
                    log(f"{ticker}: {formatar_duracao(estado['tempo_acumulado'][ticker])} acumulados.", "⌛")

                if estado["tempo_acumulado"][ticker] >= TEMPO_ACUMULADO_MAXIMO:
                    estado["status"][ticker] = "disparado"

                    msg_op = "VENDA A DESCOBERTO" if operacao == "venda" else "COMPRA"
                    ticker_symbol_sem_ext = ticker.replace(".SA", "")

                    msg_tg = f"""
💥 <b>ALERTA DE {msg_op.upper()} ATIVADA!</b>\n\n
<b>Ticker:</b> {ticker_symbol_sem_ext}\n
<b>Preço alvo:</b> R$ {preco_alvo:.2f}\n
<b>Preço atual:</b> R$ {preco_atual:.2f}\n\n
📊 <a href='https://br.tradingview.com/symbols/{ticker_symbol_sem_ext}'>Abrir gráfico no TradingView</a>\n\n
COMPLIANCE: Esta mensagem é uma sugestão de compra/venda baseada em nossa CARTEIRA.\n
A compra ou venda é de total decisão e responsabilidade do Destinatário.\n
Esta informação é CONFIDENCIAL, de propriedade de 1milhao Invest e de seu DESTINATÁRIO tão somente.\n
Se você NÃO for DESTINATÁRIO ou pessoa autorizada a recebê-lo, NÃO PODE usar, copiar, transmitir, retransmitir
ou divulgar seu conteúdo (no todo ou em partes), estando sujeito às penalidades da LEI.\n
A Lista de Ações do 1milhao Invest é devidamente REGISTRADA.\n\n
🤖 Robot 1milhão Invest
""".strip()

                    msg_html = f"""
<html>
  <body style="font-family:Arial,sans-serif; background-color:#0b1220; color:#e5e7eb; padding:20px;">
    <h2 style="color:#3b82f6;">💥 ALERTA DE {msg_op.upper()} ATIVADA!</h2>
    <p><b>Ticker:</b> {ticker_symbol_sem_ext}</p>
    <p><b>Preço alvo:</b> R$ {preco_alvo:.2f}</p>
    <p><b>Preço atual:</b> R$ {preco_atual:.2f}</p>
    <p>📊 <a href="https://br.tradingview.com/symbols/{ticker_symbol_sem_ext}" style="color:#60a5fa;">Ver gráfico no TradingView</a></p>
    <hr style="border:1px solid #3b82f6; margin:20px 0;">
    <p style="font-size:11px; line-height:1.5; color:#9ca3af;">
      <b>COMPLIANCE:</b> Esta mensagem é uma sugestão de compra/venda baseada em nossa CARTEIRA.<br>
      A compra ou venda é de total decisão e responsabilidade do Destinatário.<br>
      Esta informação é <b>CONFIDENCIAL</b>, de propriedade de 1milhao Invest e de seu DESTINATÁRIO tão somente.<br>
      Se você <b>NÃO</b> for DESTINATÁRIO ou pessoa autorizada a recebê-lo, <b>NÃO PODE</b> usar, copiar, transmitir, retransmitir
      ou divulgar seu conteúdo (no todo ou em partes), estando sujeito às penalidades da LEI.<br>
      A Lista de Ações do 1milhao Invest é devidamente <b>REGISTRADA.</b>
    </p>
    <p style="margin-top:10px;">🤖 Robot 1milhão Invest</p>
  </body>
</html>
""".strip()

                    try:
                        enviar_alerta("curto", f"Alerta {msg_op.upper()} - {ticker_symbol_sem_ext}", msg_html, msg_tg)
                    except Exception as e:
                        log(f"Erro ao enviar alerta de {ticker}: {e}", "⚠️")

                    estado.setdefault("historico_alertas", [])
                    estado["historico_alertas"].append({
                        "hora": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "ticker": ticker,
                        "operacao": operacao,
                        "preco_alvo": preco_alvo,
                        "preco_atual": preco_atual
                    })

                    estado["ativos"] = [a for a in estado["ativos"] if a.get("ticker") != ticker]
                    estado["tempo_acumulado"].pop(ticker, None)
                    estado["em_contagem"].pop(ticker, None)

    # ==================================================
    # 💾 SALVAR ESTADO (SUBSTITUI COMPLETAMENTE)
    # ==================================================
    estado_sanit = sanitize_estado(estado)
    try:
        apagar_estado_duravel(STATE_KEY)
        salvar_estado_duravel(STATE_KEY, estado_sanit)
        log("Estado salvo.", "💾")
    except Exception as e:
        log(f"Erro ao salvar estado: {e}", "⚠️")

    time.sleep(INTERVALO_VERIFICACAO)
