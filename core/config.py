# core/config.py
import os
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()

# ================================
# 🌍 CONFIGURAÇÕES GERAIS
# ================================
TZ = os.getenv("TZ", "Europe/Lisbon")
HORARIO_INICIO_PREGAO = os.getenv("HORARIO_INICIO_PREGAO", "14:00")
HORARIO_FIM_PREGAO = os.getenv("HORARIO_FIM_PREGAO", "21:00")

# ================================
# 🔐 E-MAIL
# ================================
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# ================================
# 💬 TELEGRAM
# ================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# ================================
# 🤖 ROBÔS CONFIGURADOS
# ================================
ROBOTS = {
    "curto": {
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_CURTO"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_CURTO"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL_CURTO"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_CURTO"),
    },
    "curtissimo": {
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_CURTISSIMO"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_CURTISSIMO"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL_CURTISSIMO"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_CURTISSIMO"),
    },
    "loss_curto": {
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_LOSS_CURTO"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_LOSS_CURTO"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL_LOSS_CURTO"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_LOSS_CURTO"),
    },
    "loss_curtissimo": {
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_LOSS_CURTISSIMO"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_LOSS_CURTISSIMO"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL_LOSS_CURTISSIMO"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_LOSS_CURTISSIMO"),
    },
    "clube": {
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_CLUBE"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_CLUBE"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL_CLUBE"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_CLUBE"),
    },
    "loss_clube": {
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_LOSS_CLUBE"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_LOSS_CLUBE"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL_LOSS_CLUBE"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_LOSS_CLUBE"),
    },
}

# ================================
# ⏱️ PARÂMETROS DO ROBÔ
# ================================
# Tempo entre verificações (em segundos)
INTERVALO_VERIFICACAO = 60  # 1 minuto

# Tempo total que o ativo deve permanecer na zona de preço antes do alerta
TEMPO_ACUMULADO_MAXIMO = 300  # 5 minutos
