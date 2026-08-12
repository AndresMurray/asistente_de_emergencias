import asyncio
import datetime
import sys
import os
import json
import argparse
import random
import string
import requests
import pytest
import re
from typing import List, Dict, Any
from dotenv import load_dotenv
from livekit import rtc, api

# Cargar variables de entorno desde .env.local
load_dotenv(".env.local")

# Añadir el directorio raíz al path para poder importar agent
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Configurar el fallback de la base de datos local si no está definida en .env.local
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5433/emergencias_vdb"

from agent import SYSTEM_INSTRUCTIONS, search_similarity

# ── Configuración de Verbose y LiveKit ────────────────────────────────
VERBOSE = os.environ.get("LIVEKIT_EVALS_VERBOSE", "0") == "1"
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")


# ── Escenarios Multiturno Simulados (Cargados desde test_scenarios.json) ──────
def cargar_escenarios() -> dict:
    ruta_json = os.path.join(os.path.dirname(__file__), "test_scenarios.json")
    with open(ruta_json, "r", encoding="utf-8") as f:
        return json.load(f)

ESCENARIOS = cargar_escenarios()
SIMULATED_CALLS = {k: v["turns"] for k, v in ESCENARIOS.items()}
FALLBACK_CHECKLISTS = {k: v["fallback_checklist"] for k, v in ESCENARIOS.items()}

RUN_TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")



def generar_room_name() -> str:
    chars = string.ascii_lowercase + string.digits
    rand_str = ''.join(random.choice(chars) for _ in range(8))
    return f"eval-room-{rand_str}"

def limpiar_json(text: str) -> str:
    """
    Limpia los bloques de código markdown de un string de JSON si están presentes
    y remueve comas sobrantes al final de arrays u objetos.
    """
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    # Eliminar comas finales inválidas en JSON
    text = re.sub(r',\s*([\]}])', r'\1', text)
    return text.strip()



def llamar_llm(prompt: str, json_format: bool = False) -> str:
    """
    Realiza una petición síncrona a la API de Gemini (gemini-3.5-flash).
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("Falta la variable de entorno GEMINI_API_KEY para ejecutar la evaluación con Gemini.")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    if json_format:
        payload["generationConfig"] = {
            "responseMimeType": "application/json"
        }
        
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            res_data = response.json()
            return res_data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            print(f"\n[Gemini] Error API Gemini: Código {response.status_code} - {response.text}")
    except Exception as e:
        print(f"\n[Gemini] Error de conexión al llamar a Gemini: {e}")
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
        
        response_text = llamar_llm(prompt, json_format=True)
        if response_text:
            data = json.loads(limpiar_json(response_text))
            checklist = data.get("checklist", [])
            if checklist:
                return checklist
    except Exception as e:
        print(f"\n[Checklist] Error extrayendo de Supabase o decodificando JSON: {e}. Usando fallback.")
    return FALLBACK_CHECKLISTS[escenario]

async def ejecutar_agente_livekit_cloud(turns: List[str], room_name: str) -> List[Dict[str, str]]:
    """
    Conecta al room de LiveKit Cloud, envía los mensajes por canal de datos
    y espera las respuestas del agente remoto.
    """
    

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

        # Esperar la respuesta del agente remoto (máx 30s)
        try:
            await asyncio.wait_for(reply_event.wait(), timeout=30.0)
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
        response_text = llamar_llm(prompt, json_format=True)
        if response_text:
            return json.loads(limpiar_json(response_text))
    except Exception as e:
        print(f"\n[Juez] Error al procesar respuesta del LLM Juez o decodificar JSON: {e}")
        
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

def guardar_resultado(escenario: str, transcript: str, checklist: List[str], result: Dict[str, Any]) -> str:
    directorio_resultados = os.path.join(os.path.dirname(__file__), "resultados")
    os.makedirs(directorio_resultados, exist_ok=True)
    
    nombre_archivo = f"resultado_run_{RUN_TIMESTAMP}.json"
    ruta_archivo = os.path.join(directorio_resultados, nombre_archivo)
    
    # Cargar datos existentes si el archivo ya fue creado en esta sesión
    datos_run = {
        "fecha_ejecucion": datetime.datetime.now().isoformat(),
        "resultados": {}
    }
    
    if os.path.exists(ruta_archivo):
        try:
            with open(ruta_archivo, "r", encoding="utf-8") as f:
                datos_run = json.load(f)
        except Exception:
            pass
            
    # Añadir o actualizar el resultado de este escenario específico
    datos_run["resultados"][escenario] = {
        "checklist": checklist,
        "transcript": transcript,
        "score": result.get("score", 0.0),
        "puntos_cubiertos": result.get("puntos_cubiertos", []),
        "puntos_no_cubiertos": result.get("puntos_no_cubiertos", []),
        "analisis_juez": result.get("analisis", "")
    }
    
    with open(ruta_archivo, "w", encoding="utf-8") as f:
        json.dump(datos_run, f, ensure_ascii=False, indent=2)
    return os.path.relpath(ruta_archivo, start=os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))



# ── Ejecución Directa ─────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Evalúa la cobertura de información crítica en el agente.")
    parser.add_argument("--verbose", action="store_true", help="Muestra el detalle turno por turno de la conversación.")
    args = parser.parse_args()
    
    if args.verbose:
        global VERBOSE
        VERBOSE = True
        
    for escenario, turns in SIMULATED_CALLS.items():
        # 1. Obtener Checklist
        checklist = await obtener_checklist_de_supabase(escenario, turns[0])
        
        # 2. Correr conversación multiturno
        if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
            raise ValueError(
                "Faltan credenciales de LiveKit Cloud (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) "
                "en .env.local para ejecutar la evaluación en la nube."
            )
            
        room_name = generar_room_name()
        conversation = await ejecutar_agente_livekit_cloud(turns, room_name)
        
        # Verificar que el agente haya respondido a todos los turnos
        for turn in conversation:
            if turn["assistant"] == "[Sin respuesta/Timeout]":
                raise RuntimeError(f"El agente en la nube no respondió o dio timeout en el turno: '{turn['user']}'")
        
        # 3. Formatear la transcripción
        transcript_lines = []
        for turn in conversation:
            transcript_lines.append(f"Usuario: {turn['user']}")
            transcript_lines.append(f"Asistente: {turn['assistant']}")
        transcript = "\n".join(transcript_lines)
        
        # 4. Evaluar con el Juez local
        result = await evaluar_cobertura_juez(transcript, checklist)
        
        # Guardar en archivo
        ruta_relativa = guardar_resultado(escenario, transcript, checklist, result)
        
        score = result.get("score", 0.0)
        veredicto = "PASSED" if score >= 0.8 else "FAILED"
        
        print(f"\n========================================================")
        print(f" ESCENARIO: {escenario.upper()} ({veredicto})")
        print(f"========================================================")
        print(f"- Score obtenido: {score:.2f} (Umbral >= 0.80)")
        print(f"- Puntos cubiertos: {len(result.get('puntos_cubiertos', []))}/{len(checklist)}")
        print(f"- Reporte guardado en: {ruta_relativa}")
        print(f"========================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
