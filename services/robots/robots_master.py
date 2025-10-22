# services/robots/robots_master.py
# -*- coding: utf-8 -*-
"""
🧠 Master Controller — Robôs 1Milhão Invest (Render Edition)
Executa todos os 6 robôs simultaneamente em subprocessos independentes.
Garante flush imediato e logging visível no Render.
"""

import subprocess
import threading
import time
import sys
import os
from datetime import datetime

ROBOTS = [
    ("CURTO", "services.robots.robot_curto"),
    ("CURTISSIMO", "services.robots.robot_curtissimo"),
    ("CLUBE", "services.robots.robot_clube"),
    ("LOSS_CURTO", "services.robots.robot_loss_curto"),
    ("LOSS_CURTISSIMO", "services.robots.robot_loss_curtissimo"),
    ("LOSS_CLUBE", "services.robots.robot_loss_clube"),
]

# ==================================================
# 🧩 Função auxiliar para rodar subprocesso e logar stdout/stderr
# ==================================================
def iniciar_robo(nome_exibicao, modulo_import):
    while True:
        try:
            print(f"\n🚀 Iniciando robô [{nome_exibicao}]...\n", flush=True)

            # Executa cada robô como subprocesso real (Render capta stdout)
            proc = subprocess.Popen(
                [sys.executable, "-m", modulo_import],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True
            )

            # Prefixa cada linha de saída com o nome do robô
            for line in proc.stdout:
                timestamp = datetime.utcnow().strftime("%H:%M:%S")
                print(f"[{timestamp}] [{nome_exibicao}] {line.rstrip()}", flush=True)

            proc.wait()
            print(f"🔁 Robô [{nome_exibicao}] terminou — reiniciando em 60s...\n", flush=True)
            time.sleep(60)

        except KeyboardInterrupt:
            print(f"🛑 [{nome_exibicao}] interrompido manualmente.")
            break
        except Exception as e:
            print(f"⚠️ Erro no robô [{nome_exibicao}]: {e}", flush=True)
            time.sleep(30)

# ==================================================
# 🚀 Inicialização principal
# ==================================================
threads = []
for nome, modulo in ROBOTS:
    t = threading.Thread(target=iniciar_robo, args=(nome, modulo), daemon=True)
    threads.append(t)
    t.start()
    time.sleep(3)

print("\n🧠 Todos os robôs foram iniciados com sucesso.\n", flush=True)
print("📡 Monitorando execução contínua... Pressione Ctrl+C para encerrar.\n", flush=True)

try:
    while True:
        vivos = [n for n, t in zip([r[0] for r in ROBOTS], threads) if t.is_alive()]
        print(f"[{time.strftime('%H:%M:%S')}] Robôs ativos: {', '.join(vivos)}", flush=True)
        time.sleep(120)
except KeyboardInterrupt:
    print("\n🛑 Encerrando master manualmente...")

