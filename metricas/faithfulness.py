import sys
import os
import json
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv

# Añadir el directorio raíz al path para poder importar agent
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Cargamos env local antes de importar agent
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env.local'))

from agent import search_similarity
from livekit_agente import obtener_respuesta_agente_livekit

# ── Parámetros ──────────────────────────────────────────────────────────────
MODEL_JUDGE = "llama-3.3-70b-versatile"

# Instrucciones para el Juez
JUDGE_SYSTEM_PROMPT = """Sos un evaluador de Fidelidad (Faithfulness Judge) para un sistema RAG (Retrieval-Augmented Generation).
Tu tarea es evaluar si la respuesta generada por el asistente es FIEL al contexto provisto.

REGLAS DE FIDELIDAD:
1. Toda la información fáctica, afirmaciones, procedimientos y recomendaciones en la respuesta deben poder deducirse o encontrarse directamente en el contexto provisto.
2. Si la respuesta contiene información inventada (alucinaciones) que no está respaldada por el contexto, la respuesta NO es fiel.
3. Si el contexto está vacío (o dice que no hay protocolos) y el asistente responde acordemente que no tiene información, se considera FIEL.
4. No evalúas la pertinencia o si responde la pregunta original (eso es otra métrica), solo evalúas si inventó información que no estaba en el contexto.

FORMATO DE RESPUESTA:
Debes responder ÚNICAMENTE con un objeto JSON válido, sin markdown, con este formato exacto:
{
  "faithful": true o false,
  "reason": "Explicación breve de por qué es fiel al contexto o qué afirmación específica fue inventada."
}
"""


async def evaluate_faithfulness(query: str, answer: str, context: str, session: aiohttp.ClientSession, api_key: str) -> dict:
    if answer == "ERROR_GENERATION":
        return {"faithful": False, "reason": "Error generating response"}

    prompt = f"Consulta original del usuario: {query}\n\nContexto recuperado (Knowledge Base):\n{context}\n\nRespuesta generada por el asistente:\n{answer}\n\nEvalúa la respuesta e indica si es faithful (fiel) al contexto."

    payload = {
        "model": MODEL_JUDGE,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "response_format": { "type": "json_object" }
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    for attempt in range(6):
        try:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 429:
                    wait_time = 10 * (attempt + 1)
                    print(f"    [Rate Limit Judge] Esperando {wait_time}s para reintentar... (intento {attempt+1}/6)")
                    await asyncio.sleep(wait_time)
                    continue
                if resp.status != 200:
                    print(f"Error en Groq API (Judge): {await resp.text()}")
                    return {"faithful": False, "reason": "Error in Judge API call"}
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"faithful": False, "reason": "Error parsing Judge JSON"}
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            print(f"    [Network/Timeout Error Judge] Reintentando... ({e})")
            await asyncio.sleep(5)
    return {"faithful": False, "reason": "Rate limit / Timeout exceeded"}


async def main():
    print("--- EVALUACIÓN DE FAITHFULNESS (Agente real LiveKit / RAG) ---")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("ERROR: La variable de entorno GROQ_API_KEY no está configurada en .env.local.")
        return

    dataset_path = os.path.join(os.path.dirname(__file__), "dataset_evaluacion.json")
    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            evaluation_dataset = json.load(f)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo de dataset en {dataset_path}")
        return

    num_queries = len(evaluation_dataset)
    results = []
    faithful_count = 0
    evaluated_count = 0
    error_count = 0

    async with aiohttp.ClientSession() as session:
        for i, data in enumerate(evaluation_dataset):
            query = data["query"]
            print(f"\n[{i+1}/{num_queries}] Evaluando consulta: '{query}'")

            # 1. Obtener respuesta del agente real de LiveKit (RAG desplegado)
            print("  Consultando al agente real de LiveKit (RAG)...")
            generated_answer = await obtener_respuesta_agente_livekit(query)

            if generated_answer == "ERROR_GENERATION":
                error_count += 1
                print("  ⚠️ ERROR_GENERATION: el agente no respondió (excluida del score).")
                results.append({
                    "query_id": i + 1,
                    "query": query,
                    "retrieved_context": "No se pudo recuperar (sin respuesta del agente).",
                    "generated_answer": generated_answer,
                    "faithfulness_evaluation": {"faithful": None, "reason": "Error generating response"},
                })
                continue

            # 2. Recuperar el contexto que debió usar el RAG para esta consulta
            print("  Recuperando contexto RAG (separado)...")
            retrieved_context = await search_similarity(query)
            if not retrieved_context:
                retrieved_context = "No se encontraron protocolos."

            # 3. Evaluar con Juez
            print("  Evaluando fidelidad (LLM-as-a-Judge)...")
            judge_result = await evaluate_faithfulness(query, generated_answer, retrieved_context, session, api_key)

            evaluated_count += 1
            is_faithful = judge_result.get("faithful", False)
            if is_faithful:
                faithful_count += 1
                print("  ✅ Resultado: FAITHFUL (Fiel)")
            else:
                print(f"  ❌ Resultado: UNFAITHFUL -> Razón: {judge_result.get('reason', '')}")

            results.append({
                "query_id": i + 1,
                "query": query,
                "retrieved_context": retrieved_context,
                "generated_answer": generated_answer,
                "faithfulness_evaluation": judge_result
            })

            # Pausa para evitar rate limits de Groq (judge) y sobrecargar al agente
            await asyncio.sleep(2)

    faithfulness_score = (faithful_count / evaluated_count) * 100 if evaluated_count else 0.0
    print("\n" + "=" * 60)
    print(f"Faithfulness Global: {faithfulness_score:.2f}% ({faithful_count}/{evaluated_count} consultas fieles al contexto)")
    if error_count:
        print(f"⚠️  Se excluyeron {error_count} consultas por ERROR_GENERATION (el agente no respondió).")

    output_dir = os.path.join(os.path.dirname(__file__), "resultados")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"resultados_faithfulness_{timestamp}.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "fase": "Evaluación Faithfulness (Agente real LiveKit / RAG)",
            "metrica": "Faithfulness",
            "model_generation": "Agente LiveKit Cloud (RAG desplegado)",
            "model_judge": MODEL_JUDGE,
            "faithfulness_score_percent": faithfulness_score,
            "num_consultas": num_queries,
            "num_evaluadas": evaluated_count,
            "num_faithful": faithful_count,
            "num_error_generacion": error_count,
            "resultados_detallados": results,
        }, f, indent=4, ensure_ascii=False)

    print(f"Resultados guardados en '{output_file}'")

if __name__ == "__main__":
    asyncio.run(main())