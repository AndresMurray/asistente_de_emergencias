import asyncio
import json
import os
import random
import string
from typing import List, Dict, Any

from dotenv import load_dotenv
from livekit import rtc, api

# Cargar variables de entorno desde .env.local (raíz del repo)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env.local'))

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

VERBOSE = os.environ.get("LIVEKIT_EVALS_VERBOSE", "0") == "1"


def generar_room_name() -> str:
    chars = string.ascii_lowercase + string.digits
    rand_str = ''.join(random.choice(chars) for _ in range(8))
    return f"eval-room-{rand_str}"


async def ejecutar_agente_livekit_cloud(turns: List[str], room_name: str = None) -> List[Dict[str, str]]:
    """
    Conecta al room de LiveKit Cloud, envía los mensajes por canal de datos
    y espera las respuestas del agente remoto (sistema RAG real desplegado).

    Retorna una lista de {"user": ..., "assistant": ...}. Si un turno no
    obtiene respuesta a tiempo, registra "[Sin respuesta/Timeout]".
    """
    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise ValueError("Faltan variables de entorno LiveKit (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) en .env.local.")

    room_name = room_name or generar_room_name()

    # Generar Token de Acceso
    token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
        .with_identity(f"metricas-eval-{random.randint(1000, 9999)}") \
        .with_name("Metricas Evaluator Client") \
        .with_grants(api.VideoGrants(room_join=True, room=room_name)) \
        .to_jwt()

    room = rtc.Room()
    print(f"[LiveKit Cloud] Conectando a la sala '{room_name}'...")
    await room.connect(LIVEKIT_URL, token)

    print("[LiveKit Cloud] Esperando a que el agente se una a la sala (máx 20s)...")
    agent_joined = False
    for _ in range(20):
        if len(room.remote_participants) > 0:
            agent_joined = True
            break
        await asyncio.sleep(1)

    if not agent_joined:
        await room.disconnect()
        raise TimeoutError("El agente remoto no se unió a la sala a tiempo.")

    print("[LiveKit Cloud] Agente conectado. Iniciando conversación...")
    conversation_log: List[Dict[str, str]] = []
    reply_event = asyncio.Event()
    last_reply = ""

    @room.on("data_received")
    def on_data_received(data_packet: rtc.DataPacket):
        nonlocal last_reply
        try:
            payload = json.loads(data_packet.data.decode('utf-8'))
            if payload.get("type") == "chat_reply":
                last_reply = payload.get("message", "")
                reply_event.set()
        except Exception as e:
            if VERBOSE:
                print(f"[LiveKit Cloud] Error decodificando respuesta: {e}")

    for turn_idx, user_query in enumerate(turns):
        reply_event.clear()

        if VERBOSE:
            print(f"\n[Turno {turn_idx + 1}] Enviando al chat: {user_query}")

        # Enviar consulta por el canal de datos
        await room.local_participant.publish_data(
            payload=json.dumps({"type": "chat", "message": user_query}).encode('utf-8'),
            topic="test-chat"
        )

        # Esperar la respuesta del agente remoto (máx 45s)
        try:
            await asyncio.wait_for(reply_event.wait(), timeout=45.0)
            if VERBOSE:
                print(f"[Turno {turn_idx + 1}] Respuesta del agente: {last_reply}")
            conversation_log.append({"user": user_query, "assistant": last_reply})
        except asyncio.TimeoutError:
            print(f"  [Timeout] El agente no respondió al turno {turn_idx + 1} a tiempo.")
            conversation_log.append({"user": user_query, "assistant": "[Sin respuesta/Timeout]"})

    await room.disconnect()
    return conversation_log


async def obtener_respuesta_agente_livekit(query: str) -> str:
    """
    Envía una única consulta al agente real de LiveKit y devuelve la respuesta.
    Retorna "ERROR_GENERATION" si el turno dio timeout.
    """
    conversation = await ejecutar_agente_livekit_cloud([query])
    if not conversation:
        return "ERROR_GENERATION"
    reply = conversation[0]["assistant"]
    if reply == "[Sin respuesta/Timeout]":
        return "ERROR_GENERATION"
    return reply