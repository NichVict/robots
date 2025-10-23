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

# ==================================================
# 💬 LOGGING EM TEMPO REAL (Render-friendly)
# ==================================================
# Substitui o print padrão por versão com flush imediato
print = lambda *args, **kwargs: builtins.print(*args, **kwargs, flush=True)

# ==================================================
# ⚙️ CONFIGURAÇÕES
# ==================================================
TZ = ZoneInfo("Europe/Lisbon")
HORARIO_INICIO_PREGAO = datetime.time(3, 0, 0)
HORARIO_FIM_PREGAO = datetime.time(23, 59, 0)
INTERVALO_VERIFICACAO = 60       # 1 minuto
TEMPO_ACUMULADO_MAXIMO = 300     # 5 minutos

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
estado = carregar_estado_duravel("curto")

if not estado:
    log("Falha ao carregar estado remoto — aguardando reconexão...", "⚠️")
    while not estado:
        time.sleep(60)
        estado = carregar_estado_duravel("curto")
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
    # 🔄 RECARREGAR ESTADO DO SUPABASE (regra 1)
    # ==================================================
        # ==================================================
    # 🧹 LIMPEZA PREVENTIVA DE TICKERS REMOVIDOS
    # ==================================================
    try:
        # Remove qualquer ticker marcado como "Removido" ou "Removendo"
        tickers_para_limpar = [
            t for t, s in estado.get("status", {}).items()
            if isinstance(s, str) and ("Removido" in s or "Removendo" in s)
        ]
        if tickers_para_limpar:
            for t in tickers_para_limpar:
                estado["status"].pop(t, None)
                estado["tempo_acumulado"].pop(t, None)
                estado["em_contagem"].pop(t, None)
            # Atualiza o Supabase com estado limpo
            salvar_estado_duravel("curto", estado)
            log(f"🧹 Limpou resíduos de {', '.join(tickers_para_limpar)} no início do ciclo.", "✅")
    except Exception as e:
        log(f"⚠️ Falha ao limpar resíduos de tickers removidos: {e}", "⚠️")




    # ==================================================
    # 🕓 FLUXO NORMAL — DURANTE O PREGÃO
    # ==================================================
    if dentro_pregao(now):
        data_hoje = str(now.date())
        ultima = str(estado.get("ultima_data_abertura_enviada", ""))

        # 🔒 Envia mensagem de abertura 1x por dia
        if ultima != data_hoje:
            enviar_alerta(
                "curto",
                "📣 Pregão Aberto",
                "<b>O pregão foi iniciado! 🟢</b><br><i>O robô de curto prazo está monitorando os ativos.</i>",
                "🤖 Robô CURTO iniciando monitoramento — Pregão Aberto!"
            )
            estado["ultima_data_abertura_enviada"] = data_hoje

            # 🧹 ZERA contagens do dia anterior
            log("🧹 Limpando contagens do dia anterior (novo pregão iniciado)...", "🔁")
            estado["tempo_acumulado"].clear()
            estado["em_contagem"].clear()
            estado["status"].clear()

            salvar_estado_duravel("curto", estado)
            log("Contagens zeradas com sucesso para o novo pregão.", "✅")

        log(f"Monitorando {len(estado['ativos'])} ativos...", "🟢")

        # ==================================================
        # 🔍 Verificação de cada ativo
        # ==================================================
        for ativo in estado["ativos"]:
            ticker = ativo["ticker"]
            preco_alvo = ativo["preco"]
            operacao = ativo["operacao"]
            tk_full = f"{ticker}.SA" if not ticker.endswith(".SA") else ticker

            try:
                preco_atual = obter_preco_atual(tk_full)
                # 🧩 Proteção: evita strings, None, etc.
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

                    # ==================================================
                    # 🔒 BLOQUEIO TRANSACIONAL (anti-duplicação entre instâncias)
                    # ==================================================
                    try:
                        estado_remoto = carregar_estado_duravel("curto")
                        status_remoto = estado_remoto.get("status", {}).get(ticker, "")

                        if "🚀" in status_remoto or "Removido" in status_remoto or "Removendo" in status_remoto:
                            log(f"⏸️ {ticker} já foi disparado por outra instância. Abortando duplicação.", "⚠️")
                            continue

                        # Marca imediatamente como 'Disparando...' no Supabase
                        estado["status"][ticker] = "🚀 Disparando..."
                        salvar_estado_duravel("curto", estado)
                        log(f"🔒 {ticker} bloqueado como 'Disparando...' (transação aberta).", "🔐")

                    except Exception as e:
                        log(f"⚠️ Falha no bloqueio transacional de {ticker}: {e}", "⚠️")




                    estado["status"][ticker] = "🚀 Disparado"

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

                    enviar_alerta("curto", f"Alerta {msg_op.upper()} - {ticker}", msg_html, msg_tg)

                    estado["historico_alertas"].append({
                        "hora": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "ticker": ticker,
                        "operacao": operacao,
                        "preco_alvo": preco_alvo,
                        "preco_atual": preco_atual
                    })

                    # ==================================================
                    # ✅ REMOÇÃO DEFINITIVA — ordem corrigida (apaga antes de salvar)
                    # ==================================================
                    estado["status"][ticker] = "✅ Removendo..."
                    log(f"{ticker} marcado como 'Removendo...'", "🗂️")

                    # 1️⃣ Remove localmente da lista e dicionários
                    estado["ativos"] = [a for a in estado["ativos"] if a.get("ticker") != ticker]
                    estado["tempo_acumulado"].pop(ticker, None)
                    estado["em_contagem"].pop(ticker, None)

                    try:
                        # 2️⃣ Apaga primeiro no Supabase (para limpar antes do novo save)
                        apagar_estado_duravel("curto", apenas_ticker=ticker)
                        log(f"Registro de {ticker} removido do Supabase.", "🗑️")
                    except Exception as e:
                        log(f"Erro ao limpar {ticker} no Supabase: {e}", "⚠️")

                    # 3️⃣ Marca como removido e salva o estado limpo
                    estado["status"][ticker] = "✅ Ativado (removido)"
                    salvar_estado_duravel("curto", estado)
                    log(f"{ticker} removido completamente e persistido.", "💾")

                    continue  # próximo ativo


        # --------------------------------------------------
        # 🧹 SALVAR ESTADO GERAL E ESPERAR PRÓXIMO CICLO
        # --------------------------------------------------
        salvar_estado_duravel("curto", estado)
        log("Estado salvo.", "💾")
        time.sleep(INTERVALO_VERIFICACAO)

