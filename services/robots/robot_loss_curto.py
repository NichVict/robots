# robot_loss_curto.py
import time
import datetime
from core.state import carregar_estado, salvar_estado
from core.prices import obter_preco_atual
from core.notifications import enviar_alerta
from core.schedule import dentro_pregao, segundos_ate_abertura, agora_lx, formatar_duracao
from core.config import TEMPO_ACUMULADO_MAXIMO, INTERVALO_VERIFICACAO

APP_ID = "loss_curto"

print("🤖 Robô LOSS CURTO iniciado.")
estado = carregar_estado("loss_curto")
print(f"📦 {len(estado['ativos'])} ativos carregados do Supabase.")

# ==================================================
# 🔔 Função de envio customizada (mensagem STOP)
# ==================================================
def notificar_encerramento_stop(ticker: str, preco_alvo: float, preco_atual: float, operacao: str):
    ticker_sem_ext = ticker.replace(".SA", "")
    if operacao == "venda":
        msg_operacao_anterior = "COMPRA"
        direcao = "⬇️ Queda"
    else:
        msg_operacao_anterior = "VENDA A DESCOBERTO"
        direcao = "⬆️ Alta"

    msg_tg = (
        f"🛑 <b>ENCERRAMENTO (STOP) ATIVADO!</b>\n\n"
        f"<b>Ticker:</b> {ticker_sem_ext}\n"
        f"<b>Operação anterior:</b> {msg_operacao_anterior}\n"
        f"<b>Encerramento via:</b> {operacao.upper()}\n\n"
        f"<b>STOP:</b> R$ {preco_alvo:.2f}\n"
        f"<b>Preço atual:</b> R$ {preco_atual:.2f}\n\n"
        f"{direcao} | <a href='https://br.tradingview.com/symbols/{ticker_sem_ext}'>Ver gráfico</a>"
    )

    msg_html = f"""
    <html>
      <body style="font-family:Arial,sans-serif; background-color:#0b1220; color:#e5e7eb; padding:20px;">
        <h2 style="color:#ef4444;">ALERTA STOP - LOSS CURTO</h2>
        <p><b>Ticker:</b> {ticker_sem_ext}</p>
        <p><b>Operação anterior:</b> {msg_operacao_anterior}</p>
        <p><b>Encerramento via:</b> {operacao.upper()}</p>
        <p><b>STOP:</b> R$ {preco_alvo:.2f}</p>
        <p><b>Preço atual:</b> R$ {preco_atual:.2f}</p>
        <p>📊 <a href="https://br.tradingview.com/symbols/{ticker_sem_ext}" style="color:#60a5fa;">Abrir gráfico</a></p>
        <hr style="border:1px solid #ef4444; margin:20px 0;">
        <p style="font-size:11px; color:#9ca3af;">
          <b>COMPLIANCE:</b> Esta mensagem é uma sugestão de ENCERRAMENTO baseada na CARTEIRA CURTO PRAZO.<br>
          A execução é de total decisão e responsabilidade do Destinatário.<br>
          Esta informação é CONFIDENCIAL, de propriedade de 1milhao Invest e de seu DESTINATÁRIO tão somente.<br>
          A Lista de Ações do Canal 1milhao é devidamente REGISTRADA.
        </p>
      </body>
    </html>
    """
    enviar_alerta("loss_curto", f"🛑 ENCERRAMENTO (STOP) — {ticker_sem_ext}", msg_html, msg_tg)


# ==================================================
# 🔁 LOOP PRINCIPAL
# ==================================================
while True:
    agora = agora_lx()

    if dentro_pregao(agora):
        print(f"\n[{agora.strftime('%H:%M:%S')}] 🟢 Pregão aberto — monitorando STOPs...")

        for ativo in estado["ativos"]:
            ticker = ativo["ticker"]
            preco_alvo = ativo["preco"]
            operacao = ativo["operacao"]
            tk_full = f"{ticker}.SA" if not ticker.endswith(".SA") else ticker

            preco_atual = obter_preco_atual(tk_full)
            if preco_atual <= 0:
                print(f"⚠️ Falha ao obter preço de {ticker}.")
                continue

            condicao = (
                (operacao == "compra" and preco_atual >= preco_alvo)
                or (operacao == "venda" and preco_atual <= preco_alvo)
            )

            if condicao:
                if not estado["em_contagem"].get(ticker, False):
                    estado["em_contagem"][ticker] = True
                    estado["tempo_acumulado"][ticker] = 0
                    print(f"⚠️ {ticker} entrou na zona de STOP.")
                else:
                    estado["tempo_acumulado"][ticker] += INTERVALO_VERIFICACAO
                    print(f"⌛ {ticker}: {formatar_duracao(estado['tempo_acumulado'][ticker])} acumulados.")

                    if estado["tempo_acumulado"][ticker] >= TEMPO_ACUMULADO_MAXIMO:
                        print(f"🛑 ENCERRAMENTO (STOP) confirmado: {ticker}")
                        notificar_encerramento_stop(tk_full, preco_alvo, preco_atual, operacao)
                        estado["status"][ticker] = "🚀 Encerrado"
                        estado["em_contagem"][ticker] = False
                        estado["tempo_acumulado"][ticker] = 0

            else:
                if estado["em_contagem"].get(ticker, False):
                    print(f"❌ {ticker} saiu da zona STOP.")
                    estado["em_contagem"][ticker] = False
                    estado["tempo_acumulado"][ticker] = 0
                    estado["status"][ticker] = "🔴 Fora do STOP"

        salvar_estado("loss_curto", estado)
        print("💾 Estado salvo.")
        time.sleep(INTERVALO_VERIFICACAO)

    else:
        faltam, prox = segundos_ate_abertura(agora)
        print(f"\n[{agora.strftime('%H:%M:%S')}] 🟥 Pregão fechado. Dormindo {faltam//60} min até {prox.strftime('%H:%M')}...\n")
        time.sleep(min(faltam, 3600))

