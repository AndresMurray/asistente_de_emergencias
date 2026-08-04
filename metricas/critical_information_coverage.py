import asyncio
import sys
import os
import json
from typing import List
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Cargar variables de entorno desde .env.local
load_dotenv(".env.local")

# Añadir el directorio raíz al path para poder importar src y agent
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configurar el fallback de la base de datos local si no está definida en .env.local
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5433/emergencias_vdb"

from agent import SYSTEM_INSTRUCTIONS, search_similarity

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

async def ejecutar_agente_remoto(query: str, client: AsyncOpenAI) -> str:
    """
    Simula la llamada al agente remoto LiveKit ejecutando el LLM con las
    mismas instrucciones y resolviendo la llamada de herramienta `buscar_protocolo`.
    """
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": query}
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
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1
        )
        
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        
        if tool_calls:
            # Agregar el mensaje del asistente que pide llamar a la herramienta
            messages.append(response_message)
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if function_name == "buscar_protocolo":
                    search_query = function_args.get("query", query)
                    # Ejecutar la búsqueda real usando la lógica de agent.py
                    tool_output = await search_similarity(search_query)
                    
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_output
                    })
            
            # Segunda llamada al LLM enviando los resultados de la herramienta
            second_response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.1
            )
            return second_response.choices[0].message.content or ""
            
        return response_message.content or ""
    except Exception as e:
        print(f"  [Error LLM] Error al invocar OpenAI: {e}")
        return ""

async def main():
    print("--- EVALUACIÓN DE CRITICAL INFO COVERAGE CON AGENTE LIVEKIT SIMULADO ---")
    print("Inicializando cliente de OpenAI y cargando dataset...")
    
    # Inicializar cliente de OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: No se encontró la variable de entorno OPENAI_API_KEY.")
        return
        
    client = AsyncOpenAI(api_key=api_key)
    
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
        print("  Generando respuesta simulada con gpt-4o-mini y buscar_protocolo...")
        
        # Ejecutar llamada remota simulada
        generated_answer = await ejecutar_agente_remoto(query, client)
                
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
    
    # Guardar resultados en JSON
    output_dir = os.path.join(os.path.dirname(__file__), "resultados")
    os.makedirs(output_dir, exist_ok=True)
    
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"resultados_critical_info_coverage_{timestamp}.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "fase": "Evaluación Agente LiveKit Simulada",
            "promedio_global_critical_info_coverage": avg_coverage,
            "resultados_detallados": results
        }, f, indent=4, ensure_ascii=False)
        
    print(f"Resultados guardados en '{output_file}'")

if __name__ == "__main__":
    asyncio.run(main())
