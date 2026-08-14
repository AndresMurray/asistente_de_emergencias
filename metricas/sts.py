
"""
STS - Semantic Text Similarity (métrica de Lalo)
==================================================

Evalúa la arquitectura cloud del agente LiveKit simulando la llamada remota
(llama-3.3-70b-versatile vía Groq + tool buscar_protocolo) y comparando la
respuesta generada con la respuesta esperada del dataset usando similitud
coseno de embeddings.

El modelo de embeddings es el mismo de la arquitectura cloud:
    Cohere embed-multilingual-v3.0 (1024 dims)

Uso:
    export PYTHONPATH=.
    python metricas/sts.py

Requiere un archivo .env.local con:
    GROQ_API_KEY=...
    COHERE_API_KEY=...
    DATABASE_URL=postgresql://...  (opcional, fallback a localhost:5433)

Dataset:
    DataSetRespuestasEsperadas.xlsx (raíz del repo)
    Columnas esperadas: Query, Respuesta Esperada
"""

import asyncio
import sys
import os
import json
import math
import unicodedata
from datetime import datetime
from typing import List, Optional

import aiohttp
import openpyxl
from dotenv import load_dotenv

# Directorio raíz del proyecto
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Añadir directorio raíz al path para importar agent.py
sys.path.append(PROJECT_ROOT)

# Cargar variables de entorno desde la raíz del proyecto (donde vive .env.local)
load_dotenv(os.path.join(PROJECT_ROOT, ".env.local"))

# Fallback de la base de datos local si no está definida en .env.local
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5433/emergencias_vdb"

from prompts import SYSTEM_INSTRUCTIONS
from rag import Retriever


# Un solo retriever para toda la corrida, igual que en agent.py: adentro tiene el
# pool de conexiones y no conviene abrir uno por consulta.
_retriever: Retriever | None = None


def _get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
        _retriever.connect()
    return _retriever


# ── Configuración ───────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

COHERE_API_KEY = os.getenv("COHERE_API_KEY")
COHERE_EMBED_URL = "https://api.cohere.ai/v1/embed"
EMBED_MODEL = "embed-multilingual-v3.0"

DATASET_EXCEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "DataSetRespuestasEsperadas.xlsx"
)


# ── Helpers de texto ────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    """Minúsculas y sin acentos, para un match robusto por substring."""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _load_dataset_from_excel(path: str) -> List[dict]:
    """Lee el Excel con queries y respuestas esperadas."""
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    dataset = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        query = row[0]
        expected_answer = row[1] if len(row) > 1 else ""
        if not query:
            continue
        dataset.append({
            "query": str(query).strip(),
            "expected_answer": str(expected_answer).strip(),
        })
    return dataset


# ── Llamadas a Groq (compatible con OpenAI, vía aiohttp) ────────────────────
async def _groq_chat_completion(
    messages: List[dict],
    tools: Optional[List[dict]] = None,
) -> dict:
    """Llama al endpoint de chat completions de Groq y devuelve el JSON parseado."""
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.1,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with aiohttp.ClientSession() as session:
        async with session.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
        ) as response:
            response.raise_for_status()
            return await response.json()


# ── Simulación del agente remoto (mismo patrón que critical_information_coverage)
async def ejecutar_agente_remoto(query: str) -> str:
    """
    Simula la llamada al agente remoto LiveKit ejecutando el LLM con las
    mismas instrucciones y resolviendo la llamada de herramienta `buscar_protocolo`.
    Usa Groq llama-3.3-70b-versatile.
    """
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": query},
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "buscar_protocolo",
                "description": (
                    "Busca en la base de datos vectorial los fragmentos de protocolo "
                    "semanticamente mas relevantes para la consulta del operador de emergencia vial. "
                    "Ejemplo de query: 'que hacer ante un choque con heridos'"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "La consulta de búsqueda semántica",
                        }
                    },
                    "required": ["query"],
                },
            },
        }
    ]

    try:
        response = await _groq_chat_completion(messages, tools=tools)

        response_message = response["choices"][0]["message"]
        tool_calls = response_message.get("tool_calls")

        if tool_calls:
            # Agregar el mensaje del asistente que pide llamar a la herramienta
            messages.append(response_message)

            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])

                if function_name == "buscar_protocolo":
                    search_query = function_args.get("query", query)
                    # Ejecutar la búsqueda real usando el retriever de rag/
                    result = await _get_retriever().search(search_query)
                    tool_output = result.para_llm() if result.status == "ok" else ""
                    if result.status == "error":
                        print(f"  [Error retrieval] {result.error}")

                    messages.append({
                        "tool_call_id": tool_call["id"],
                        "role": "tool",
                        "name": function_name,
                        "content": tool_output,
                    })

            # Segunda llamada al LLM enviando los resultados de la herramienta
            second_response = await _groq_chat_completion(messages)
            return second_response["choices"][0]["message"].get("content", "")

        return response_message.get("content", "")
    except Exception as e:
        print(f"  [Error LLM] Error al invocar Groq: {e}")
        return ""


# ── Embeddings con Cohere (mismo modelo de la arquitectura cloud) ───────────
async def get_cohere_embedding(text: str) -> List[float]:
    """
    Genera el embedding de un texto usando Cohere embed-multilingual-v3.0.
    Es el mismo modelo que usa la arquitectura cloud para retrieval.

    La key del proyecto es Trial (~10 llamadas/min), y cada consulta del
    dataset gasta dos embeddings (respuesta generada + esperada). El throttle
    compartido de rag/ratelimit espacia TODAS las llamadas a Cohere del proceso
    (retrieval incluido). Si igual llega un 429, se reintenta con backoff
    exponencial hasta 8 veces.
    """
    payload = {
        "texts": [text],
        "model": EMBED_MODEL,
        "input_type": "search_document",
        "embedding_types": ["float"],
    }
    headers = {
        "Authorization": f"Bearer {COHERE_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    from rag.ratelimit import esperar_turno

    async with aiohttp.ClientSession() as session:
        for attempt in range(8):
            await esperar_turno()
            async with session.post(
                COHERE_EMBED_URL, headers=headers, json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["embeddings"]["float"][0]

                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    espera = int(retry_after) if retry_after else min(2 ** attempt * 6, 60)
                    print(
                        f"  [Rate limit] 429 de Cohere, esperando {espera}s "
                        f"(intento {attempt + 1}/8)"
                    )
                    await asyncio.sleep(espera)
                    continue

                response.raise_for_status()

    raise RuntimeError("Cohere siguió devolviendo 429 después de 8 reintentos")


# ── Similitud coseno ────────────────────────────────────────────────────────
def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Similitud coseno entre dos vectores (Python puro, sin numpy)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Main ────────────────────────────────────────────────────────────────────
async def main():
    print("--- EVALUACIÓN DE STS CON AGENTE LIVEKIT SIMULADO ---")
    print(f"Modelo LLM: {GROQ_MODEL} (Groq)")
    print(f"Modelo embeddings: {EMBED_MODEL} (Cohere)")
    print("Inicializando cliente de Groq y cargando dataset...")

    if not GROQ_API_KEY:
        print("Error: No se encontró la variable de entorno GROQ_API_KEY.")
        return

    if not COHERE_API_KEY:
        print("Error: No se encontró la variable de entorno COHERE_API_KEY.")
        return

    if not os.path.exists(DATASET_EXCEL_PATH):
        print(f"Error: No se encontró el dataset en '{DATASET_EXCEL_PATH}'")
        return

    dataset = _load_dataset_from_excel(DATASET_EXCEL_PATH)
    print(f"Dataset cargado: {len(dataset)} consultas.\n")

    total_sts = 0.0
    num_queries = len(dataset)
    results = []

    for i, data in enumerate(dataset):
        query = data["query"]
        expected_answer = data["expected_answer"]

        print(f"Consulta {i + 1}: '{query}'")
        print(f"  Generando respuesta simulada con {GROQ_MODEL} y buscar_protocolo...")

        # 1) Generar respuesta con el agente simulado
        generated_answer = await ejecutar_agente_remoto(query)

        if not generated_answer:
            print("  [Advertencia] Respuesta vacía, STS = 0.0\n")
            sts = 0.0
        else:
            # 2) Embeddear respuesta generada y esperada
            print("  Calculando embeddings con Cohere...")
            gen_emb, exp_emb = await asyncio.gather(
                get_cohere_embedding(generated_answer),
                get_cohere_embedding(expected_answer),
            )

            # 3) Calcular similitud coseno
            sts = cosine_similarity(gen_emb, exp_emb)
            print(f"  STS = {sts:.4f}\n")

        total_sts += sts

        results.append({
            "query_id": i + 1,
            "query": query,
            "expected_answer": expected_answer,
            "generated_answer": generated_answer,
            "sts": sts,
        })

    avg_sts = total_sts / num_queries if num_queries else 0.0
    print("=" * 60)
    print(f"STS global (promedio): {avg_sts:.4f}")
    print("=" * 60)

    # Guardar resultados
    output_dir = os.path.join(os.path.dirname(__file__), "resultados")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"resultados_sts_{timestamp}.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "fase": "Evaluación Agente LiveKit Simulado - STS",
            "metrica": "Semantic Text Similarity",
            "modelo_llm": GROQ_MODEL,
            "modelo_embeddings": f"cohere {EMBED_MODEL}",
            "sts_global": avg_sts,
            "num_consultas": num_queries,
            "resultados_detallados": results,
        }, f, indent=4, ensure_ascii=False)

    print(f"\nResultados guardados en '{output_file}'")

    if _retriever is not None:
        _retriever.close()


if __name__ == "__main__":
    asyncio.run(main())
