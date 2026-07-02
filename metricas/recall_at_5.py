"""
Recall@5 (métrica de Andy) — versión a nivel CHUNK
==================================================

Recall@K mide qué proporción de los chunks relevantes (gold) fueron recuperados
dentro del top-K.

    Recall@K = |chunks_recuperados_topK  ∩  chunks_gold| / |chunks_gold|

Por qué a nivel chunk (y no documento)
--------------------------------------
Todos los chunks provienen de un único PDF, así que comparar el nombre del PDF
recuperado contra el nombre del PDF esperado es degenerado: da 1.0 en todas las
consultas (verificado en corridas previas). No mide calidad de retrieval.

Por eso la relevancia se evalúa a nivel de chunk. Los ids de chunk son UUID
aleatorios (cambian si se re-ingesta) y no hay número de página, así que NO se
hardcodean: el conjunto gold se resuelve EN TIEMPO DE EVALUACIÓN recorriendo el
corpus y marcando los chunks cuyo texto contiene al menos `MIN_HITS` de las
palabras-clave distintivas de la respuesta (`mrr_relevant_keywords`; si falta,
`critical_facts`). Match por substring, insensible a mayúsculas y acentos.
"""
import asyncio
import sys
import os
import json
import unicodedata
from typing import List, Tuple, Set

# Añadir el directorio raíz al path para poder importar src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.main import Pipeline

# ── Parámetros de la métrica ──────────────────────────────────────────────────
K = 5           # top-K a evaluar (Recall@5)
MIN_HITS = 1    # nº de keywords que debe contener un chunk para ser "gold"


def _normalize(text: str) -> str:
    """Minúsculas y sin acentos, para un match robusto por substring."""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def matched_keywords(chunk_text: str, keywords: List[str]) -> List[str]:
    """Keywords que aparecen (como substring normalizado) en el texto del chunk."""
    norm_text = _normalize(chunk_text)
    return [kw for kw in keywords if _normalize(kw) in norm_text]


def fetch_corpus(db_manager) -> List[Tuple[str, str]]:
    """Trae todo el corpus como lista de (chunk_id, texto). [] si la BD no está disponible."""
    if getattr(db_manager, "use_mock", False) or db_manager.cursor is None:
        return []
    try:
        db_manager.cursor.execute("SELECT id, texto_del_chunk FROM protocol_chunks;")
        return [(str(row[0]), row[1]) for row in db_manager.cursor.fetchall()]
    except Exception as e:
        if db_manager.conn:
            db_manager.conn.rollback()
        print(f"[Recall - Aviso] No se pudo leer el corpus completo ({e}).")
        return []


def gold_ids_for_query(
    corpus: List[Tuple[str, str]], keywords: List[str], min_hits: int = MIN_HITS
) -> Set[str]:
    """Ids de los chunks del corpus que contienen >= min_hits keywords (gold set)."""
    if not keywords:
        return set()
    return {
        cid for cid, text in corpus
        if len(matched_keywords(text, keywords)) >= min_hits
    }


def recall_at_k(retrieved_ids: List[str], gold_ids: Set[str], k: int = K) -> float:
    """
    Proporción de chunks gold que aparecen en el top-K recuperado.
    Devuelve None si no hay chunks gold en el corpus (consulta no evaluable).
    """
    if not gold_ids:
        return None
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & gold_ids)
    return hits / len(gold_ids)


async def main():
    print("--- EVALUACIÓN DE RECALL@5 (nivel chunk) CON EL RAG REAL ---")
    print(f"Configuración: Recall@{K}, min_hits={MIN_HITS}")
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

    # Corpus completo (necesario para el denominador: cuántos chunks gold existen).
    corpus = fetch_corpus(pipe_instance.searcher.db_manager)
    if corpus:
        print(f"[Recall] Corpus cargado: {len(corpus)} chunks.\n")
    else:
        print("[Recall] ADVERTENCIA: sin acceso al corpus completo, el denominador de "
              "Recall no es fiable. Levantá la BD (pg :5433) para un resultado válido.\n")

    total_recall = 0.0
    evaluadas = 0
    results = []

    for i, data in enumerate(evaluation_dataset):
        query = data["query"]
        keywords = data.get("mrr_relevant_keywords") or data.get("critical_facts", [])

        chunks = pipe_instance.searcher.search_similarity(query, limit=K)
        retrieved_ids = [chunk.id for chunk in chunks]
        gold_ids = gold_ids_for_query(corpus, keywords) if corpus else set()

        r_at_k = recall_at_k(retrieved_ids, gold_ids, k=K)

        if r_at_k is not None:
            total_recall += r_at_k
            evaluadas += 1
            recall_display = f"{r_at_k:.2f}"
        else:
            recall_display = "N/A (sin chunks gold en el corpus)"

        results.append({
            "query_id": i + 1,
            "query": query,
            "gold_keywords": keywords,
            "expected_chunk_ids": sorted(gold_ids),
            "num_expected_chunks": len(gold_ids),
            "retrieved_chunk_ids": retrieved_ids,
            "recall_at_5": r_at_k,
        })
        print(f"Consulta {i+1}: '{query}'")
        print(f"  Chunks gold en corpus: {len(gold_ids)} | recuperados top-{K}: {len(retrieved_ids)}")
        print(f"  Recall@{K}: {recall_display}\n")

    avg_recall = total_recall / evaluadas if evaluadas else 0.0
    print("=" * 60)
    print(f"Recall@{K} promedio (sobre {evaluadas} consultas evaluables): {avg_recall:.4f}")

    await pipe_instance.on_shutdown()

    output_dir = os.path.join(os.path.dirname(__file__), "resultados")
    os.makedirs(output_dir, exist_ok=True)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"resultados_recall_at_5_{timestamp}.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "fase": "Evaluación RAG Real",
            "metrica": f"Recall@{K} (nivel chunk)",
            "min_hits": MIN_HITS,
            "promedio_global_recall_at_5": avg_recall,
            "consultas_evaluables": evaluadas,
            "num_consultas": len(evaluation_dataset),
            "resultados_detallados": results,
        }, f, indent=4, ensure_ascii=False)

    print(f"Resultados guardados en '{output_file}'")


if __name__ == "__main__":
    asyncio.run(main())
