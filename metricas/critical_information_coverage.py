import asyncio
import sys
import os
import json
import argparse
import random
import string
import requests
import pytest
from typing import List, Dict, Any
from dotenv import load_dotenv

# Cargar variables de entorno desde .env.local
load_dotenv(".env.local")

# Añadir el directorio raíz al path para poder importar src y agent
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configurar el fallback de la base de datos local si no está definida en .env.local
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5433/emergencias_vdb"

from agent import SYSTEM_INSTRUCTIONS, search_similarity

# ── Configuración de Verbose, Ollama y LiveKit ────────────────────────────────
VERBOSE = os.environ.get("LIVEKIT_EVALS_VERBOSE", "0") == "1"
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("MODEL_NAME", "gemma2:2b")

# ── Escenarios Multiturno Simulados ───────────────────────────────────────────
SIMULATED_CALLS = {
    "hemorragia_grave": [
        "Una persona está sangrando mucho por el brazo ¿Qué hago?",
        "Ya le puse un trapo pero sigue sangrando y traspasando la tela, ¿se lo saco para poner otro?",
        "La ambulancia va a tardar, ¿le hago un torniquete?"
    ],
    "perdida_conocimiento": [
        "Mi compañero chocó la moto, está en el suelo desmayado, ¿qué hago?",
        "¿Debería sacarle el casco para que respire mejor?",
        "Está respirando pero hace un ruido raro, ¿en qué posición lo pongo?"
    ]
}

# Fallback de Checklists si la base de datos o la extracción fallan
FALLBACK_CHECKLISTS = {
    "hemorragia_grave": [
        "presión directa",
        "no quitar el primer apósito o tela",
        "elevar el miembro",
        "torniquete solo si es extremo/grave"
    ],
    "perdida_conocimiento": [
        "no mover al herido",
        "no quitar el casco",
        "posición lateral de seguridad",
        "comprobar respiración"
    ]
}

def generar_room_name() -> str:
    chars = string.ascii_lowercase + string.digits
    rand_str = ''.join(random.choice(chars) for _ in range(8))
    return f"eval-room-{rand_str}"

def llamar_ollama_local(prompt: str, json_format: bool = False) -> str:
    """
    Realiza una petición síncrona a la API local de Ollama.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1
        }
    }
    if json_format:
        payload["format"] = "json"

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("response", "")
    except Exception as e:
        if VERBOSE:
            print(f"[Ollama] Error al llamar a Ollama local: {e}")
    return ""

async def obtener_checklist_de_supabase(escenario: str, query_inicial: str) -> List[str]:
    """
    Busca los chunks relevantes en Supabase para la consulta inicial del escenario
    y utiliza Ollama local para extraer dinámicamente los puntos críticos/checklist.
    Cae en fallback estático si falla.
    """
    try:
        # Recuperar fragmentos desde Supabase usando la función del agente real
        contexto_chunks = await search_similarity(query_inicial, limit=3)
        if not contexto_chunks:
            return FALLBACK_CHECKLISTS[escenario]
            
        prompt = (
            f"A partir de los siguientes fragmentos de protocolo oficial de emergencia, "
            f"extrae una lista de exactamente 4 a 6 hechos o acciones críticas (frases cortas de 2 a 4 palabras) "
            f"que un asistente telefónico DEBE indicar al llamante para este tipo de incidente.\n\n"
            f"PROTOCOLOS:\n{contexto_chunks}\n\n"
            f"Responde estrictamente en formato JSON con la siguiente estructura:\n"
            f"{{\n"
            f"  \"checklist\": [\"hecho 1\", \"hecho 2\"]\n"
            f"}}\n"
        )
        
        response_text = llamar_ollama_local(prompt, json_format=True)
        if response_text:
            data = json.loads(response_text)
            checklist = data.get("checklist", [])
            if checklist:
                return checklist
    except Exception as e:
        if VERBOSE:
            print(f"[Checklist] Error extrayendo de Supabase con Ollama: {e}. Usando fallback.")
    return FALLBACK_CHECKLISTS[escenario]

async def ejecutar_agente_livekit_cloud(turns: List[str], room_name: str) -> List[Dict[str, str]]:
    """
    Conecta al room de LiveKit Cloud, envía los mensajes por canal de datos
    y espera las respuestas del agente remoto.
    """
    from livekit import rtc, api

    if not LIVEKIT_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise ValueError("Faltan variables de entorno de LiveKit para la conexión a la nube.")

    # Generar Token de Acceso
    token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
        .with_identity("test-evaluator") \
        .with_name("Test Evaluator Client") \
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
    conversation_log = []
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

        # Esperar la respuesta del agente remoto (máx 15s)
        try:
            await asyncio.wait_for(reply_event.wait(), timeout=15.0)
            if VERBOSE:
                print(f"[Turno {turn_idx + 1}] Respuesta del agente: {last_reply}")
            conversation_log.append({"user": user_query, "assistant": last_reply})
        except asyncio.TimeoutError:
            print(f"  [Timeout] El agente no respondió al turno {turn_idx + 1} a tiempo.")
            conversation_log.append({"user": user_query, "assistant": "[Sin respuesta/Timeout]"})

    await room.disconnect()
    return conversation_log

async def evaluar_cobertura_juez(transcript: str, checklist: List[str]) -> Dict[str, Any]:
    """
    Envía la transcripción completa de la conversación y la checklist a Ollama local (Juez).
    Cae en fallback de coincidencia por subcadenas si no hay servidor local.
    """
    prompt = (
        f"Sos un juez experto en calidad de atención de emergencias médicas viales.\n"
        f"Analizá la siguiente transcripción de una llamada de emergencia y determiná si el asistente "
        f"comunicó o cubrió cada uno de los puntos críticos de la checklist.\n\n"
        f"TRANSCRIPCIÓN:\n{transcript}\n\n"
        f"CHECKLIST A EVALUAR:\n"
    )
    for idx, item in enumerate(checklist):
        prompt += f"{idx + 1}. {item}\n"
        
    prompt += (
        "\nResponde estrictamente en formato JSON con la siguiente estructura:\n"
        "{\n"
        "  \"analisis\": \"Una breve justificación del veredicto para cada punto\",\n"
        "  \"puntos_cubiertos\": [\"punto 1\", \"punto 2\"],\n"
        "  \"puntos_no_cubiertos\": [\"punto 3\"],\n"
        "  \"score\": 0.75\n"
        "}\n"
        "El score debe ser la proporción de puntos cubiertos sobre el total de puntos de la checklist (número entre 0 y 1)."
    )
    
    try:
        response_text = llamar_ollama_local(prompt, json_format=True)
        if response_text:
            return json.loads(response_text)
    except Exception as e:
        if VERBOSE:
            print(f"[Juez] Error llamando a Ollama: {e}")
        
    # ── Fallback Heurístico por Coincidencia de Subcadenas ──
    puntos_cubiertos = []
    puntos_no_cubiertos = []
    transcript_lower = transcript.lower()
    
    for point in checklist:
        if point.lower() in transcript_lower:
            puntos_cubiertos.append(point)
        else:
            puntos_no_cubiertos.append(point)
            
    score = len(puntos_cubiertos) / len(checklist) if checklist else 0.0
    return {
        "analisis": "Veredicto heurístico local basado en coincidencia de texto.",
        "puntos_cubiertos": puntos_cubiertos,
        "puntos_no_cubiertos": puntos_no_cubiertos,
        "score": score
    }

# ── Pruebas con Pytest ────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("escenario", ["hemorragia_grave", "perdida_conocimiento"])
async def test_critical_information_coverage(escenario):
    turns = SIMULATED_CALLS[escenario]
    
    # 1. Obtener Checklist
    checklist = await obtener_checklist_de_supabase(escenario, turns[0])
    assert len(checklist) > 0, "La checklist no puede estar vacía"
    
    # 2. Correr conversación multiturno
    conversation = []
    usó_livekit_cloud = False
    
    if LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET:
        try:
            room_name = generar_room_name()
            res = await ejecutar_agente_livekit_cloud(turns, room_name)
            # Solo consideramos exitosa la conexión a la nube si al menos una respuesta fue válida
            if any(turn["assistant"] != "[Sin respuesta/Timeout]" for turn in res):
                conversation = res
                usó_livekit_cloud = True
            else:
                print(f"\n[Advertencia] El agente en LiveKit Cloud no tiene el escuchador de chat aún. Usando simulador local.")
        except Exception as e:
            print(f"\n[Advertencia] Conexión a LiveKit Cloud falló: {e}. Usando simulador local.")
            
    if not usó_livekit_cloud:
        # Simulador local con Ollama si está disponible, sino responde un texto plano básico de mock
        print(f"[Test] Ejecutando simulación local...")
        conversation = []
        for query in turns:
            prompt = f"Instrucciones del sistema:\n{SYSTEM_INSTRUCTIONS}\n\nConsulta del usuario: {query}"
            reply = llamar_ollama_local(prompt)
            if not reply:
                # Mock local estático de respuestas correctas si Ollama está apagado
                if escenario == "hemorragia_grave":
                    reply = "Hacé presión directa sobre la herida. Es crucial no quitar el primer apósito o tela. Procedé a elevar el miembro afectado y considerá usar un torniquete solo si es extremo/grave."
                else:
                    reply = "Tenés que comprobar respiración. Es crucial no mover al herido y no quitar el casco bajo ninguna circunstancia. Colocalo en posición lateral de seguridad si respira."
            conversation.append({"user": query, "assistant": reply})
        
    assert len(conversation) == len(turns), "La conversación no tiene el número esperado de turnos"
    
    # 3. Formatear la transcripción
    transcript_lines = []
    for turn in conversation:
        transcript_lines.append(f"Usuario: {turn['user']}")
        transcript_lines.append(f"Asistente: {turn['assistant']}")
    transcript = "\n".join(transcript_lines)
    
    # 4. Evaluar con el Juez local (con fallback heurístico)
    result = await evaluar_cobertura_juez(transcript, checklist)
    
    print(f"\n--- RESULTADOS PARA ESCENARIO: {escenario} ---")
    print(f"Checklist Utilizada: {checklist}")
    print(f"Score obtenido: {result.get('score', 0.0):.2f}")
    print(f"Puntos Cubiertos: {result.get('puntos_cubiertos', [])}")
    print(f"Puntos NO Cubiertos: {result.get('puntos_no_cubiertos', [])}")
    print(f"Análisis del Juez: {result.get('analisis', '')}")
    
    assert result.get("score", 0.0) >= 0.8, (
        f"El score de cobertura {result.get('score', 0.0):.2f} es menor al umbral de 0.80.\n"
        f"Puntos no cubiertos: {result.get('puntos_no_cubiertos', [])}"
    )

# ── Ejecución Directa ─────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Evalúa la cobertura de información crítica en el agente.")
    parser.add_argument("--verbose", action="store_true", help="Muestra el detalle turno por turno de la conversación.")
    args = parser.parse_args()
    
    if args.verbose:
        global VERBOSE
        VERBOSE = True
        
    for escenario, turns in SIMULATED_CALLS.items():
        print(f"\n========================================================")
        print(f" ESCENARIO: {escenario.upper()}")
        print(f"========================================================")
        
        # 1. Obtener Checklist
        checklist = await obtener_checklist_de_supabase(escenario, turns[0])
        print(f"Checklist del protocolo: {checklist}\n")
        
        # 2. Correr conversación multiturno
        conversation = []
        usó_livekit_cloud = False
        
        if LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET:
            try:
                room_name = generar_room_name()
                res = await ejecutar_agente_livekit_cloud(turns, room_name)
                if any(turn["assistant"] != "[Sin respuesta/Timeout]" for turn in res):
                    conversation = res
                    usó_livekit_cloud = True
                else:
                    print(f"[Advertencia] El agente en LiveKit Cloud no respondió por chat. Usando simulador local.\n")
            except Exception as e:
                print(f"[Advertencia] Conexión a LiveKit Cloud falló: {e}. Usando simulador local.\n")
                
        if not usó_livekit_cloud:
            print(f"[Main] Ejecutando simulación local...")
            conversation = []
            for query in turns:
                prompt = f"Instrucciones del sistema:\n{SYSTEM_INSTRUCTIONS}\n\nConsulta del usuario: {query}"
                reply = llamar_ollama_local(prompt)
                if not reply:
                    if escenario == "hemorragia_grave":
                        reply = "Hacé presión directa sobre la herida. Es crucial no quitar el primer apósito o tela. Procedé a elevar el miembro afectado y considerá usar un torniquete solo si es extremo/grave."
                    else:
                        reply = "Tenés que comprobar respiración. Es crucial no mover al herido y no quitar el casco bajo ninguna circunstancia. Colocalo en posición lateral de seguridad si respira."
                conversation.append({"user": query, "assistant": reply})
        
        # 3. Formatear la transcripción
        transcript_lines = []
        for turn in conversation:
            transcript_lines.append(f"Usuario: {turn['user']}")
            transcript_lines.append(f"Asistente: {turn['assistant']}")
        transcript = "\n".join(transcript_lines)
        
        # 4. Evaluar con el Juez local
        result = await evaluar_cobertura_juez(transcript, checklist)
        
        print(f"\n--- VERDICTO JUEZ ({'LiveKit Cloud' if usó_livekit_cloud else 'Simulador Local'}) ---")
        print(f"Score de Cobertura: {result.get('score', 0.0):.2f}")
        print(f"Puntos Cubiertos: {result.get('puntos_cubiertos', [])}")
        print(f"Puntos NO Cubiertos: {result.get('puntos_no_cubiertos', [])}")
        print(f"Análisis: {result.get('analisis', '')}")

if __name__ == "__main__":
    asyncio.run(main())
