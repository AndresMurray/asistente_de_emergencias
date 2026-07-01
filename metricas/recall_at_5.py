import asyncio
import sys
import os
import json
from typing import List

# Añadir el directorio raíz al path para poder importar src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.main import Pipeline

def recall_at_k(retrieved_doc_ids: List[str], expected_relevant_docs: List[str], k: int = 5) -> float:
    """
    Calcula el Recall@K (Qué porcentaje de los documentos relevantes esperados 
    fueron recuperados en el top K).
    """
    if not expected_relevant_docs:
        return 0.0
        
    top_k_retrieved = retrieved_doc_ids[:k]
    
    hits = sum(1 for doc in expected_relevant_docs if doc in top_k_retrieved)
    return hits / len(expected_relevant_docs)

async def main():
    print("--- EVALUACIÓN DE RECALL@5 CON EL RAG REAL ---")
    print("Inicializando conexión a Base de Datos y Ollama...")
    
    # Inicializar el pipeline real
    pipe_instance = Pipeline()
    await pipe_instance.on_startup()
    
    # Este es el dataset que usarás. Debes definir qué ID o metadata de origen 
    # esperas que el RAG recupere (por ejemplo, el nombre del archivo en 'source' 
    # o una fase específica en la metadata).
    evaluation_dataset = [
        {
            "query": "¿Qué datos se deben registrar al tomar conocimiento de un siniestro vial?",
            # Ajusta esto para que coincida con los 'source' o metadatos de tus chunks
            "expected_relevant_docs": ["protocolo_default.pdf"] 
        },
        {
            "query": "¿Qué hago al arribar al lugar de un accidente?",
            "expected_relevant_docs": ["protocolo_default.pdf"]
        }
    ]
    
    total_recall = 0.0
    num_queries = len(evaluation_dataset)
    results = []
    
    for i, data in enumerate(evaluation_dataset):
        query = data["query"]
        expected = data["expected_relevant_docs"]
        
        # BUSQUEDA REAL EN EL VECTOR STORE:
        # Extraemos el limit a 5 para el Recall@5
        chunks = pipe_instance.searcher.search_similarity(query, limit=5)
        
        # Extraemos una característica única del chunk recuperado (ej: el metadata 'source')
        # Dependiendo de tu base de datos, puedes cambiarlo por chunk.id o chunk.metadata.get("id_documento")
        retrieved_ids = [chunk.metadata.get("source", "desconocido") for chunk in chunks]
        
        r_at_5 = recall_at_k(retrieved_ids, expected, k=5)
        total_recall += r_at_5
        
        results.append({
            "query_id": i + 1,
            "query": query,
            "retrieved_ids": retrieved_ids,
            "expected_ids": expected,
            "recall_at_5": r_at_5
        })
        print(f"Consulta {i+1}: '{query}'")
        print(f"  Recuperados: {retrieved_ids}")
        print(f"  Esperados: {expected}")
        print(f"  Recall@5: {r_at_5:.2f}\n")
    
    avg_recall_at_5 = total_recall / num_queries
    print(f"Promedio global Recall@5: {avg_recall_at_5:.2f}")
    
    # Limpieza
    await pipe_instance.on_shutdown()
    
    output_file = "resultados_recall_at_5_real.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "fase": "Evaluación RAG Real",
            "promedio_global_recall_at_5": avg_recall_at_5,
            "resultados_detallados": results
        }, f, indent=4, ensure_ascii=False)
        
    print(f"Resultados guardados en '{output_file}'")

if __name__ == "__main__":
    asyncio.run(main())
