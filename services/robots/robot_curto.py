# services/robots/robot_curto.py
# -*- coding: utf-8 -*-
import time
import datetime
from zoneinfo import ZoneInfo
from core.state import carregar_estado_duravel, salvar_estado_duravel, apagar_estado_duravel
from core.prices import obter_preco_atual
from core.notifications import enviar_alerta

# ==================================================
# ⚙️ CONFIGURAÇÕES
# ==================================================
TZ = ZoneInfo("Europe/Lisbon")
HORARIO_INICIO_PREGAO = datetime.time(14, 0, 0)
HORARIO_FIM_PREGAO = datetime.time(21, 0, 0)
INTERVALO_VERIFICACAO = 300       # 5 minutos
TEMPO_ACUMULADO_MAXIMO = 1500     # 25 minutos

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
print("🤖 Robô CURTO iniciado.")
estado = carregar_estado_duravel("curto")

if not isinstance(estado, dict):
    estado = {}

estado.setdefault("ativos", [])
estado.setdefault("tempo_acumulado", {})
estado.setdefault("em_contagem", {})
estado.setdefault("status", {})
estado.setdefault("historico_alertas", [])
estado.setdefault("ultima_data_abertura_enviada", None)

try:
    if isinstance(estado["ultima_data_abertura_enviada"], datetime.date):
        estado["ultima_data_abertura_enviada"] = estado["ultima_data_abertura_enviada"].isoformat()
    elif not isinstance(estado["ultima_data_abertura_enviada"], str):
        estado["ultima_data_abertura_enviada"] = None
except Exception:
    estado["ultima_data_abertura_enviada"] = None

print(f"📦 {len(estado['ativos'])} ativos carregados.")
print("=" * 60)

# ==================================================
# 🔁 LOOP PRINCIPAL
# ==================================================
while True:
    now = agora_lx()

    if dentro_pregao(now):
        data_hoje = str(now.date())
        ultima = str(estado.get("ultima_data_abertura_enviada", ""))

        # 🔒 Envia mensagem de abertura 1x por dia
        if ultima != data_hoje:
            enviar_alerta(
                "curto",
                "📣 Pregão Aberto",
                "<b>O pregão foi iniciado! 🟢</b><br><i>O robô de curto prazo está monitorando os ativos.</i>",
                "🤖 Robô iniciando monitoramento — Pregão Aberto!"
            )
            estado["ultima_data_abertura_enviada"] = data_hoje
            salvar_estado_duravel("curto", estado)
            print(f"[{now.strftime('%H:%M:%S')}] 📣 Mensagem de abertura enviada ({data_hoje}).\n")

        print(f"[{now.strftime('%H:%M:%S')}] 🟢 Monitorando {len(estado['ativos'])} ativos...")

        tickers_para_remover = []

        for ativo in estado["ativos"]:
            ticker = ativo["ticker"]
            preco_alvo = ativo["preco"]
            operacao = ativo["operacao"]
            tk_full = f"{ticker}.SA" if not ticker.endswith(".SA") else ticker

            try:
                preco_atual = obter_preco_atual(tk_full)
            except Exception as e:
                print(f"⚠️ Erro ao obter preço de {ticker}: {e}")
                continue

            if not preco_atual or preco_atual <= 0:
                print(f"⚠️ Preço inválido para {ticker}. Pulando...")
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
                    print(f"⚠️ {ticker} atingiu o alvo ({preco_alvo:.2f}). Iniciando contagem...")
                else:
                    estado["tempo_acumulado"][ticker] += INTERVALO_VERIFICACAO
                    print(f"⌛ {ticker}: {formatar_duracao(estado['tempo_acumulado'][ticker])} acumulados.")

                # 🚀 Disparo do alerta
                if estado["tempo_acumulado"][ticker] >= TEMPO_ACUMULADO_MAXIMO:
                    estado["status"][ticker] = "🚀 Disparado"

                    msg_op = "VENDA A DESCOBERTO" if operacao == "venda" else "COMPRA"
                    ticker_symbol_sem_ext = ticker.replace(".SA", "")

                    msg_tg = f"""
💥 <b>ALERTA DE {msg_op.upper()} ATIVADA!</b>\n\n
<b>Ticker:</b> {ticker_symbol_sem_ext}\n
<b>Preço alvo:</b> R$ {preco_alvo:.2f}\n
<b>Preço atual:</b> R$ {preco_atual:.2f}\n\n
📊 <a href='https://br.tradingview.com/symbols/{ticker_symbol_sem_ext}'>Abrir gráfico no TradingView</a>
""".strip()

                    msg_html = f"""
<html>
  <body style="font-family:Arial,sans-serif; background-color:#0b1220; color:#e5e7eb; padding:20px;">
    <h2 style="color:#3b82f6;">💥 ALERTA DE {msg_op.upper()} ATIVADA!</h2>
    <p><b>Ticker:</b> {ticker_symbol_sem_ext}</p>
    <p><b>Preço alvo:</b> R$ {preco_alvo:.2f}</p>
    <p><b>Preço atual:</b> R$ {preco_atual:.2f}</p>
    <p>📊 <a href="https://br.tradingview.com/symbols/{ticker_symbol_sem_ext}" style="color:#60a5fa;">Ver gráfico</a></p>
    <hr style="border:1px solid #3b82f6; margin:20px 0;">
    <p style="font-size:11px; color:#9ca3af;">Mensagem de alerta automática do robô CURTO.</p>
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

                    tickers_para_remover.append(ticker)
                    estado["em_contagem"][ticker] = False
                    estado["tempo_acumulado"][ticker] = 0

            else:
                if estado["em_contagem"].get(ticker, False):
                    print(f"❌ {ticker} saiu da zona de preço.")
                    estado["em_contagem"][ticker] = False
                    estado["tempo_acumulado"][ticker] = 0
                    estado["status"][ticker] = "🔴 Fora da zona"

        # -----------------------------
        # 🧹 LIMPEZA PÓS-ATIVAÇÃO
        # -----------------------------
        if tickers_para_remover:
            estado["ativos"] = [a for a in estado["ativos"] if a["ticker"] not in tickers_para_remover]
            for t in tickers_para_remover:
                estado["tempo_acumulado"].pop(t, None)
                estado["em_contagem"].pop(t, None)
                estado["status"][t] = "✅ Ativado (removido)"
                # 🔥 Limpeza seletiva no Supabase
                try:
                    apagar_estado_duravel("curto", apenas_ticker=t)
                    print(f"🗑️ Registro de {t} removido do Supabase (curto).")
                except Exception as e:
                    print(f"⚠️ Erro ao limpar {t} no Supabase: {e}")
            print(f"🧹 Removidos após ativação: {', '.join(tickers_para_remover)}")

        salvar_estado_duravel("curto", estado)
        print("💾 Estado salvo.\n")
        time.sleep(INTERVALO_VERIFICACAO)

    else:
        faltam, prox = segundos_ate_abertura(now)
        print(f"[{now.strftime('%H:%M:%S')}] 🟥 Pregão fechado. Próximo em {formatar_duracao(faltam)} (às {prox.strftime('%H:%M')}).")
        time.sleep(min(faltam, 3600))





