# services/robots/robot_curto.py
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
# Substitui o print padrão por versão com flush imediato
print = lambda *args, **kwargs: builtins.print(*args, **kwargs, flush=True)

# ==================================================
# ⚙️ CONFIGURAÇÕES
# ==================================================
TZ = ZoneInfo("Europe/Lisbon")
STATE_KEY = "curto_przo_v1"
HORARIO_INICIO_PREGAO = datetime.time(3, 0, 0)
HORARIO_FIM_PREGAO = datetime.time(23, 29, 0)
INTERVALO_VERIFICACAO = 300     # 3 minutos
TEMPO_ACUMULADO_MAXIMO = 1500   # 8 minutos

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
log("Robô CURTO iniciado.", "🤖")
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
    # 🕓 FLUXO NORMAL — DURANTE O PREGÃO
    # ==================================================
    if dentro_pregao(now):
        data_hoje = str(now.date())
        ultima = str(estado.get("ultima_data_abertura_enviada", ""))

        # 🔒 Mensagem de abertura diária
        if ultima != data_hoje:
            enviar_alerta(
                "curto",
                "📣 Pregão Aberto",
                "<b>O pregão foi iniciado! 🟢</b><br><i>O robô de curto prazo está monitorando os ativos.</i>",
                "🤖 Robô CURTO iniciando monitoramento — Pregão Aberto!"
            )
            estado["ultima_data_abertura_enviada"] = data_hoje
            log("🧹 Limpando contagens do dia anterior (novo pregão iniciado)...", "🔁")
            estado["tempo_acumulado"].clear()
            estado["em_contagem"].clear()
            estado["status"].clear()
            salvar_estado_duravel(STATE_KEY, estado)
            log("Contagens zeradas com sucesso para o novo pregão.", "✅")

        log(f"Monitorando {len(estado['ativos'])} ativos...", "🟢")

        # ==================================================
        # 📊 Exibe os tickers e preços atuais
        # ==================================================
        if estado["ativos"]:
            detalhes = []
            for ativo in estado["ativos"]:
                ticker = ativo["ticker"]
                tk_full = f"{ticker}.SA" if not ticker.endswith(".SA") else ticker
                try:
                    preco_atual = obter_preco_atual(tk_full)
                    if isinstance(preco_atual, dict):
                        preco_atual = preco_atual.get("preco") or preco_atual.get("last") or preco_atual.get("price")
                    if isinstance(preco_atual, (int, float)):
                        detalhes.append(f"• {ticker} — preço atual: R$ {preco_atual:.2f}")
                except Exception as e:
                    detalhes.append(f"• {ticker} — erro ao obter preço ({e})")
            if detalhes:
                log("     \n".join(detalhes), "💬")

        # ==================================================
        # 🔍 Verificação dos ativos
        # ==================================================

        for ativo in estado["ativos"]:
            ticker = ativo["ticker"]
            preco_alvo = ativo["preco"]
            operacao = ativo["operacao"]
            tk_full = f"{ticker}.SA" if not ticker.endswith(".SA") else ticker

            try:
                preco_atual = obter_preco_atual(tk_full)
                if isinstance(preco_atual, dict):
                    preco_atual = preco_atual.get("preco") or preco_atual.get("last") or preco_atual.get("price")
                if not isinstance(preco_atual, (int, float)):
                    log(f"Retorno inesperado ao obter preço de {ticker}: {type(preco_atual).__name__}. Pulando...", "⚠️")
                    continue
            except Exception as e:
                log(f"Erro ao obter preço de {ticker}: {e}", "⚠️")
                continue

            if preco_atual <= 0:
                log(f"Preço inválido para {ticker}. Pulando...", "⚠️")
                continue

            condicao = (
                (operacao == "compra" and preco_atual >= preco_alvo)
                or (operacao == "venda" and preco_atual <= preco_alvo)
            )

            # -----------------------------
            # BLOCO DE CONTAGEM
            # -----------------------------
            if condicao:
                estado["status"][ticker] = "🟡 Em contagem"

                if not estado["em_contagem"].get(ticker, False):
                    estado["em_contagem"][ticker] = True
                    estado["tempo_acumulado"][ticker] = 0
                    log(f"{ticker} atingiu o alvo ({preco_alvo:.2f}). Iniciando contagem...", "⚠️")
                else:
                    estado["tempo_acumulado"][ticker] += INTERVALO_VERIFICACAO
                    log(f"{ticker}: {formatar_duracao(estado['tempo_acumulado'][ticker])} acumulados.", "⌛")

                # ==================================================
                # 🚀 Disparo do alerta — com bloqueio anti-duplicação
                # ==================================================
                if estado["tempo_acumulado"][ticker] >= TEMPO_ACUMULADO_MAXIMO:
                    if estado["status"].get(ticker) in ["🚀 Disparado", "✅ Removendo...", "✅ Ativado (removido)"]:
                        log(f"{ticker} já foi disparado ou está sendo removido. Ignorando duplicação.", "⏸️")
                        continue

                    estado["status"][ticker] = "🚀 Disparado"

                    msg_op = "VENDA A DESCOBERTO" if operacao == "venda" else "COMPRA"
                    ticker_symbol_sem_ext = ticker.replace(".SA", "")

                    # =============================
                    # ✉️ MENSAGEM DE ALERTA COMPLETA
                    # =============================
                    msg_tg = f"""
💥 <b>ALERTA DE {msg_op.upper()} ATIVADA!</b>\n\n
<b>Ticker:</b> {ticker_symbol_sem_ext}\n
<b>Preço alvo:</b> R$ {preco_alvo:.2f}\n
<b>Preço atual:</b> R$ {preco_atual:.2f}\n\n
📊 <a href='https://br.tradingview.com/symbols/{ticker_symbol_sem_ext}'>Abrir gráfico no TradingView</a>\n\n
───────────────\n
<i><b>COMPLIANCE:</b> mensagem baseada em nossa carteira e não constitui recomendação formal. A decisão de compra ou venda é exclusiva do destinatário. Conteúdo confidencial, uso restrito ao destinatário autorizado. © 1milhão Invest.</i>\n
───────────────\n
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

                   
                    enviar_alerta(                                   
                        "curto",
                        f"🔥 ALERTA CARTEIRA DE CURTO PRAZO — {msg_op.upper()} {ticker}",
                        msg_html,
                        msg_tg
                    )

                    estado["historico_alertas"].append({
                        "hora": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "ticker": ticker,
                        "operacao": operacao,
                        "preco_alvo": preco_alvo,
                        "preco_atual": preco_atual
                    })

                    # ==================================================
                    # ✅ LIMPEZA DEFINITIVA APÓS ALERTA
                    # ==================================================
                    estado["status"][ticker] = "✅ Removendo..."
                    log(f"{ticker} marcado como 'Removendo...'", "🗂️")

                    estado["ativos"] = [a for a in estado["ativos"] if a.get("ticker") != ticker]
                    estado["tempo_acumulado"].pop(ticker, None)
                    estado["em_contagem"].pop(ticker, None)
                    estado["precos_historicos"] = estado.get("precos_historicos", {})
                    estado["precos_historicos"].pop(ticker, None)

                    try:
                        # ✅ CORREÇÃO: apaga somente o ticker
                        apagar_estado_duravel(STATE_KEY, apenas_ticker=ticker)
                        salvar_estado_duravel(STATE_KEY, estado)
                        log(f"{ticker} removido do Supabase e estado atualizado.", "🗑️")
                    except Exception as e:
                        log(f"Erro ao limpar {ticker} no Supabase: {e}", "⚠️")

                    estado["status"][ticker] = "✅ Ativado (removido)"
                    salvar_estado_duravel(STATE_KEY, estado)
                    log(f"{ticker} removido completamente e persistido.", "💾")
                    continue

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

