from datetime import datetime
import builtins


def log(msg: str, icon: str = "💬"):
    """Log bonito e com flush automático (Render-friendly)."""
    now = datetime.utcnow().strftime("%H:%M:%S")
    builtins.print(f"[{now}] {icon} {msg}", flush=True)
