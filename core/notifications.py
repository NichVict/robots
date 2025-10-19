# core/notifications.py
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from telegram import Bot
from core.config import EMAIL_SENDER, GMAIL_APP_PASSWORD, TELEGRAM_TOKEN, ROBOTS

# ==================================================
# ✉️ Função para envio de e-mail (Gmail SMTP)
# ==================================================
def enviar_email_html(destinatario, assunto, corpo_html):
    if not EMAIL_SENDER or not GMAIL_APP_PASSWORD:
        print("⚠️ Email não configurado. Verifique .env")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = EMAIL_SENDER
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo_html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_SENDER, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)

        print(f"📧 Email enviado para {destinatario}")
        return True

    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {e}")
        return False


# ==================================================
# 💬 Função para envio de mensagem Telegram
# ==================================================
async def enviar_telegram_async(chat_id: str, mensagem: str):
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=mensagem,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        print(f"📲 Telegram enviado para {chat_id}")
        return True
    except Exception as e:
        print(f"❌ Erro Telegram: {e}")
        return False


def enviar_telegram(chat_id: str, mensagem: str):
    asyncio.run(enviar_telegram_async(chat_id, mensagem))


# ==================================================
# 🚀 Função central para envio de alertas
# ==================================================
def enviar_alerta(robot_name: str, assunto: str, corpo_html: str, corpo_telegram: str = None):
    """
    Envia um alerta via e-mail e Telegram com base nas configs do robô.
    """
    if robot_name not in ROBOTS:
        print(f"Robô '{robot_name}' não encontrado nas configurações.")
        return

    cfg = ROBOTS[robot_name]
    email_dest = cfg.get("EMAIL_RECIPIENT")
    chat_id = cfg.get("TELEGRAM_CHAT_ID")

    # E-mail
    ok_email = enviar_email_html(email_dest, assunto, corpo_html) if email_dest else False

    # Telegram
    corpo_tg = corpo_telegram if corpo_telegram else corpo_html
    ok_tg = False
    if chat_id and TELEGRAM_TOKEN:
        ok_tg = asyncio.run(enviar_telegram_async(chat_id, corpo_tg))

    status = []
    if ok_email:
        status.append("📧 Email")
    if ok_tg:
        status.append("💬 Telegram")

    if status:
        print(f"✅ Alerta enviado via {', '.join(status)} para {robot_name}")
    else:
        print(f"⚠️ Nenhum canal ativo para {robot_name}")

