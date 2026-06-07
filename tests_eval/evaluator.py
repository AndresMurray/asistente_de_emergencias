import os
import json
import time
import asyncio
from typing import List, Dict, Any

from src.main import Pipeline

class RAGEvaluator:
    """Clase encargada de automatizar la evaluación de latencia y precisión del RAG."""

    def __init__(self, dataset_path: str) -> None:
        self.dataset_path = dataset_path
        self.dataset: List[Dict[str, Any]] = []
        self.pipeline = Pipeline()

    def load_dataset(self) -> None:
        """Carga el conjunto de datos de prueba desde un archivo JSON."""
        if not os.path.exists(self.dataset_path):
            raise FileNotFoundError(f"No se encontró el dataset en '{self.dataset_path}'")
        
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            self.dataset = json.load(f)
        print(f"[Evaluator] Cargados {len(self.dataset)} casos de prueba.")

    async def run_evaluation(self) -> None:
        """Ejecuta la evaluación sobre todos los casos de prueba."""
        # Inicializar el pipeline
        await self.pipeline.on_startup()
        
        results = []
        total_latency_ms = 0.0
        successful_guardrails = 0
        successful_keywords = 0
        
        print("\n" + "="*80)
        print(" INICIANDO EVALUACIÓN AUTOMATIZADA DE LA PoC (RAG BAJA LATENCIA)")
        print("="*80)
        print(f"{'ID':<3} | {'Query':<45} | {'Latencia':<10} | {'Guardrail':<10} | {'Keywords':<8}")
        print("-"*80)

        for case in self.dataset:
            qid = case["id"]
            query = case["query"]
            expected_scope = case["expected_scope"]
            keywords = case["keywords"]
            
            start_time = time.perf_counter()
            
            # Invocar el orquestador principal
            raw_response = self.pipeline.pipe(query, "poc-model", [])
            
            # Si la respuesta es un generador (streaming), consumir todos los tokens para medir latencia final
            response_text = ""
            if isinstance(raw_response, str):
                response_text = raw_response
            else:
                for token in raw_response:
                    response_text += token
                    
            latency_ms = (time.perf_counter() - start_time) * 1000
            total_latency_ms += latency_ms
            
            # Evaluar Guardrail (alcance)
            # Si era out_of_scope, esperamos que mencione el 911 o "no poseo ese procedimiento"
            is_guardrail_ok = True
            if expected_scope == "out_of_scope":
                # Comprobar que responda que no está o redirija al 911
                if "911" not in response_text and "No poseo ese procedimiento" not in response_text:
                    is_guardrail_ok = False
            else:
                # Si está dentro de alcance, no debería redirigir preventivamente
                if "comuníquate con el 911" in response_text:
                    is_guardrail_ok = False
                    
            if is_guardrail_ok:
                successful_guardrails += 1

            # Evaluar Keywords (calidad mínima de la respuesta)
            # En la PoC con mocks, evaluamos si al menos una keyword del mock coincide
            keyword_matches = [kw for kw in keywords if kw.lower() in response_text.lower()]
            has_keywords_ok = len(keyword_matches) > 0
            if has_keywords_ok:
                successful_keywords += 1
                
            results.append({
                "id": qid,
                "query": query,
                "latency_ms": latency_ms,
                "guardrail_ok": is_guardrail_ok,
                "keywords_ok": has_keywords_ok,
                "response_preview": response_text[:60].replace('\n', ' ') + "..."
            })
            
            g_status = "PASSED" if is_guardrail_ok else "FAILED"
            k_status = "PASSED" if has_keywords_ok else "FAILED"
            print(f"{qid:<3} | {query[:43] + '...':<45} | {latency_ms:6.1f} ms | {g_status:<10} | {k_status:<8}")

        await self.pipeline.on_shutdown()

        # Reporte final
        num_cases = len(self.dataset)
        avg_latency = total_latency_ms / num_cases if num_cases > 0 else 0
        guardrail_acc = (successful_guardrails / num_cases) * 100 if num_cases > 0 else 0
        keyword_acc = (successful_keywords / num_cases) * 100 if num_cases > 0 else 0

        print("="*80)
        print(" RESUMEN DE MÉTRICAS PoC")
        print("="*80)
        print(f"Número de casos evaluados: {num_cases}")
        print(f"Latencia promedio:          {avg_latency:.2f} ms")
        print(f"Precisión de Guardrails:   {guardrail_acc:.1f}% ({successful_guardrails}/{num_cases})")
        print(f"Precisión de Respuestas:    {keyword_acc:.1f}% ({successful_keywords}/{num_cases})")
        print("="*80)

if __name__ == "__main__":
    evaluator = RAGEvaluator("tests_eval/test_dataset.json")
    try:
        evaluator.load_dataset()
        asyncio.run(evaluator.run_evaluation())
    except Exception as e:
        print(f"[Evaluator - Error] Fallo al ejecutar evaluación: {e}")
