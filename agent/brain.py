# agent/brain.py — Cerebro del agente: conexión con Claude API + tool use
# Generado por AgentKit para Plaza de Salud Glasovi

import os
import json
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Herramientas que Claude puede invocar durante la conversación
TOOLS = [
    {
        "name": "verificar_disponibilidad",
        "description": "Verifica si un horario está disponible en el calendario de Plaza de Salud Glasovi antes de confirmar una cita.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha de la cita en formato YYYY-MM-DD. Ej: '2026-06-10'"
                },
                "hora": {
                    "type": "string",
                    "description": "Hora de la cita en formato HH:MM. Ej: '10:00'"
                },
                "duracion_minutos": {
                    "type": "integer",
                    "description": "Duración de la cita en minutos. Default: 30",
                    "default": 30
                }
            },
            "required": ["fecha", "hora"]
        }
    },
    {
        "name": "crear_cita",
        "description": "Crea una cita confirmada en Google Calendar de Plaza de Salud Glasovi. Solo llamar cuando ya tienes nombre, servicio, fecha y hora confirmados con el paciente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre completo del paciente"
                },
                "telefono": {
                    "type": "string",
                    "description": "Número de WhatsApp del paciente"
                },
                "servicio": {
                    "type": "string",
                    "description": "Servicio médico solicitado. Ej: 'Medicina general', 'Odontología', 'Análisis clínicos'"
                },
                "fecha": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD"
                },
                "hora": {
                    "type": "string",
                    "description": "Hora en formato HH:MM"
                },
                "duracion_minutos": {
                    "type": "integer",
                    "description": "Duración en minutos. Default: 30",
                    "default": 30
                }
            },
            "required": ["nombre", "telefono", "servicio", "fecha", "hora"]
        }
    }
]


def _ejecutar_herramienta(nombre: str, parametros: dict) -> str:
    """Ejecuta la herramienta solicitada por Claude y retorna el resultado como string."""
    try:
        if nombre == "verificar_disponibilidad":
            from agent.calendar_service import verificar_disponibilidad
            resultado = verificar_disponibilidad(
                fecha=parametros["fecha"],
                hora=parametros["hora"],
                duracion_minutos=parametros.get("duracion_minutos", 30)
            )
        elif nombre == "crear_cita":
            from agent.calendar_service import crear_cita
            resultado = crear_cita(
                nombre=parametros["nombre"],
                telefono=parametros["telefono"],
                servicio=parametros["servicio"],
                fecha=parametros["fecha"],
                hora=parametros["hora"],
                duracion_minutos=parametros.get("duracion_minutos", 30)
            )
        else:
            resultado = {"error": f"Herramienta desconocida: {nombre}"}

        return json.dumps(resultado, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error ejecutando herramienta {nombre}: {e}")
        return json.dumps({"error": str(e)})


def cargar_config_prompts() -> dict:
    """Lee toda la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    config = cargar_config_prompts()
    return config.get("system_prompt", "Eres un asistente útil. Responde en español.")


def obtener_mensaje_error() -> str:
    config = cargar_config_prompts()
    return config.get("error_message", "Lo sentimos, estamos experimentando dificultades técnicas.")


def obtener_mensaje_fallback() -> str:
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpe, no pude entender su mensaje. ¿Podría reformularlo?")


async def generar_respuesta(mensaje: str, historial: list[dict], telefono: str = "") -> str:
    """
    Genera una respuesta usando Claude API con tool use para Google Calendar.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores
        telefono: Número del paciente (para crear citas)

    Returns:
        La respuesta generada por Claude
    """
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt()

    mensajes = [*historial, {"role": "user", "content": mensaje}]

    try:
        # Agentic loop: Claude puede llamar herramientas múltiples veces
        while True:
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_prompt,
                tools=TOOLS,
                messages=mensajes
            )

            logger.info(f"Respuesta ({response.usage.input_tokens} in / {response.usage.output_tokens} out) — stop: {response.stop_reason}")

            # Si Claude terminó de responder (sin tool use), retornar el texto
            if response.stop_reason == "end_turn":
                texto = next(
                    (block.text for block in response.content if hasattr(block, "text")),
                    obtener_mensaje_fallback()
                )
                return texto

            # Si Claude quiere usar una herramienta
            if response.stop_reason == "tool_use":
                # Agregar la respuesta de Claude (con tool_use) al historial
                mensajes.append({"role": "assistant", "content": response.content})

                # Ejecutar cada herramienta solicitada
                resultados_herramientas = []
                for block in response.content:
                    if block.type == "tool_use":
                        # Inyectar el teléfono del paciente si la herramienta lo necesita
                        parametros = dict(block.input)
                        if block.name == "crear_cita" and telefono and "telefono" not in parametros:
                            parametros["telefono"] = telefono

                        logger.info(f"Ejecutando herramienta: {block.name}({parametros})")
                        resultado = _ejecutar_herramienta(block.name, parametros)

                        resultados_herramientas.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": resultado,
                        })

                # Agregar resultados al historial y continuar el loop
                mensajes.append({"role": "user", "content": resultados_herramientas})
                continue

            # Stop reason inesperado
            break

        return obtener_mensaje_fallback()

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()
