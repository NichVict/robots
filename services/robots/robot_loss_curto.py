# services/robots/robot_loss_curto.py
# -*- coding: utf-8 -*-
import time
import datetime
from zoneinfo import ZoneInfo
from core.state import carregar_estado_duravel, salvar_estado_duravel, apagar_estado_duravel
from core.prices import obter_preco_atual
from core.notifications import enviar_alerta
from core.logger import log  # ✅ Logger centralizado
import builtins
import logging

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

if not estado:
    log("Falha ao carregar estado remoto — aguardando reconexão...", "⚠️")
    while not estado:
        time.sleep(60)
        estado = carregar_estado_duravel(STATE_KEY)
        if estado:
            log("Estado remoto recuperado com sucesso.", "✅")
else:
    log("Estado carregado com sucesso.", "✅")

if not isinstance(estado, dict):
    estado = {}

estado.setdefault("ativos", [])
estado.setdefault("tempo_acumulado", {})
estado.setdefault("em_contagem", {})
estado.setdefault("status", {})
estado.setdefault("historico_alertas", [])
estado.setdefault("ultima_data_abertura_enviada", None)

log(f"{len(estado['ativos'])} ativos carregados.", "📦")
log("=" * 60, "—")

# ==================================================
# 🔁 LOOP PRINCIPAL
# ==================================================
while True:
    now = agora_lx()

    # ==================================================
    # 🔄 RECARREGAR ESTADO DO SUPABASE
    # ==================================================
    try:
        remoto = carregar_estado_duravel(STATE_KEY)
        if isinstance(remoto, dict):
            estado_remoto_ativos = remoto.get("ativos", [])
            ativos_removidos = {
                t for t, s in estado.get("status", {}).items()
                if "Removido" in s or "Removendo" in s
            }

            estado["ativos"] = [
                a for a in estado_remoto_ativos
                if a.get("ticker") not in ativos_removidos
            ]

            if ativos_removidos:
                log(f"Ignorando {len(ativos_removidos)} ativo(s) removido(s): {', '.join(ativos_removidos)}", "🧹")

            estado.setdefault("tempo_acumulado", {})
            estado.setdefault("em_contagem", {})
            estado.setdefault("status", {})
            remoto.setdefault("tempo_acumulado", {})
            remoto.setdefault("em_contagem", {})
            remoto.setdefault("status", {})

            atuais = {a["ticker"] for a in estado["ativos"] if "ticker" in a}
            novo_tempo = {}
            novo_contagem = {}
            novo_status = {}

            for t in atuais:
                if t in estado["tempo_acumulado"]:
                    novo_tempo[t] = estado["tempo_acumulado"][t]
                elif t in remoto["tempo_acumulado"]:
                    novo_tempo[t] = remoto["tempo_acumulado"][t]

                if t in estado["em_contagem"]:
                    novo_contagem[t] = estado["em_contagem"][t]
                elif t in remoto["em_contagem"]:
                    novo_contagem[t] = remoto["em_contagem"][t]

                if t in estado["status"]:
                    novo_status[t] = estado["status"][t]
                elif t in remoto["status"]:
                    novo_status[t] = remoto["status"][t]

            estado["tempo_acumulado"] = novo_tempo
            estado["em_contagem"] = novo_contagem
            estado["status"] = novo_status
            log(f"Estado sincronizado com Supabase ({len(estado['ativos'])} ativos).", "🔁")
        else:
            log("Aviso: resposta do Supabase inválida ao tentar recarregar estado.", "⚠️")
    except Exception as e:
        log(f"Erro ao recarregar estado do Supabase: {e}", "⚠️")

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
            log("🧹 Limpando contagens do dia anterior (novo pregão iniciado)...", "🔁")
            estado["tempo_acumulado"].clear()
            estado["em_contagem"].clear()
            estado["status"].clear()
            salvar_estado_duravel(STATE_KEY, estado)
            log("Contagens zeradas com sucesso para o novo pregão.", "✅")

        log(f"Monitorando {len(estado['ativos'])} ativos (LOSS)...", "🟢")

        # ==================================================
        # 🔍 Verificação dos ativos (zona inversa)
        # ==================================================
        for ativo in estado["ativos"]:
            ticker = ativo["ticker"]
            preco_stop = ativo["preco"]
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

            # 💡 Condição inversa de STOP:
            condicao = (
                (operacao == "compra" and preco_atual <= preco_stop)
                or (operacao == "venda" and preco_atual >= preco_stop)
            )

            # -----------------------------
            # BLOCO DE CONTAGEM
            # -----------------------------
            if condicao:
                estado["status"][ticker] = "🟡 Em contagem (STOP)"

                if not estado["em_contagem"].get(ticker, False):
                    estado["em_contagem"][ticker] = True
                    estado["tempo_acumulado"][ticker] = 0
                    log(f"{ticker} entrou na zona de STOP ({preco_stop:.2f}). Iniciando contagem...", "⚠️")
                else:
                    estado["tempo_acumulado"][ticker] += INTERVALO_VERIFICACAO
                    log(f"{ticker}: {formatar_duracao(estado['tempo_acumulado'][ticker])} acumulados.", "⌛")

                # 🚀 Disparo do ENCERRAMENTO (STOP)
                if estado["tempo_acumulado"][ticker] >= TEMPO_ACUMULADO_MAXIMO:
                    if estado["status"].get(ticker) in ["🚀 Encerrado", "✅ Removendo...", "✅ Encerrado (removido)"]:
                        log(f"{ticker} já foi encerrado. Ignorando duplicação.", "⏸️")
                        continue

                    estado["status"][ticker] = "🚀 Encerrado"

                    msg_operacao_anterior = "COMPRA" if operacao == "venda" else "VENDA A DESCOBERTO"
                    msg_op_encerrar = operacao.upper()
                    ticker_sem_ext = ticker.replace(".SA", "")

                    msg_tg = f"""
🛑 <b>ENCERRAMENTO (STOP) ATIVADO!</b>\n
<b>Ticker:</b> {ticker_sem_ext}\n
<b>Operação anterior:</b> {msg_operacao_anterior}\n
<b>Operação para encerrar:</b> {msg_op_encerrar}\n
<b>STOP (alvo):</b> R$ {preco_stop:.2f}\n
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
                        "preco_alvo": preco_stop,
                        "preco_atual": preco_atual
                    })

                    estado["status"][ticker] = "✅ Removendo..."
                    log(f"{ticker} marcado como 'Removendo...'", "🗂️")

                    estado["ativos"] = [a for a in estado["ativos"] if a.get("ticker") != ticker]
                    estado["tempo_acumulado"].pop(ticker, None)
                    estado["em_contagem"].pop(ticker, None)
                    estado["precos_historicos"] = estado.get("precos_historicos", {})
                    estado["precos_historicos"].pop(ticker, None)

                    try:
                        apagar_estado_duravel(STATE_KEY, apenas_ticker=ticker)
                        salvar_estado_duravel(STATE_KEY, estado)
                        log(f"{ticker} removido do Supabase e estado atualizado.", "🗑️")
                    except Exception as e:
                        log(f"Erro ao limpar {ticker} no Supabase: {e}", "⚠️")

                    estado["status"][ticker] = "✅ Encerrado (removido)"
                    salvar_estado_duravel(STATE_KEY, estado)
                    log(f"{ticker} encerrado completamente e persistido.", "💾")
                    continue

            else:
                if estado["em_contagem"].get(ticker, False):
                    log(f"{ticker} saiu da zona de STOP.", "❌")
                    estado["em_contagem"][ticker] = False
                    estado["tempo_acumulado"][ticker] = 0
                    estado["status"][ticker] = "🔴 Fora do STOP"

        # --------------------------------------------------
        # 🧹 SALVAR ESTADO GERAL E ESPERAR PRÓXIMO CICLO
        # --------------------------------------------------
        salvar_estado_duravel(STATE_KEY, estado)
        log("Estado salvo.", "💾")
        time.sleep(INTERVALO_VERIFICACAO)

    # ==================================================
    # 🌙 FORA DO PREGÃO — MODO ESPERA
    # ==================================================
    else:
        segundos, abre = segundos_ate_abertura(now)
        log(f"🌙 Fora do pregão. Próxima abertura em {formatar_duracao(segundos)} (às {abre.time()}).", "⏸️")
        time.sleep(INTERVALO_VERIFICACAO)
