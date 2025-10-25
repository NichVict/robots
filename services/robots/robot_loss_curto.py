# ==================================================
# 🤖 ROBÔ LOSS CURTO — VERSÃO DURÁVEL E SEGURA (com proteção de cache)
# ==================================================
# services/robots/robot_loss_curto.py
# -*- coding: utf-8 -*-
import time
import datetime
import builtins
import logging
from zoneinfo import ZoneInfo
from core.state import carregar_estado_duravel, salvar_estado_duravel, apagar_estado_duravel
from core.prices import obter_preco_atual
from core.notifications import enviar_alerta
from core.logger import log  # ✅ Logger centralizado

# ==================================================
# 🚫 DESATIVAR LOGS DE HTTP E SUPABASE
# ==================================================
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)

# ==================================================
# 💬 LOGGING EM TEMPO REAL (Render-friendly)
# ==================================================
print = lambda *args, **kwargs: builtins.print(*args, **kwargs, flush=True)

# ==================================================
# ⚙️ CONFIGURAÇÕES
# ==================================================
TZ = ZoneInfo("Europe/Lisbon")
STATE_KEY = "loss_curto_przo_v1"
HORARIO_INICIO_PREGAO = datetime.time(3, 0, 0)
HORARIO_FIM_PREGAO = datetime.time(23, 59, 0)
INTERVALO_VERIFICACAO = 60      # 1 minuto
TEMPO_ACUMULADO_MAXIMO = 120    # 2 minutos (para testes)

# ==================================================
# 🕒 FUNÇÕES DE TEMPO
# ==================================================
def agora_lx():
    return datetime.datetime.now(TZ)

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

def formatar_duracao(segundos):
    return str(datetime.timedelta(seconds=int(segundos)))

# ==================================================
# 🚀 INICIALIZAÇÃO
# ==================================================
log("Robô LOSS CURTO iniciado.", "🤖")
estado = carregar_estado_duravel(STATE_KEY)

print("🧩 DEBUG — Estado inicial carregado:", estado)

# ==================================================
# 🧹 Proteção contra cache corrompido (mas sem apagar dados válidos)
# ==================================================
if not estado or not isinstance(estado, dict):
    print("⚠️ Estado inválido ou corrompido. Criando novo estado base.")
    estado = {}

# ✅ Garante estrutura mínima sem sobrescrever dados válidos
estado.setdefault("ativos", [])
estado.setdefault("status", {})
estado.setdefault("tempo_acumulado", {})
estado.setdefault("em_contagem", {})
estado.setdefault("historico_alertas", [])
estado.setdefault("ultima_data_abertura_enviada", None)
estado.setdefault("eventos_enviados", {})
estado.setdefault("log_monitoramento", [])
estado.setdefault("precos_historicos", {})
estado.setdefault("pausado", False)
estado.setdefault("_last_writer", "robot_loss_curto")
estado["_last_writer_ts"] = datetime.datetime.now(TZ).isoformat()

log("✅ Estado carregado e validado (dados preservados).", "🧾")

log(f"{len(estado['ativos'])} ativos carregados.", "📦")
log("=" * 60, "—")

# ==================================================
# 🔁 LOOP PRINCIPAL
# ==================================================
# 🔁 LOOP PRINCIPAL (com proteção de integridade)
# ==================================================
while True:
    now = agora_lx()

    # ==================================================
    # 🕓 DURANTE O PREGÃO
    # ==================================================
    if dentro_pregao(now):
        data_hoje = str(now.date())
        ultima = str(estado.get("ultima_data_abertura_enviada", ""))

        # 🔒 Mensagem de abertura diária
        if ultima != data_hoje:
            enviar_alerta(
                "loss_curto",
                "📣 Pregão Aberto",
                "<b>🛑 O pregão foi iniciado!</b><br><i>O robô LOSS CURTO está monitorando stops de encerramento.</i>",
                "🛑 Robô LOSS CURTO ativo — Pregão Aberto!"
            )
            estado["ultima_data_abertura_enviada"] = data_hoje
            estado["tempo_acumulado"].clear()
            estado["em_contagem"].clear()
            estado["status"].clear()
            salvar_estado_duravel(STATE_KEY, estado)
            log("🧹 Contagens zeradas — novo pregão iniciado.", "✅")

        log(f"Monitorando {len(estado['ativos'])} ativos (LOSS)...", "🟢")
        # ==================================================
        # 🔁 Proteção contra estado vazio (recarrega Supabase)
        # ==================================================
        if not estado.get("ativos"):
            time.sleep(5)
            novo_estado = carregar_estado_duravel(STATE_KEY)
            if novo_estado and novo_estado.get("ativos"):
                log("🔁 Estado recarregado com sucesso após delay — ativos encontrados.", "✅")
                estado = novo_estado
            else:
                log("🛑 ⚠️ Estado sem ativos detectado — ignorando salvamento para proteger dados.", "⚠️")
                time.sleep(INTERVALO_VERIFICACAO)
                continue

        

        tickers_para_remover = []

        for ativo in estado["ativos"]:
            ticker = ativo["ticker"]
            preco_alvo = ativo["preco"]
            operacao = ativo["operacao"]
            tk_full = f"{ticker}.SA" if not ticker.endswith(".SA") else ticker

            try:
                preco_atual = obter_preco_atual(tk_full)
                if isinstance(preco_atual, dict):
                    preco_atual = preco_atual.get("preco") or preco_atual.get("last") or preco_atual.get("price")
                if not isinstance(preco_atual, (int, float)) or preco_atual <= 0:
                    log(f"⚠️ Preço inválido para {ticker}. Pulando...", "⚠️")
                    continue
            except Exception as e:
                log(f"Erro ao obter preço de {ticker}: {e}", "⚠️")
                continue

            # 💡 Condição de STOP (zona inversa)
            condicao = (
                (operacao == "compra" and preco_atual <= preco_alvo)
                or (operacao == "venda" and preco_atual >= preco_alvo)
            )

            # -----------------------------
            # BLOCO DE CONTAGEM
            # -----------------------------
            if condicao:
                estado["status"][ticker] = "🟡 Em contagem"

                if not estado["em_contagem"].get(ticker, False):
                    estado["em_contagem"][ticker] = True
                    estado["tempo_acumulado"][ticker] = 0
                    log(f"{ticker} entrou na zona de STOP ({preco_alvo:.2f}). Iniciando contagem...", "⚠️")
                else:
                    estado["tempo_acumulado"][ticker] += INTERVALO_VERIFICACAO
                    log(f"{ticker}: {formatar_duracao(estado['tempo_acumulado'][ticker])} acumulados.", "⌛")

                # 🚀 Disparo do ENCERRAMENTO (STOP)
                if estado["tempo_acumulado"][ticker] >= TEMPO_ACUMULADO_MAXIMO:
                    event_id = f"{STATE_KEY}|{ticker}|{operacao}|{now.date()}"
                    if estado["eventos_enviados"].get(event_id):
                        log(f"{ticker}: encerramento já enviado hoje. Ignorando duplicação.", "⏸️")
                        continue

                    estado["eventos_enviados"][event_id] = True
                    estado["status"][ticker] = "🚀 Encerrado"

                    msg_operacao_anterior = "COMPRA" if operacao == "venda" else "VENDA A DESCOBERTO"
                    msg_op_encerrar = operacao.upper()
                    ticker_sem_ext = ticker.replace(".SA", "")

                    # ✉️ ALERTA COMPLETO
                    msg_tg = f"""
🛑 <b>ENCERRAMENTO (STOP) ATIVADO!</b>\n
<b>Ticker:</b> {ticker_sem_ext}\n
<b>Operação anterior:</b> {msg_operacao_anterior}\n
<b>Operação para encerrar:</b> {msg_op_encerrar}\n
<b>STOP (alvo):</b> R$ {preco_alvo:.2f}\n
<b>Preço atual:</b> R$ {preco_atual:.2f}\n
📊 <a href='https://br.tradingview.com/symbols/{ticker_sem_ext}'>Abrir gráfico no TradingView</a>\n
───────────────\n
<i><b>COMPLIANCE:</b> mensagem de encerramento baseada em nossa carteira e não constitui recomendação. Decisão exclusiva do destinatário. Conteúdo confidencial e de uso restrito. © 1milhão Invest.</i>\n
───────────────\n
🤖 Robot 1milhão Invest
""".strip()

                    enviar_alerta("loss_curto", f"🛑 ENCERRAMENTO (STOP) - {ticker}", msg_tg, msg_tg)

                    estado["historico_alertas"].append({
                        "hora": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "ticker": ticker,
                        "operacao": operacao,
                        "preco_alvo": preco_alvo,
                        "preco_atual": preco_atual
                    })

                    tickers_para_remover.append(ticker)
                    estado["em_contagem"][ticker] = False
                    estado["tempo_acumulado"][ticker] = 0

            else:
                if estado["em_contagem"].get(ticker, False):
                    log(f"{ticker} saiu da zona de STOP.", "❌")
                    estado["em_contagem"][ticker] = False
                    estado["tempo_acumulado"][ticker] = 0
                    estado["status"][ticker] = "🔴 Fora do STOP"

        # -----------------------------
        # 🧹 LIMPEZA PÓS-ENCERRAMENTO
        # -----------------------------
        if tickers_para_remover:
            estado["ativos"] = [a for a in estado["ativos"] if a["ticker"] not in tickers_para_remover]
            for t in tickers_para_remover:
                estado["tempo_acumulado"].pop(t, None)
                estado["em_contagem"].pop(t, None)
                estado["status"][t] = "✅ Encerrado (removido)"
                try:
                    apagar_estado_duravel(STATE_KEY, apenas_ticker=t)
                    log(f"{t} removido do Supabase (loss_curto).", "🗑️")
                except Exception as e:
                    log(f"Erro ao limpar {t} no Supabase: {e}", "⚠️")

        # -----------------------------
        # 💾 SALVAMENTO PROTEGIDO
        # -----------------------------
        if "ativos" in estado and isinstance(estado["ativos"], list):
            if not estado["ativos"] and not tickers_para_remover:
                log("⚠️ Estado sem ativos detectado — ignorando salvamento para proteger dados.", "🛑")
            else:
                salvar_estado_duravel(STATE_KEY, estado)
                log("Estado salvo (com proteção de integridade).", "💾")
        else:
            log("⚠️ Estrutura de estado inválida — não foi salvo.", "🧩")

        time.sleep(INTERVALO_VERIFICACAO)

    # ==================================================
    # 🌙 FORA DO PREGÃO
    # ==================================================
    else:
        faltam, prox = segundos_ate_abertura(now)
        log(f"🌙 Fora do pregão. Próxima abertura em {formatar_duracao(faltam)} (às {prox.time()}).", "⏸️")
        time.sleep(min(faltam, 3600))
