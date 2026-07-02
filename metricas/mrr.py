"""
MRR — Mean Reciprocal Rank (métrica de Salva)
=============================================

Mide la CALIDAD DEL RANKING del retriever: para cada consulta, ¿en qué posición
del top-K aparece el PRIMER chunk relevante? Cuanto más arriba, mejor.

    RR_i = 1 / rank_del_primer_chunk_relevante   (0 si no aparece en el top-K)
    MRR  = promedio de RR_i sobre todas las consultas

Granularidad: chunk, no documento
---------------------------------
Todos los chunks provienen de un único PDF, así que comparar a nivel *documento*
(nombre del PDF contra nombre del PDF) es degenerado: daría 1.0 siempre. Por eso
el MRR se evalúa comparando **ids de chunk contra ids de chunk**.

Cómo se define el "chunk relevante" (expected_chunk_ids)
-------------------------------------------------------
Los ids de chunk son UUID aleatorios asignados en la ingesta (cambian si se
re-ingesta) y los chunks no guardan número de página. Por eso NO hardcodeamos
ids en el dataset: los resolvemos EN TIEMPO DE EVALUACIÓN. Se recorre todo el
corpus y se marcan como relevantes (gold) los chunks cuyo texto contiene al
menos `MIN_HITS` de las palabras-clave distintivas de la respuesta correcta
(campo `mrr_relevant_keywords`; si falta, se usa `critical_facts`).

Así obtenemos, por consulta, un conjunto real de `expected_chunk_ids`, y el MRR
compara esos ids contra los `retrieved_chunk_ids` que devuelve el retriever.
El match de keywords es por substring, insensible a mayúsculas y acentos.
"""
import asyncio
import sys
import os
import json
import unicodedata
from typing import List, Tuple, Dict, Set

# Añadir el directorio raíz al path para poder importar src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.main import Pipeline

# ── Parámetros de la métrica ──────────────────────────────────────────────────
K = 10          # profundidad del ranking a evaluar (MRR@K)
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
    """
    Trae todo el corpus como lista de (chunk_id, texto). Necesario para resolver
    el conjunto 'gold' de chunks relevantes por consulta. Devuelve [] si la BD no
    está disponible (modo mock o error), en cuyo caso se cae al fallback.
    """
    if getattr(db_manager, "use_mock", False) or db_manager.cursor is None:
        return []
    try:
        db_manager.cursor.execute("SELECT id, texto_del_chunk FROM protocol_chunks;")
        return [(str(row[0]), row[1]) for row in db_manager.cursor.fetchall()]
    except Exception as e:
        if db_manager.conn:
            db_manager.conn.rollback()
        print(f"[MRR - Aviso] No se pudo leer el corpus completo ({e}). Se usará fallback.")
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


def reciprocal_rank(retrieved_ids: List[str], gold_ids: Set[str]) -> Tuple[float, int]:
    """
    (reciprocal_rank, rank_del_primer_relevante). Recorre los ids recuperados en
    orden y se detiene en el primero que pertenece al gold set. (0.0, -1) si ninguno.
    """
    if not gold_ids:
        return 0.0, -1
    for rank, cid in enumerate(retrieved_ids, start=1):
        if cid in gold_ids:
            return 1.0 / rank, rank
    return 0.0, -1


async def main():
    print("--- EVALUACIÓN DE MRR (Mean Reciprocal Rank) CON EL RAG REAL ---")
    print(f"Configuración: MRR@{K}, min_hits={MIN_HITS} (relevancia a nivel chunk)")
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

    # Corpus completo (para resolver los expected_chunk_ids reales por consulta).
    corpus = fetch_corpus(pipe_instance.searcher.db_manager)
    if corpus:
        print(f"[MRR] Corpus cargado: {len(corpus)} chunks. Resolviendo gold ids por consulta.\n")
    else:
        print("[MRR] Sin acceso al corpus completo: los chunks gold se resolverán "
              "sobre los recuperados (RR equivalente, sin denominador de Recall).\n")

    total_rr = 0.0
    num_queries = len(evaluation_dataset)
    results = []

    for i, data in enumerate(evaluation_dataset):
        query = data["query"]
        keywords = data.get("mrr_relevant_keywords") or data.get("critical_facts", [])

        # BÚSQUEDA REAL EN EL VECTOR STORE (top-K para poder rankear).
        chunks = pipe_instance.searcher.search_similarity(query, limit=K)
        retrieved_ids = [chunk.id for chunk in chunks]

        # Gold set de ids: contra el corpus completo o, si no hay, sobre los recuperados.
        if corpus:
            gold_ids = gold_ids_for_query(corpus, keywords)
        else:
            gold_ids = {
                chunk.id for chunk in chunks
                if len(matched_keywords(chunk.text, keywords)) >= MIN_HITS
            }

        rr, rank = reciprocal_rank(retrieved_ids, gold_ids)
        total_rr += rr

        ranking_detail = []
        for pos, chunk in enumerate(chunks, start=1):
            ranking_detail.append({
                "rank": pos,
                "chunk_id": chunk.id,
                "fase": chunk.metadata.get("fase_protocolo", "N/A"),
                "es_gold": chunk.id in gold_ids,
                "matched_keywords": matched_keywords(chunk.text, keywords),
                "snippet": chunk.text.strip().replace("\n", " ")[:140],
            })

        results.append({
            "query_id": i + 1,
            "query": query,
            "gold_keywords": keywords,
            "expected_chunk_ids": sorted(gold_ids),
            "num_expected_chunks": len(gold_ids),
            "retrieved_chunk_ids": retrieved_ids,
            "primer_rank_relevante": rank,   # -1 si no apareció en el top-K
            "reciprocal_rank": rr,
            "ranking": ranking_detail,
        })

        rank_str = f"posición {rank}" if rank > 0 else f"NO encontrado en top-{K}"
        print(f"Consulta {i+1}: '{query}'")
        print(f"  Keywords gold: {keywords}")
        print(f"  Chunks gold en el corpus: {len(gold_ids)}")
        print(f"  Primer chunk relevante: {rank_str}  ->  RR = {rr:.3f}\n")

    mrr = total_rr / num_queries if num_queries else 0.0
    hits_at_k = sum(1 for r in results if r["primer_rank_relevante"] > 0)
    print("=" * 60)
    print(f"MRR@{K} global: {mrr:.4f}")
    print(f"Consultas con al menos un chunk relevante en el top-{K}: {hits_at_k}/{num_queries}")

    await pipe_instance.on_shutdown()

    output_dir = os.path.join(os.path.dirname(__file__), "resultados")
    os.makedirs(output_dir, exist_ok=True)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"resultados_mrr_{timestamp}.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "fase": "Evaluación RAG Real",
            "metrica": f"MRR@{K}",
            "min_hits": MIN_HITS,
            "mrr_global": mrr,
            "consultas_con_hit_en_top_k": hits_at_k,
            "num_consultas": num_queries,
            "resultados_detallados": results,
        }, f, indent=4, ensure_ascii=False)

    print(f"Resultados guardados en '{output_file}'")


if __name__ == "__main__":
    asyncio.run(main())
