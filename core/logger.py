# core/logger.py
from datetime import datetime, timezone
import builtins

def log(msg: str, icon: str = "💬"):
    """Log bonito e com flush automático (Render-friendly)."""
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    builtins.print(f"[{now}] {icon} {msg}", flush=True)

