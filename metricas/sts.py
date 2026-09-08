import asyncio
import math
import os
from typing import List

import aiohttp
import pandas as pd
import numpy as np

import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env.local", override=True)

from rag.embeddings import embed_query
from rag.config import load_settings
from ask_livekit import ask
from rag.session import close_fallback

settings = load_settings()


# ── Similitud coseno ────────────────────────────────────────────────────────
def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Similitud coseno entre dos vectores (Python puro, sin numpy)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

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

        answer_embedding = await embed_query(answer, settings)
        expected_embedding = await embed_query(expected, settings)
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
