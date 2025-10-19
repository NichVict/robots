# robot_curto.py
import time
from core.state import carregar_estado, salvar_estado, apagar_estado
from core.prices import obter_preco_atual
from core.notifications import enviar_alerta
from core.schedule import dentro_pregao, segundos_ate_abertura, agora_lx, formatar_duracao
from core.config import TEMPO_ACUMULADO_MAXIMO, INTERVALO_VERIFICACAO

# ==================================================
# 🧠 Estado em memória
# ==================================================
estado = carregar_estado("curto")

# Estrutura esperada no estado:
# {
#   "ativos": [{"ticker": "PETR4.SA", "operacao": "compra", "preco": 37.50}, ...],
#   "tempo_acumulado": {"PETR4.SA": 0, ...},
#   "em_contagem": {"PETR4.SA": False, ...},
#   "status": {"PETR4.SA": "🟢 Monitorando", ...}
# }

print("🤖 Robô CURTO iniciado.")
print(f"📦 {len(estado['ativos'])} ativos carregados do Supabase.")
print("=" * 60)

# ==================================================
# 🔁 LOOP PRINCIPAL
# ==================================================
while True:
    agora = agora_lx()

    if dentro_pregao(agora):
        print(f"\n[{agora.strftime('%H:%M:%S')}] 🟢 Pregão aberto — verificando ativos...")

        for ativo in estado["ativos"]:
            ticker = ativo["ticker"]
            preco_alvo = ativo["preco"]
            operacao = ativo["operacao"]
            tk_full = f"{ticker}.SA" if not ticker.endswith(".SA") else ticker

            preco_atual = obter_preco_atual(tk_full)
            if preco_atual <= 0:
                print(f"⚠️ Falha ao obter preço de {ticker}. Pulando...")
                continue

            print(f"   {ticker}: R$ {preco_atual:.2f} (alvo {preco_alvo:.2f})")

            # --- Condição para ativar contagem ---
            condicao = (
                (operacao == "compra" and preco_atual >= preco_alvo) or
                (operacao == "venda" and preco_atual <= preco_alvo)
            )

            # --- Inicia contagem ---
            if condicao:
                if not estado["em_contagem"].get(ticker, False):
                    estado["em_contagem"][ticker] = True
                    estado["tempo_acumulado"][ticker] = 0
                    print(f"⚠️ {ticker} entrou na zona de preço.")
                else:
                    estado["tempo_acumulado"][ticker] += INTERVALO_VERIFICACAO
                    print(f"⌛ {ticker}: {formatar_duracao(estado['tempo_acumulado'][ticker])} acumulados.")

                    if estado["tempo_acumulado"][ticker] >= TEMPO_ACUMULADO_MAXIMO:
                        print(f"🚀 ALERTA DISPARADO: {ticker}")
                        msg_html = f"""
                        <h3>💥 Alerta de {operacao.upper()} ativado!</h3>
                        <p><b>Ticker:</b> {ticker}<br>
                        <b>Preço alvo:</b> R$ {preco_alvo:.2f}<br>
                        <b>Preço atual:</b> R$ {preco_atual:.2f}</p>
                        """
                        msg_tg = (
                            f"💥 ALERTA de {operacao.upper()} ativado!\n"
                            f"{ticker} | Alvo: R$ {preco_alvo:.2f} | Atual: R$ {preco_atual:.2f}"
                        )
                        enviar_alerta("curto", f"Alerta de {operacao} - {ticker}", msg_html, msg_tg)
                        estado["status"][ticker] = "🚀 Disparado"
                        estado["em_contagem"][ticker] = False
                        estado["tempo_acumulado"][ticker] = 0

            else:
                # Saiu da zona de preço
                if estado["em_contagem"].get(ticker, False):
                    print(f"❌ {ticker} saiu da zona de preço.")
                    estado["em_contagem"][ticker] = False
                    estado["tempo_acumulado"][ticker] = 0

        # 🔄 Salva o estado no Supabase/local
        salvar_estado("curto", estado)
        print("💾 Estado salvo.")
        time.sleep(INTERVALO_VERIFICACAO)

    else:
        # Fora do pregão → dorme até o próximo
        faltam, prox = segundos_ate_abertura(agora)
        print(f"\n[{agora.strftime('%H:%M:%S')}] 🟥 Pregão fechado. Dormindo {faltam//60} min até {prox.strftime('%H:%M')}...\n")
        time.sleep(min(faltam, 3600))  # dorme no máximo 1h entre checks

