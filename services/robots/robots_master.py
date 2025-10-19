# services/robots/robots_master.py
# -*- coding: utf-8 -*-
"""
🧠 Master Controller — Robôs 1Milhão Invest
Executa todos os 6 robôs simultaneamente em threads separadas:
- robot_curto
- robot_curtissimo
- robot_clube
- robot_loss_curto
- robot_loss_curtissimo
- robot_loss_clube
"""

import threading
import time
import importlib
import traceback

ROBOTS = [
    ("CURTO", "services.robots.robot_curto"),
    ("CURTISSIMO", "services.robots.robot_curtissimo"),
    ("CLUBE", "services.robots.robot_clube"),
    ("LOSS_CURTO", "services.robots.robot_loss_curto"),
    ("LOSS_CURTISSIMO", "services.robots.robot_loss_curtissimo"),
    ("LOSS_CLUBE", "services.robots.robot_loss_clube"),
]

def iniciar_robo(nome_exibicao, modulo_import):
    while True:
        try:
            print(f"\n🚀 Iniciando robô [{nome_exibicao}]...\n")
            mod = importlib.import_module(modulo_import)
            if hasattr(mod, "__main__"):
                mod.__main__()
            else:
                pass
            print(f"🔁 Robô [{nome_exibicao}] terminou — reiniciando em 60s...\n")
            time.sleep(60)
        except KeyboardInterrupt:
            print(f"🛑 [{nome_exibicao}] interrompido manualmente.")
            break
        except Exception as e:
            print(f"⚠️ Erro no robô [{nome_exibicao}]: {e}")
            traceback.print_exc()
            print(f"🔁 Reiniciando [{nome_exibicao}] em 30s...\n")
            time.sleep(30)

threads = []
for nome, modulo in ROBOTS:
    t = threading.Thread(target=iniciar_robo, args=(nome, modulo), daemon=True)
    threads.append(t)
    t.start()
    time.sleep(3)

print("\n🧠 Todos os robôs foram iniciados com sucesso.\n")
print("📡 Monitorando execução contínua... Pressione Ctrl+C para encerrar.\n")

try:
    while True:
        vivos = [n for n, t in zip([r[0] for r in ROBOTS], threads) if t.is_alive()]
        print(f"[{time.strftime('%H:%M:%S')}] Robôs ativos: {', '.join(vivos)}")
        time.sleep(120)
except KeyboardInterrupt:
    print("\n🛑 Encerrando master manualmente...")
