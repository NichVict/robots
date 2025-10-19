import os
from dotenv import load_dotenv
from datetime import time

# Carrega variáveis do .env (para rodar localmente)
load_dotenv()

# ==========================
# CONFIGURAÇÕES GERAIS
# ==========================
TZ = os.getenv("TZ", "Europe/Lisbon")
HORARIO_INICIO_PREGAO = os.getenv("HORARIO_INICIO_PREGAO", "14:00")
HORARIO_FIM_PREGAO = os.getenv("HORARIO_FIM_PREGAO", "21:00")

def parse_time(hora_str):
    h, m = hora_str.split(":")
    return time(int(h), int(m))

HORARIO_INICIO_PREGAO = parse_time(HORARIO_INICIO_PREGAO)
HORARIO_FIM_PREGAO = parse_time(HORARIO_FIM_PREGAO)

# ==========================
# E-MAIL / TELEGRAM
# ==========================
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# ==========================
# SUPABASE E DESTINATÁRIOS
# ==========================
ROBOTS = {
    "curto": {
        "SUPABASE_URL": os.getenv("SUPABASE_URL_CURTO"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_CURTO"),
        "TABLE": "kv_state_curto",
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_CURTO"),
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_CURTO"),
    },
    "loss_curto": {
        "SUPABASE_URL": os.getenv("SUPABASE_URL_LOSS_CURTO"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_LOSS_CURTO"),
        "TABLE": "kv_state_losscurto",
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_LOSS_CURTO"),
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_LOSS_CURTO"),
    },
    "clube": {
        "SUPABASE_URL": os.getenv("SUPABASE_URL_CLUBE"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_CLUBE"),
        "TABLE": "kv_state_clube",
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_CLUBE"),
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_CLUBE"),
    },
    "loss_clube": {
        "SUPABASE_URL": os.getenv("SUPABASE_URL_LOSS_CLUBE"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_LOSS_CLUBE"),
        "TABLE": "kv_state_lossclube",
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_LOSS_CLUBE"),
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_LOSS_CLUBE"),
    },
    "curtissimo": {
        "SUPABASE_URL": os.getenv("SUPABASE_URL_CURTISSIMO"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_CURTISSIMO"),
        "TABLE": "kv_state_curtissimo",
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_CURTISSIMO"),
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_CURTISSIMO"),
    },
    "loss_curtissimo": {
        "SUPABASE_URL": os.getenv("SUPABASE_URL_LOSS_CURTISSIMO"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY_LOSS_CURTISSIMO"),
        "TABLE": "kv_state_losscurtissimo",
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID_LOSS_CURTISSIMO"),
        "EMAIL_RECIPIENT": os.getenv("EMAIL_RECIPIENT_LOSS_CURTISSIMO"),
    },
}

