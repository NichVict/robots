# core/state.py
import json
from supabase import create_client, Client
from core.config import ROBOTS

# ==================================================
# 🔗 Conexões Supabase dinâmicas por robô
# ==================================================
SUPABASES = {}

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

# ==================================================
# 📦 Funções de persistência durável
# ==================================================
def carregar_estado_duravel(nome_robo: str):
    """Carrega o estado do robô a partir do Supabase."""
    print(f"🔄 Carregando estado do robô '{nome_robo}'...")

    sb: Client = SUPABASES.get(nome_robo)
    if not sb:
        print(f"⚠️ Supabase não configurado para '{nome_robo}'. Usando estado vazio.")
        return {"ativos": [], "tempo_acumulado": {}, "em_contagem": {}, "status": {}}

    tabela = TABELAS.get(nome_robo)
    if not tabela:
        raise ValueError(f"Tabela não definida para o robô '{nome_robo}'.")

    try:
        data = sb.table(tabela).select("k", "v").execute()
        estado = {item["k"]: item["v"] for item in data.data}
        print(f"✅ Estado carregado ({len(estado)} chaves).")

        return list(estado.values())[0] if estado else {
            "ativos": [],
            "tempo_acumulado": {},
            "em_contagem": {},
            "status": {}
        }

    except Exception as e:
        print(f"⚠️ Erro ao carregar estado de {nome_robo}: {e}")
        return {"ativos": [], "tempo_acumulado": {}, "em_contagem": {}, "status": {}}


def salvar_estado_duravel(nome_robo: str, estado: dict):
    """Salva o estado do robô no Supabase."""
    sb: Client = SUPABASES.get(nome_robo)
    if not sb:
        print(f"⚠️ Supabase não configurado para '{nome_robo}'. Estado não será salvo.")
        return

    tabela = TABELAS.get(nome_robo)
    if not tabela:
        raise ValueError(f"Tabela não definida para o robô '{nome_robo}'.")

    try:
        sb.table(tabela).upsert({"k": f"{nome_robo}_przo_v1", "v": estado}).execute()
        print(f"💾 Estado de '{nome_robo}' salvo com sucesso.")
    except Exception as e:
        print(f"⚠️ Erro ao salvar estado de {nome_robo}: {e}")


def salvar_estado_duravel(nome_robo: str, estado: dict):
    """Salva o estado do robô no Supabase (substituição total, sem duplicar registros)."""
    sb: Client = SUPABASES.get(nome_robo)
    if not sb:
        print(f"⚠️ Supabase não configurado para '{nome_robo}'. Estado não será salvo.")
        return

    tabela = TABELAS.get(nome_robo)
    if not tabela:
        raise ValueError(f"Tabela não definida para o robô '{nome_robo}'.")

    try:
        chave = f"{nome_robo}_przo_v1"

        # 🔥 Apaga qualquer registro antigo antes de salvar
        sb.table(tabela).delete().neq("k", chave).execute()

        # 💾 Upsert substitui o registro único
        sb.table(tabela).upsert({"k": chave, "v": estado}).execute()
        print(f"💾 Estado de '{nome_robo}' salvo com sucesso (substituição completa).")
    except Exception as e:
        print(f"⚠️ Erro ao salvar estado de {nome_robo}: {e}")





