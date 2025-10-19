# core/schedule.py
import datetime
from zoneinfo import ZoneInfo
from core.config import TZ, HORARIO_INICIO_PREGAO, HORARIO_FIM_PREGAO

# ==================================================
# 🔧 Conversão segura dos horários (string → datetime.time)
# ==================================================
def _parse_time(hora_str):
    """Converte 'HH:MM' (string) em objeto datetime.time"""
    if isinstance(hora_str, datetime.time):
        return hora_str
    h, m = map(int, str(hora_str).split(":"))
    return datetime.time(hour=h, minute=m)

HORARIO_INICIO_PREGAO = _parse_time(HORARIO_INICIO_PREGAO)
HORARIO_FIM_PREGAO = _parse_time(HORARIO_FIM_PREGAO)

# ==================================================
# 🕓 UTILITÁRIOS DE TEMPO
# ==================================================
def agora_lx() -> datetime.datetime:
    """Retorna o horário atual em Lisboa (ou TZ definido)."""
    return datetime.datetime.now(ZoneInfo(TZ))


def dentro_pregao(dt: datetime.datetime = None) -> bool:
    """Retorna True se estamos dentro do horário de pregão."""
    if dt is None:
        dt = agora_lx()
    t = dt.time()
    return HORARIO_INICIO_PREGAO <= t <= HORARIO_FIM_PREGAO


def segundos_ate_abertura(dt: datetime.datetime = None):
    """Calcula quantos segundos faltam até o próximo pregão."""
    if dt is None:
        dt = agora_lx()

    abre = dt.replace(
        hour=HORARIO_INICIO_PREGAO.hour,
        minute=HORARIO_INICIO_PREGAO.minute,
        second=0,
        microsecond=0,
    )
    fecha = dt.replace(
        hour=HORARIO_FIM_PREGAO.hour,
        minute=HORARIO_FIM_PREGAO.minute,
        second=0,
        microsecond=0,
    )

    if dt < abre:
        return int((abre - dt).total_seconds()), abre
    elif dt > fecha:
        prox = abre + datetime.timedelta(days=1)
        return int((prox - dt).total_seconds()), prox
    else:
        return 0, abre


def formatar_duracao(segundos: int) -> str:
    """Formata segundos em HH:MM:SS (ex: 3:15:08)."""
    return str(datetime.timedelta(seconds=segundos))

