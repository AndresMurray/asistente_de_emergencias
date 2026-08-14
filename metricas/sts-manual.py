import asyncio
from sts import cosine_similarity, get_cohere_embedding
import pandas as pd
import numpy as np

# Importar la función ask del script ask_livekit.py
import sys
from pathlib import Path

# Agregar el root del proyecto a sys.path para poder importar ask_livekit
# cuando este script se corre desde metricas/.
sys.path.insert(0, str(Path(__file__).parent.parent))

from ask_livekit import ask
from rag.session import close_fallback

FALLBACK_ANSWER = (
    "No tengo ese procedimiento en mis protocolos de emergencia viales registrados. "
    "Por favor, hacé la consulta pertinente o procedé según el protocolo general."
)

# Importar CSV de dataset
dataset_path = Path(__file__).parent.parent / "DataSet.csv"
df_dataset = pd.read_csv(dataset_path)

queries = df_dataset["Query"].tolist()
expected_answers = df_dataset["RespuestaEsperada"].tolist()


async def main():
    unanswered = 0
    similarities = []

    for question, expected in zip(queries, expected_answers):
        answer = await ask(question)
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
        close_fallback()
