# core/state.py
import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from core.config import ROBOTS, TZ

# -----------------------------
# 🔧 CONFIGURAÇÕES GERAIS
# -----------------------------
LOCAL_STATE_DIR = "session_data"
os.makedirs(LOCAL_STATE_DIR, exist_ok=True)

def agora_lx():
    return datetime.now(ZoneInfo(TZ))

# -----------------------------
# 💾 CLASSE DE ESTADO DO ROBÔ
# -----------------------------
class RobotState:
    """
    Classe responsável por salvar e carregar o estado
    (tanto local quanto remoto) de cada robô.
    """

    def __init__(self, robot_name: str):
        if robot_name not in ROBOTS:
            raise ValueError(f"Robô desconhecido: {robot_name}")

        self.robot_name = robot_name
        cfg = ROBOTS[robot_name]

        self.supabase_url = cfg["SUPABASE_URL"]
        self.supabase_key = cfg["SUPABASE_KEY"]
        self.table = cfg["TABLE"]

        self.local_file = os.path.join(LOCAL_STATE_DIR, f"state_{robot_name}.json")

    # -----------------------------
    # 🔹 SALVAR ESTADO
    # -----------------------------
    def save(self, data: dict):
        """
        Salva o estado no Supabase e localmente.
        """
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        payload = {"k": f"state_{self.robot_name}", "v": data}
        url = f"{self.supabase_url}/rest/v1/{self.table}"

        try:
            r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
            if r.status_code not in (200, 201, 204):
                print(f"[{self.robot_name}] Erro ao salvar remoto: {r.text}")
        except Exception as e:
            print(f"[{self.robot_name}] Falha no Supabase: {e}")

        # Fallback local
        try:
            with open(self.local_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[{self.robot_name}] Falha ao salvar local: {e}")

    # -----------------------------
    # 🔹 CARREGAR ESTADO
    # -----------------------------
    def load(self) -> dict:
        """
        Carrega o estado do Supabase; se falhar, usa o arquivo local.
        """
        headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}"}
        url = f"{self.supabase_url}/rest/v1/{self.table}?k=eq.state_{self.robot_name}&select=v"

        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200 and r.json():
                return r.json()[0]["v"]
            else:
                print(f"[{self.robot_name}] Nenhum estado remoto encontrado.")
        except Exception as e:
            print(f"[{self.robot_name}] Erro Supabase: {e}")

        # Fallback local
        if os.path.exists(self.local_file):
            try:
                with open(self.local_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[{self.robot_name}] Erro no fallback local: {e}")

        return {}

    # -----------------------------
    # 🔹 APAGAR ESTADO
    # -----------------------------
    def clear(self):
        """
        Apaga o estado remoto e local do robô.
        """
        headers = {"apikey": self.supabase_key, "Authorization": f"Bearer {self.supabase_key}"}
        url = f"{self.supabase_url}/rest/v1/{self.table}?k=eq.state_{self.robot_name}"

        try:
            requests.delete(url, headers=headers, timeout=10)
        except Exception as e:
            print(f"[{self.robot_name}] Erro ao apagar remoto: {e}")

        if os.path.exists(self.local_file):
            try:
                os.remove(self.local_file)
            except Exception as e:
                print(f"[{self.robot_name}] Erro ao apagar local: {e}")

