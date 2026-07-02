import asyncio
import sys
import os
import json
from typing import List

# Añadir el directorio raíz al path para poder importar src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.main import Pipeline

def critical_information_coverage(generated_answer: str, critical_facts: List[str]) -> float:
    """
    Calcula el Critical Information Coverage verificando si los hechos críticos están en la respuesta.
    """
    if not critical_facts:
        return 0.0
        
    answer_lower = generated_answer.lower()
    
    covered_facts = 0
    for fact in critical_facts:
        if fact.lower() in answer_lower:
            covered_facts += 1
            
    return covered_facts / len(critical_facts)

async def main():
    print("--- EVALUACIÓN DE CRITICAL INFO COVERAGE CON RAG REAL ---")
    print("Inicializando conexión a Base de Datos y Ollama...")
    
    # Forzar la URL correcta de la base de datos (puerto 5433, base emergencias_vdb) 
    # tal como está configurado en tu docker-compose para la DB vectorial.
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5433/emergencias_vdb"
    
    # Inicializar el pipeline real
    pipe_instance = Pipeline()
    await pipe_instance.on_startup()
    
    # Cargar dataset unificado desde JSON
    dataset_path = os.path.join(os.path.dirname(__file__), "dataset_evaluacion.json")
    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            evaluation_dataset = json.load(f)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo de dataset en {dataset_path}")
        return
    
    total_coverage = 0.0
    num_queries = len(evaluation_dataset)
    results = []
    
    for i, data in enumerate(evaluation_dataset):
        query = data["query"]
        critical_facts = data["critical_facts"]
        
        print(f"Consulta {i+1}: '{query}'")
        print("  Generando respuesta real (esto puede tardar unos segundos)...")
        
        # GENERACIÓN REAL A TRAVÉS DEL PIPELINE
        # El modelo y la URL de Ollama los toma de la configuración del pipeline (Valves)
        response_stream = pipe_instance.pipe(query, pipe_instance.valves.MODEL_NAME, [])
        
        # Recolectamos la respuesta completa ya que viene en un generador (stream)
        generated_answer = ""
        if isinstance(response_stream, str):
            generated_answer = response_stream
        else:
            for token in response_stream:
                generated_answer += token
                
        coverage = critical_information_coverage(generated_answer, critical_facts)
        total_coverage += coverage
        
        results.append({
            "query_id": i + 1,
            "query": query,
            "critical_facts": critical_facts,
            "generated_answer": generated_answer,
            "critical_info_coverage": coverage
        })
        print(f"  Hechos críticos cubiertos: {coverage:.2f}")
        print(f"  Respuesta generada: {generated_answer.strip()[:100]}...\n")
    
    avg_coverage = total_coverage / num_queries
    print(f"Promedio global Coverage: {avg_coverage:.2f}")
    
    # Limpieza
    await pipe_instance.on_shutdown()
    
    # Guardar resultados en JSON
    output_dir = os.path.join(os.path.dirname(__file__), "resultados")
    os.makedirs(output_dir, exist_ok=True)
    
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"resultados_critical_info_coverage_{timestamp}.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "fase": "Evaluación RAG Real",
            "promedio_global_critical_info_coverage": avg_coverage,
            "resultados_detallados": results
        }, f, indent=4, ensure_ascii=False)
        
    print(f"Resultados guardados en '{output_file}'")

if __name__ == "__main__":
    asyncio.run(main())
