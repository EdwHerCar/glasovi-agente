# agent/tools.py — Herramientas del agente
# Generado por AgentKit para Plaza de Salud Glasovi

import os
import yaml
import logging
from datetime import datetime

logger = logging.getLogger("agentkit")


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención de Plaza de Salud Glasovi."""
    info = cargar_info_negocio()
    horario_str = info.get("negocio", {}).get("horario", "No disponible")
    ahora = datetime.now()
    dia_semana = ahora.weekday()  # 0=lunes, 6=domingo
    hora_actual = ahora.hour

    # Lunes a Viernes (0-4): 9am a 7pm
    # Sábado (5): 9am a 2pm
    # Domingo (6): cerrado
    if dia_semana == 6:
        esta_abierto = False
    elif dia_semana == 5:
        esta_abierto = 9 <= hora_actual < 14
    else:
        esta_abierto = 9 <= hora_actual < 19

    return {
        "horario": horario_str,
        "esta_abierto": esta_abierto,
        "dia_actual": ahora.strftime("%A"),
    }


def buscar_en_knowledge(consulta: str) -> str:
    """
    Busca información relevante en los archivos de /knowledge.
    Retorna el contenido más relevante encontrado.
    """
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


# ════════════════════════════════════════════════════════════
# Herramientas para AGENDAR CITAS (caso de uso #2)
# ════════════════════════════════════════════════════════════

SERVICIOS_DISPONIBLES = [
    "medicina general",
    "papanicolau",
    "análisis clínicos",
    "farmacia",
    "odontología",
    "ultrasonido",
    "electrocardiograma",
    "rayos x",
]


def validar_servicio(servicio: str) -> bool:
    """Verifica si el servicio solicitado existe en la plaza."""
    servicio_lower = servicio.lower()
    return any(s in servicio_lower for s in SERVICIOS_DISPONIBLES)


def obtener_servicios_disponibles() -> list[str]:
    """Retorna la lista de servicios de Plaza de Salud Glasovi."""
    return SERVICIOS_DISPONIBLES


# ════════════════════════════════════════════════════════════
# Herramientas para CALIFICACIÓN DE LEADS (caso de uso #3)
# ════════════════════════════════════════════════════════════

def calificar_urgencia(mensaje: str) -> str:
    """
    Determina si el mensaje indica urgencia médica.
    Retorna: 'urgente', 'pronto', 'normal'
    """
    palabras_urgentes = ["emergencia", "urgente", "urgencia", "dolor fuerte", "accidente", "sangrado"]
    palabras_pronto = ["pronto", "esta semana", "hoy", "mañana", "lo antes posible"]

    mensaje_lower = mensaje.lower()

    if any(p in mensaje_lower for p in palabras_urgentes):
        return "urgente"
    elif any(p in mensaje_lower for p in palabras_pronto):
        return "pronto"
    return "normal"
