"""
Answer Relevancy — Relevancia de la respuesta (métrica de Alex)
==============================================================

Mide qué tan PERTINENTE es la respuesta generada respecto a la pregunta del
usuario. Es una métrica *reference-free*: NO usa la respuesta esperada, solo
la pregunta y la respuesta que produce el RAG. Penaliza respuestas incompletas,
divagantes o con información irrelevante.

Procedimiento (estilo RAGAS)
----------------------------
1. Se genera la respuesta real del RAG para la pregunta original `q`.
2. Un LLM genera `N_QUESTIONS` preguntas "inversas" {q1..qn}: preguntas que esa
   respuesta estaría contestando.
3. Se calcula la similitud coseno entre el embedding de `q` y el de cada `qi`.
4. Answer Relevancy = promedio de esas similitudes.
   - Si la respuesta es "evasiva" (no compromete información: "no tengo ese
     dato", derivación al 911, etc.) se asigna 0, porque una respuesta que no
     responde no puede ser relevante.

Intuición: si la respuesta es buena y está enfocada, las preguntas que se
"deducen" de ella se parecerán mucho a la pregunta original.

Reutiliza el LLM (Ollama) y el modelo de embeddings ya cableados en el pipeline;
no requiere dependencias nuevas (coseno en Python puro).
"""
import asyncio
import sys
import os
import json
import math
import re
from typing import List

# Añadir el directorio raíz al path para poder importar src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.main import Pipeline

# ── Parámetros de la métrica ──────────────────────────────────────────────────
N_QUESTIONS = 3   # nº de preguntas inversas a generar por respuesta (RAGAS usa 3)

# Frases que delatan una respuesta evasiva / no comprometida -> relevancia 0.
NONCOMMITTAL_MARKERS = [
    "no tengo", "no dispongo", "no poseo", "no puedo ayudar", "no puedo responder",
    "no cuento con", "no hay información", "fuera de mi alcance", "no está en el",
    "comunícate con el 911", "comunicate con el 911", "llamá al 911", "no lo sé",
    "no lo se", "no tengo información",
]


def collect_stream(stream) -> str:
    """El pipeline devuelve un generador (stream) o un string; lo unificamos a texto."""
    if isinstance(stream, str):
        return stream
    return "".join(token for token in stream)


def is_noncommittal(answer: str) -> bool:
    """Heurística: detecta respuestas evasivas que no comprometen información."""
    a = answer.lower()
    return any(marker in a for marker in NONCOMMITTAL_MARKERS)


def build_reverse_question_prompt(answer: str, n: int) -> str:
    """Prompt para que el LLM infiera las preguntas que la respuesta contesta."""
    return (
        f"A partir de la siguiente RESPUESTA, generá exactamente {n} preguntas "
        f"distintas, en español, que esa respuesta estaría contestando.\n"
        f"Devolvé SOLO las preguntas, una por línea, sin numeración, sin viñetas "
        f"y sin ningún texto adicional.\n\n"
        f"RESPUESTA:\n{answer}\n\n"
        f"PREGUNTAS:"
    )


def parse_questions(raw: str, n: int) -> List[str]:
    """Extrae hasta `n` preguntas del texto crudo generado por el LLM."""
    questions = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Quitar numeración/viñetas iniciales: "1.", "1)", "-", "*", "•"
        line = re.sub(r"^\s*(?:\d+[\.\)]|[-*•])\s*", "", line).strip()
        if line:
            questions.append(line)
    return questions[:n]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Similitud coseno entre dos vectores (Python puro, sin numpy)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def main():
    print("--- EVALUACIÓN DE ANSWER RELEVANCY CON EL RAG REAL ---")
    print(f"Configuración: {N_QUESTIONS} preguntas inversas por respuesta")
    print("Inicializando conexión a Base de Datos y Ollama...")

    # Forzar la URL correcta de la base de datos (puerto 5433, base emergencias_vdb).
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5433/emergencias_vdb"

    pipe_instance = Pipeline()
    await pipe_instance.on_startup()

    dataset_path = os.path.join(os.path.dirname(__file__), "dataset_evaluacion.json")
    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            evaluation_dataset = json.load(f)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo de dataset en {dataset_path}")
        return

    total_relevancy = 0.0
    num_queries = len(evaluation_dataset)
    results = []

    for i, data in enumerate(evaluation_dataset):
        query = data["query"]
        print(f"Consulta {i+1}: '{query}'")
        print("  Generando respuesta real (esto puede tardar unos segundos)...")

        # 1) Respuesta real del RAG
        generated_answer = collect_stream(
            pipe_instance.pipe(query, pipe_instance.valves.MODEL_NAME, [])
        ).strip()

        # 2) Respuesta evasiva -> relevancia 0
        if is_noncommittal(generated_answer):
            relevancy = 0.0
            gen_questions, sims = [], []
            print("  Respuesta evasiva detectada -> Answer Relevancy = 0.0\n")
        else:
            # 3) Preguntas inversas generadas por el LLM
            rq_prompt = build_reverse_question_prompt(generated_answer, N_QUESTIONS)
            raw_questions = collect_stream(pipe_instance.llm_client.generate_stream(rq_prompt))
            gen_questions = parse_questions(raw_questions, N_QUESTIONS)

            if not gen_questions:
                relevancy = 0.0
                sims = []
                print("  El LLM no generó preguntas inversas -> Answer Relevancy = 0.0\n")
            else:
                # 4) Similitud coseno pregunta original vs. cada pregunta inversa
                q_emb = pipe_instance.searcher.get_embeddings(query)
                sims = [
                    cosine_similarity(q_emb, pipe_instance.searcher.get_embeddings(gq))
                    for gq in gen_questions
                ]
                relevancy = sum(sims) / len(sims)
                print(f"  Preguntas inversas generadas: {len(gen_questions)}")
                print(f"  Answer Relevancy = {relevancy:.3f}\n")

        total_relevancy += relevancy

        results.append({
            "query_id": i + 1,
            "query": query,
            "generated_answer": generated_answer,
            "noncommittal": is_noncommittal(generated_answer),
            "preguntas_inversas": gen_questions,
            "similitudes": [round(s, 4) for s in sims],
            "answer_relevancy": relevancy,
        })

    avg_relevancy = total_relevancy / num_queries if num_queries else 0.0
    print("=" * 60)
    print(f"Answer Relevancy global (promedio): {avg_relevancy:.4f}")

    await pipe_instance.on_shutdown()

    output_dir = os.path.join(os.path.dirname(__file__), "resultados")
    os.makedirs(output_dir, exist_ok=True)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"resultados_answer_relevancy_{timestamp}.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "fase": "Evaluación RAG Real",
            "metrica": "Answer Relevancy",
            "n_preguntas_inversas": N_QUESTIONS,
            "answer_relevancy_global": avg_relevancy,
            "num_consultas": num_queries,
            "resultados_detallados": results,
        }, f, indent=4, ensure_ascii=False)

    print(f"Resultados guardados en '{output_file}'")


if __name__ == "__main__":
    asyncio.run(main())
