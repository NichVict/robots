# core/state.py
from __future__ import annotations

import json
from typing import Optional
from supabase import create_client, Client
from core.config import ROBOTS

# ==================================================
# 🔗 Conexões Supabase dinâmicas por robô
# ==================================================
SUPABASES: dict[str, Client] = {}
for nome, cfg in ROBOTS.items():
    url = cfg.get("SUPABASE_URL")
    key = cfg.get("SUPABASE_KEY")
    if url and key:
        try:
            SUPABASES[nome] = create_client(url, key)
        except Exception as e:
            print(f"⚠️ Erro ao criar cliente Supabase para '{nome}': {e}")

# ==================================================
# 🗂️ Mapeamento fixo das tabelas Supabase
# ==================================================
TABELAS = {
    "clube": "kv_state_clube",
    "curto": "kv_state_curto",
    "curtissimo": "kv_state_curtissimo",
    "loss_clube": "kv_state_lossclube",
    "loss_curto": "kv_state_losscurto",
    "loss_curtissimo": "kv_state_losscurtissimo",
}

DEFAULT_STATE = {
    "ativos": [],
    "tempo_acumulado": {},
    "em_contagem": {},
    "status": {},
}

def _sb_and_table(nome_robo: str) -> tuple[Client, str, str]:
    sb: Optional[Client] = SUPABASES.get(nome_robo)
    if not sb:
        raise ValueError(f"Supabase não configurado para '{nome_robo}'.")
    tabela = TABELAS.get(nome_robo)
    if not tabela:
        raise ValueError(f"Tabela não definida para o robô '{nome_robo}'.")
    chave = f"{nome_robo}_przo_v1"
    return sb, tabela, chave

# ==================================================
# 📥 Carregar
# ==================================================
def carregar_estado_duravel(nome_robo: str) -> dict:
    """Carrega o estado do robô a partir do registro-único (k = '<robo>_przo_v1')."""
    print(f"🔄 Carregando estado do robô '{nome_robo}'...")
    try:
        sb, tabela, chave = _sb_and_table(nome_robo)
    except Exception as e:
        print(f"⚠️ {e}")
        return DEFAULT_STATE.copy()

    try:
        res = sb.table(tabela).select("k,v").eq("k", chave).execute()
        if res.data:
            estado = res.data[0]["v"]
            if isinstance(estado, dict):
                print("✅ Estado carregado (1 chave).")
                return estado
        print("ℹ️ Nenhum estado encontrado — usando defaults.")
        return DEFAULT_STATE.copy()
    except Exception as e:
        print(f"⚠️ Erro ao carregar estado de {nome_robo}: {e}")
        return DEFAULT_STATE.copy()

# ==================================================
# 💾 Salvar (SEGURO)
# ==================================================
def salvar_estado_duravel(nome_robo: str, estado: dict) -> None:
    """
    Salva o estado do robô por upsert NA MESMA CHAVE.
    ⚠️ NÃO realiza nenhum DELETE em massa.
    """
    try:
        sb, tabela, chave = _sb_and_table(nome_robo)
    except Exception as e:
        print(f"⚠️ {e}")
        return

    try:
        sb.table(tabela).upsert({"k": chave, "v": estado}).execute()
        print(f"💾 Estado de '{nome_robo}' salvo com sucesso.")
    except Exception as e:
        print(f"⚠️ Erro ao salvar estado de {nome_robo}: {e}")

# ==================================================
# 🧹 Apagar (SEMPRE GRANULAR)
# ==================================================
def apagar_estado_duravel(nome_robo: str, apenas_ticker: Optional[str] = None) -> None:
    """
    Remoção segura:
      - Sem `apenas_ticker`: NÃO faz nada (bloqueia limpeza total).
      - Com `apenas_ticker`: remove só aquele ticker do estado e regrava.
    Use após alerta confirmado.
    """
    try:
        sb, tabela, chave = _sb_and_table(nome_robo)
    except Exception as e:
        print(f"⚠️ {e}")
        return

    try:
        # Carrega o registro atual
        res = sb.table(tabela).select("k,v").eq("k", chave).execute()
        if not res.data:
            print(f"ℹ️ Nenhum estado para '{nome_robo}'.")
            return
        estado = res.data[0]["v"] or {}

        if not apenas_ticker:
            print(f"🚫 Ação bloqueada: tentativa de apagar o estado completo de '{nome_robo}'.")
            print("   Use apagar_estado_duravel(nome_robo, apenas_ticker='TICKER').")
            return

        # Remove o ticker
        ativos_antes = len(estado.get("ativos", []))
        estado["ativos"] = [a for a in estado.get("ativos", []) if a.get("ticker") != apenas_ticker]
        # Zera auxiliares
        for campo in ("tempo_acumulado", "em_contagem", "status"):
            if isinstance(estado.get(campo), dict):
                estado[campo].pop(apenas_ticker, None)

        ativos_depois = len(estado.get("ativos", []))
        if ativos_depois < ativos_antes:
            sb.table(tabela).upsert({"k": chave, "v": estado}).execute()
            print(f"🧹 Ticker '{apenas_ticker}' removido do estado de '{nome_robo}'.")
        else:
            print(f"ℹ️ Ticker '{apenas_ticker}' não estava no estado de '{nome_robo}'.")

    except Exception as e:
        print(f"⚠️ Erro ao tentar apagar estado de {nome_robo}: {e}")






