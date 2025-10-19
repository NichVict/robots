# 🤖 Robots 1Milhão Invest

Sistema com **6 robôs financeiros** automatizados e integrados ao **Supabase**, **Telegram** e **Gmail**,  
com interface em **Streamlit** e execução contínua no **Render.com**.

---

## 🧩 Estrutura

robots/
├── app/painel.py # Painel principal (monitoramento dos robôs)
├── services/robots/ # Robôs individuais
│ ├── curto.py
│ ├── loss_curto.py
│ ├── clube.py
│ ├── loss_clube.py
│ ├── curtissimo.py
│ └── loss_curtissimo.py
├── core/ # Utilitários internos (config, supabase, telegram, etc.)
├── .streamlit/secrets.toml # Credenciais (Supabase, Gmail, Telegram)
├── requirements.txt # Dependências Python
├── Procfile # Instruções de inicialização (Render)
└── README.md


---

## ⚙️ Configuração

1. **Instalar dependências**
   ```bash
   pip install -r requirements.txt
supabase_url_clube = "https://kflwifvrkcqmrzgpvhqe.supabase.co"
supabase_key_clube = "..."
telegram_token = "..."
telegram_chat_id_clube = "..."
email_sender = "..."
gmail_app_password = "..."
email_recipient_clube = "..."

streamlit run services/robots/clube.py

streamlit run services/robots/clube.py --server.port $PORT --server.address 0.0.0.0



---

esse formato é **enxuto, técnico e funcional** — ideal para manter no GitHub.  
assim que você colar e salvar, me diga **“ok README resumido”** para eu te enviar o próximo arquivo (`.env.example`).
