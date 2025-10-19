# core/prices.py
from yahooquery import Ticker
import pandas as pd
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests

# ==================================================
# ⚙️ Função principal de preço atual
# ==================================================

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
)
def obter_preco_atual(ticker_symbol: str) -> float:
    """
    Retorna o preço atual do ativo usando YahooQuery.
    Se falhar, tenta várias vezes antes de desistir.
    """
    try:
        tk = Ticker(ticker_symbol)
        p = tk.price.get(ticker_symbol, {}).get("regularMarketPrice")
        if p is not None:
            return float(p)

        # fallback se o campo regularMarketPrice não existir
        hist = tk.history(period="1d")
        if isinstance(hist, pd.DataFrame) and not hist.empty:
            preco = hist["close"].iloc[-1]
            return float(preco)

    except Exception as e:
        print(f"⚠️ Erro ao obter preço de {ticker_symbol}: {e}")

    # última tentativa via API pública do Yahoo Finance (fallback bruto)
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker_symbol}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            p = data["quoteResponse"]["result"][0]["regularMarketPrice"]
            if p:
                return float(p)
    except Exception as e:
        print(f"⚠️ Erro fallback Yahoo API: {e}")

    # Se tudo falhar
    return -1.0


# ==================================================
# 🕒 Função auxiliar para debug e monitoramento
# ==================================================
def testar_ticker(ticker: str):
    """
    Exemplo: testar_ticker("PETR4.SA")
    """
    preco = obter_preco_atual(ticker)
    if preco > 0:
        print(f"✅ {ticker}: R$ {preco:.2f}")
    else:
        print(f"❌ Falha ao obter preço de {ticker}")

