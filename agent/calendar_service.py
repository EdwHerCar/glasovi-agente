# agent/calendar_service.py — Integración con Google Calendar
# Generado por AgentKit para Plaza de Salud Glasovi

"""
Funciones para crear y consultar citas en Google Calendar.
Usa una cuenta de servicio de Google Cloud para autenticarse.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("agentkit")

CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "plazaglasovi@gmail.com")
TIMEZONE = "America/Mexico_City"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Horario de atención (lunes-viernes 9-19, sábado 9-14)
HORARIO = {
    0: (9, 19),  # lunes
    1: (9, 19),  # martes
    2: (9, 19),  # miércoles
    3: (9, 19),  # jueves
    4: (9, 19),  # viernes
    5: (9, 14),  # sábado
    6: None,     # domingo — cerrado
}


def _obtener_servicio():
    """Crea el cliente de Google Calendar API usando la cuenta de servicio."""
    credenciales_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not credenciales_json:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON no configurado en .env")

    info = json.loads(credenciales_json)
    credenciales = service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=credenciales)


def verificar_disponibilidad(fecha: str, hora: str, duracion_minutos: int = 30) -> dict:
    """
    Verifica si un slot está disponible en Google Calendar.

    Args:
        fecha: Fecha en formato YYYY-MM-DD (ej: "2026-06-05")
        hora: Hora en formato HH:MM (ej: "10:00")
        duracion_minutos: Duración de la cita en minutos (default: 30)

    Returns:
        {"disponible": bool, "mensaje": str}
    """
    try:
        tz = ZoneInfo(TIMEZONE)
        inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        fin = inicio + timedelta(minutes=duracion_minutos)

        # Verificar que esté en horario de atención
        dia_semana = inicio.weekday()
        horario_dia = HORARIO.get(dia_semana)

        if horario_dia is None:
            return {"disponible": False, "mensaje": "Los domingos estamos cerrados."}

        hora_apertura, hora_cierre = horario_dia
        if inicio.hour < hora_apertura or fin.hour > hora_cierre or (fin.hour == hora_cierre and fin.minute > 0):
            return {
                "disponible": False,
                "mensaje": f"Ese horario está fuera de nuestra atención. {'Sábados atendemos de 9:00am a 2:00pm.' if dia_semana == 5 else 'De lunes a viernes atendemos de 9:00am a 7:00pm.'}"
            }

        # Verificar que no caiga en horario de comida del doctor (4:00pm a 5:30pm)
        comida_inicio = inicio.replace(hour=16, minute=0, second=0, microsecond=0)
        comida_fin = inicio.replace(hour=17, minute=30, second=0, microsecond=0)
        if inicio < comida_fin and fin > comida_inicio:
            return {
                "disponible": False,
                "mensaje": "El horario de 4:00pm a 5:30pm está reservado. ¿Le ofrezco un horario antes de las 4:00pm o a partir de las 5:30pm?"
            }

        servicio = _obtener_servicio()

        # Consultar eventos existentes en ese slot
        eventos = servicio.events().list(
            calendarId=CALENDAR_ID,
            timeMin=inicio.isoformat(),
            timeMax=fin.isoformat(),
            singleEvents=True,
        ).execute()

        if eventos.get("items"):
            return {"disponible": False, "mensaje": f"El horario {hora} del {fecha} ya está ocupado. ¿Le ofrezco otro?"}

        return {"disponible": True, "mensaje": f"El horario {hora} del {fecha} está disponible."}

    except Exception as e:
        logger.error(f"Error verificando disponibilidad: {e}")
        return {"disponible": False, "mensaje": "No pude verificar la disponibilidad en este momento."}


def crear_cita(nombre: str, telefono: str, servicio: str, fecha: str, hora: str, duracion_minutos: int = 30) -> dict:
    """
    Crea una cita en Google Calendar.

    Args:
        nombre: Nombre completo del paciente
        telefono: Número de WhatsApp del paciente
        servicio: Servicio médico solicitado
        fecha: Fecha en formato YYYY-MM-DD
        hora: Hora en formato HH:MM
        duracion_minutos: Duración en minutos (default: 30)

    Returns:
        {"exito": bool, "mensaje": str, "evento_id": str | None}
    """
    try:
        tz = ZoneInfo(TIMEZONE)
        inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        fin = inicio + timedelta(minutes=duracion_minutos)

        # Verificar disponibilidad antes de crear
        disponibilidad = verificar_disponibilidad(fecha, hora, duracion_minutos)
        if not disponibilidad["disponible"]:
            return {"exito": False, "mensaje": disponibilidad["mensaje"], "evento_id": None}

        servicio_calendar = _obtener_servicio()

        evento = {
            "summary": f"Cita: {servicio.title()} — {nombre}",
            "description": f"Paciente: {nombre}\nTeléfono: {telefono}\nServicio: {servicio}\nAgendado via WhatsApp (Glasovi)",
            "start": {"dateTime": inicio.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": fin.isoformat(), "timeZone": TIMEZONE},
            "colorId": "2",  # Verde (Sage)
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 30},
                    {"method": "email", "minutes": 60},
                ],
            },
        }

        resultado = servicio_calendar.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        evento_id = resultado.get("id", "")

        logger.info(f"Cita creada: {nombre} — {servicio} — {fecha} {hora}")
        return {
            "exito": True,
            "mensaje": f"Cita confirmada para {nombre} el {_formato_fecha(fecha)} a las {hora} para {servicio}.",
            "evento_id": evento_id,
        }

    except HttpError as e:
        logger.error(f"Error Google Calendar API: {e}")
        return {"exito": False, "mensaje": "No pude registrar la cita en el calendario. Por favor intenta de nuevo.", "evento_id": None}
    except Exception as e:
        logger.error(f"Error creando cita: {e}")
        return {"exito": False, "mensaje": "Ocurrió un error al agendar la cita.", "evento_id": None}


def listar_citas_proximas(dias: int = 7) -> list[dict]:
    """
    Lista las citas agendadas en los próximos N días.

    Args:
        dias: Cuántos días hacia adelante buscar

    Returns:
        Lista de citas con summary, start, end
    """
    try:
        tz = ZoneInfo(TIMEZONE)
        ahora = datetime.now(tz)
        fin = ahora + timedelta(days=dias)

        servicio = _obtener_servicio()
        eventos = servicio.events().list(
            calendarId=CALENDAR_ID,
            timeMin=ahora.isoformat(),
            timeMax=fin.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        citas = []
        for e in eventos.get("items", []):
            start = e.get("start", {}).get("dateTime", "")
            citas.append({
                "titulo": e.get("summary", ""),
                "inicio": start,
                "descripcion": e.get("description", ""),
            })
        return citas

    except Exception as e:
        logger.error(f"Error listando citas: {e}")
        return []


def _formato_fecha(fecha: str) -> str:
    """Convierte YYYY-MM-DD a formato legible en español."""
    try:
        dt = datetime.strptime(fecha, "%Y-%m-%d")
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        return f"{dias[dt.weekday()]} {dt.day} de {meses[dt.month - 1]}"
    except Exception:
        return fecha
