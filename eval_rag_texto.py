"""
Evaluación textual del RAG sin usar voz ni LiveKit.

Uso:
    python eval_rag_texto.py

Requiere un archivo .env.local con:
    DATABASE_URL=postgresql://...
    COHERE_API_KEY=...
    GROQ_API_KEY=...

Opcionalmente se puede pasar un dataset JSON:
    python eval_rag_texto.py --dataset tests_eval/test_dataset.json

El formato del dataset es:
[
    {"id": 1, "query": "¿...?", "expected_scope": "in_scope", "keywords": ["..."]},
    ...
]
"""

import os
import sys
import json
import time
import asyncio
import argparse
from typing import Any

import requests
from dotenv import load_dotenv

# Reusamos la lógica de retrieval ya implementada en agent.py.
# Evitamos importar livekit porque no lo necesitamos para evaluar el RAG.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import search_similarity, SYSTEM_INSTRUCTIONS

load_dotenv(".env.local")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


def build_messages(query: str, context: str) -> list[dict[str, str]]:
    """Construye los mensajes para el LLM con el system prompt y el contexto recuperado."""
    user_message = (
        "Consulta del operador:\n"
        f"{query}\n\n"
        "Contexto recuperado de los protocolos:\n"
        f"{context}\n\n"
        "Respondé como si estuvieras hablando por radio con un operador en el lugar del siniestro. "
        "Solo voz clara y directa. Sin Markdown, sin viñetas."
    )
    return [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": user_message},
    ]


def generate_answer(messages: list[dict[str, str]]) -> str:
    """Llama a Groq y devuelve el texto de la respuesta."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY no está configurada en .env.local")

    response = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 512,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


async def evaluate_query(query: str) -> dict[str, Any]:
    """Ejecuta una consulta contra el RAG y devuelve contexto + respuesta + métricas."""
    print(f"\n[Query] {query}")

    start = time.perf_counter()
    context = await search_similarity(query)
    retrieval_ms = (time.perf_counter() - start) * 1000

    print(f"[Retrieval] {retrieval_ms:.1f} ms | chunks recuperados: {context.count('[GENERAL]') if context else 0}")
    if context:
        print("--- Contexto recuperado ---")
        print(context)
        print("---------------------------")
    else:
        print("[Advertencia] No se recuperó contexto.")

    start = time.perf_counter()
    messages = build_messages(query, context or "No se encontraron protocolos relevantes.")
    answer = generate_answer(messages)
    llm_ms = (time.perf_counter() - start) * 1000

    print(f"[LLM] {llm_ms:.1f} ms")
    print(f"[Respuesta] {answer}")

    return {
        "query": query,
        "context": context,
        "answer": answer,
        "retrieval_ms": retrieval_ms,
        "llm_ms": llm_ms,
        "total_ms": retrieval_ms + llm_ms,
    }


def load_default_dataset() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "query": "¿Qué datos se deben registrar al tomar conocimiento de un siniestro vial?",
            "expected_scope": "in_scope",
            "keywords": ["registro", "ubicación", "lesionados", "conocimiento"],
        },
        {
            "id": 2,
            "query": "¿Cuánto tiempo tiene el equipo de emergencia para llegar al lugar del accidente?",
            "expected_scope": "in_scope",
            "keywords": ["arribo", "10 minutos", "escena"],
        },
        {
            "id": 3,
            "query": "¿Cómo actuar en la intervención médica ante heridos graves?",
            "expected_scope": "in_scope",
            "keywords": ["intervención", "médico", "estabilización"],
        },
        {
            "id": 4,
            "query": "¿Cuál es el protocolo de recolección de muestras para el perito judicial?",
            "expected_scope": "out_of_scope",
            "keywords": ["No tengo ese procedimiento", "911"],
        },
        {
            "id": 5,
            "query": "¿Cuál es la capital de Francia y qué museos hay que visitar?",
            "expected_scope": "out_of_scope",
            "keywords": ["No tengo ese procedimiento", "911"],
        },
    ]


async def interactive_mode() -> None:
    """Modo conversación: lee consultas de stdin y responde usando el RAG."""
    print("\n[Modo interactivo] Escribí una consulta y presioná Enter.")
    print("                  Escribí 'salir' o Ctrl+C para terminar.\n")
    try:
        while True:
            query = input("Operador > ").strip()
            if query.lower() in {"salir", "exit", "quit"}:
                print("Saliendo...")
                break
            if not query:
                continue
            await evaluate_query(query)
    except KeyboardInterrupt:
        print("\nSaliendo...")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluación textual del RAG")
    parser.add_argument(
        "--dataset",
        default=None,
        help="Ruta a un JSON con queries de prueba. Si no se indica, usa el dataset por defecto.",
    )
    parser.add_argument(
        "--output",
        default="eval_rag_resultados.json",
        help="Ruta donde guardar los resultados (por defecto: eval_rag_resultados.json)",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Consulta única para evaluar. Ignora --dataset.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Entra en modo conversación interactivo por texto.",
    )
    args = parser.parse_args()

    if args.interactive:
        await interactive_mode()
        return

    if args.query:
        await evaluate_query(args.query)
        return

    if args.dataset:
        with open(args.dataset, "r", encoding="utf-8") as f:
            dataset = json.load(f)
    else:
        dataset = load_default_dataset()

    print(f"[Evaluación RAG] {len(dataset)} casos de prueba")
    print("=" * 80)

    results: list[dict[str, Any]] = []
    for case in dataset:
        print(f"\n[Caso {case.get('id', '?')}] scope esperado: {case.get('expected_scope', 'n/a')}")
        result = await evaluate_query(case["query"])
        result["id"] = case.get("id")
        result["expected_scope"] = case.get("expected_scope")
        result["keywords"] = case.get("keywords", [])
        results.append(result)

    print("\n" + "=" * 80)
    print("RESUMEN")
    print("=" * 80)
    total_ms = sum(r["total_ms"] for r in results)
    avg_ms = total_ms / len(results) if results else 0
    print(f"Casos evaluados: {len(results)}")
    print(f"Latencia promedio total: {avg_ms:.1f} ms")
    print(f"Resultados guardados en: {args.output}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
