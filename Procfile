##############################################
# 🧠 PROCFILE — Configuração de inicialização #
# Projeto: Robots 1Milhão Invest             #
# Local: raiz do repositório (/robots)       #
# Uso: Render detecta este arquivo para rodar o app
##############################################

# ==================================================
# 🌐 Painel principal de monitoramento (6 robôs)
# ==================================================
web: streamlit run app/painel.py --server.port $PORT --server.address 0.0.0.0


##############################################
# 🚀 OPÇÕES PARA OS ROBÔS INDIVIDUAIS
# (Copiar a linha correspondente ao criar
# um novo serviço no Render)
##############################################

# ---- CURTO PRAZO ----
# web: streamlit run services/robots/curto.py --server.port $PORT --server.address 0.0.0.0

# ---- LOSS CURTO ----
# web: streamlit run services/robots/loss_curto.py --server.port $PORT --server.address 0.0.0.0

# ---- CLUBE ----
# web: streamlit run services/robots/clube.py --server.port $PORT --server.address 0.0.0.0

# ---- LOSS CLUBE ----
# web: streamlit run services/robots/loss_clube.py --server.port $PORT --server.address 0.0.0.0

# ---- CURTÍSSIMO PRAZO ----
# web: streamlit run services/robots/curtissimo.py --server.port $PORT --server.address 0.0.0.0

# ---- LOSS CURTÍSSIMO ----
# web: streamlit run services/robots/loss_curtissimo.py --server.port $PORT --server.address 0.0.0.0
