import asyncio
import math
import os
from typing import List

import aiohttp
import pandas as pd
import numpy as np

# Importar la función ask del script ask_livekit.py
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env.local", override=True)

COHERE_EMBED_URL = "https://api.cohere.ai/v1/embed"
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
EMBED_MODEL = "embed-multilingual-v3.0"
#Funciones
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

# Agregar el root del proyecto a sys.path para poder importar ask_livekit
# cuando este script se corre desde metricas/.
sys.path.insert(0, str(Path(__file__).parent.parent))

from ask_livekit import ask
from rag.session import close_fallback

FALLBACK_ANSWER = (
    "No tengo ese procedimiento en mis protocolos de emergencia viales registrados. "
    "Por favor, hacé la consulta pertinente o procedé según el protocolo general."
)

# Contexto previo de la llamada: simula el saludo y el triage inicial que ya
# pasaron (confirmación de seguridad + ubicación) para que la query del dataset
# llegue cuando el agente ya superó los primeros segundos. Sin esto, el agente
# siempre arranca preguntando "¿estás fuera de la calzada?" y nunca responde la
# consulta puntual, con lo que el STS mide la confusión, no el retrieval.
PRELUDE = [
    "Acabo de ver un accidente, hay un auto volcado.",
    "Sí, estoy fuera de la calzada, a salvo. Estoy en la ruta 9, kilómetro 45.",
]

# Importar CSV de dataset
dataset_path = Path(__file__).parent / "DataSet.csv"
df_dataset = pd.read_csv(dataset_path)

queries = df_dataset["Query"].tolist()
expected_answers = df_dataset["RespuestaEsperada"].tolist()


async def main():
    unanswered = 0
    similarities = []

    for question, expected in zip(queries, expected_answers):
        answer = await ask(question, prelude=PRELUDE)
        print(f"Pregunta: {question}")
        print(f"Respuesta: {answer}")

        if answer == FALLBACK_ANSWER:
            unanswered += 1
            continue

        answer_embedding = await get_cohere_embedding(answer)
        expected_embedding = await get_cohere_embedding(expected)
        similarity = cosine_similarity(answer_embedding, expected_embedding)
        print(f"Similitud: {similarity}")
        similarities.append(similarity)

    print(f"Cantidad de preguntas sin respuesta: {unanswered}")
    if similarities:
        print(f"STS promedio: {np.mean(similarities):.4f}")
    else:
        print("No se pudieron calcular similitudes.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        asyncio.run(close_fallback())
