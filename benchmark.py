"""
Benchmark de latencia y calidad para modelos LLM locales vía Ollama.

Métricas medidas:
- TTFT: Time To First Token (tiempo al primer token)
- Tiempo total de respuesta
- Tokens por segundo
- Seguimiento de contexto (no inventa pasos fuera del protocolo)

Uso:
    python benchmark.py
"""

import time
import json
import requests
from dataclasses import dataclass, field

OLLAMA_URL = "http://localhost:11434/api/generate"
MODELS = ["llama3.2:3b", "phi3.5", "qwen2.5:3b", "ministral-3:3b", "llama3:8b"]

PROMPT_SIN_CONTEXTO = (
    "Hay un accidente vial con heridos. ¿Cuáles son los primeros pasos?"
)

PROTOCOLO_SIMULADO = """
FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.
FASE 2 - ARRIBO AL LUGAR: Evaluar riesgos secundarios (derrames, incendios, tráfico).
FASE 3 - INTERVENCIÓN: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
"""

PROMPT_CON_CONTEXTO = (
    f"Usando ÚNICAMENTE el siguiente protocolo oficial, respondé qué hacer ante un accidente vial con heridos. "
    f"No agregues información que no esté en el protocolo.\n\n"
    f"PROTOCOLO:\n{PROTOCOLO_SIMULADO}\n\n"
    f"CONSULTA: Llegué a la escena de un accidente vial, hay 2 heridos. ¿Qué hago?"
)

PALABRAS_CLAVE_PROTOCOLO = [
    "toma de conocimiento",
    "arribo",
    "intervención",
    "ubicación",
    "lesionados",
    "riesgos",
]


@dataclass
class ResultadoBenchmark:
    modelo: str
    tipo_prompt: str
    ttft_ms: float = 0.0
    tiempo_total_s: float = 0.0
    tokens_generados: int = 0
    tokens_por_segundo: float = 0.0
    respuesta: str = ""
    sigue_protocolo: bool = False
    palabras_inventadas: list[str] = field(default_factory=list)
    error: str = ""


def ejecutar_stream(modelo: str, prompt: str) -> ResultadoBenchmark:
    resultado = ResultadoBenchmark(modelo=modelo, tipo_prompt="")
    payload = {
        "model": modelo,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": 0.1, "num_predict": 512},
    }

    try:
        t_inicio = time.perf_counter()
        ttft_registrado = False
        tokens: list[str] = []

        response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=(10, 120))

        if response.status_code != 200:
            resultado.error = f"HTTP {response.status_code}"
            return resultado

        for line in response.iter_lines():
            if not line:
                continue
            data = json.loads(line.decode("utf-8"))
            token = data.get("response", "")

            if token and not ttft_registrado:
                resultado.ttft_ms = (time.perf_counter() - t_inicio) * 1000
                ttft_registrado = True

            tokens.append(token)

            if data.get("done"):
                break

        t_fin = time.perf_counter()
        resultado.respuesta = "".join(tokens)
        resultado.tokens_generados = len(tokens)
        resultado.tiempo_total_s = t_fin - t_inicio
        resultado.tokens_por_segundo = (
            resultado.tokens_generados / resultado.tiempo_total_s
            if resultado.tiempo_total_s > 0
            else 0
        )

    except requests.exceptions.ConnectionError:
        resultado.error = "Ollama no está corriendo en http://localhost:11434"
    except Exception as e:
        resultado.error = str(e)

    return resultado


def evaluar_seguimiento_protocolo(resultado: ResultadoBenchmark) -> None:
    respuesta_lower = resultado.respuesta.lower()
    encontradas = [p for p in PALABRAS_CLAVE_PROTOCOLO if p in respuesta_lower]
    resultado.sigue_protocolo = len(encontradas) >= 2


def imprimir_resultado(r: ResultadoBenchmark, numero: int) -> None:
    print(f"\n{'─'*60}")
    print(f"  [{numero}] {r.modelo.upper()} — {r.tipo_prompt}")
    print(f"{'─'*60}")

    if r.error:
        print(f"  ERROR: {r.error}")
        return

    print(f"  TTFT (primer token):  {r.ttft_ms:.0f} ms")
    print(f"  Tiempo total:         {r.tiempo_total_s:.2f} s")
    print(f"  Tokens generados:     {r.tokens_generados}")
    print(f"  Velocidad:            {r.tokens_por_segundo:.1f} tok/s")
    if r.tipo_prompt == "CON CONTEXTO":
        protocolo_str = "SI" if r.sigue_protocolo else "NO"
        print(f"  Sigue protocolo:      {protocolo_str}")
    print(f"\n  Respuesta:\n")
    for linea in r.respuesta.strip().split("\n"):
        print(f"    {linea}")


def imprimir_tabla_resumen(resultados: list[ResultadoBenchmark]) -> None:
    print(f"\n\n{'═'*60}")
    print("  RESUMEN COMPARATIVO")
    print(f"{'═'*60}")
    print(f"  {'Modelo':<18} {'Prompt':<15} {'TTFT':>8} {'Total':>8} {'tok/s':>8} {'Protocolo':>10}")
    print(f"  {'─'*18} {'─'*15} {'─'*8} {'─'*8} {'─'*8} {'─'*10}")
    for r in resultados:
        if r.error:
            print(f"  {r.modelo:<18} {r.tipo_prompt:<15} {'ERROR':>8}")
            continue
        protocolo = ("SI" if r.sigue_protocolo else "NO") if r.tipo_prompt == "CON CONTEXTO" else "—"
        print(
            f"  {r.modelo:<18} {r.tipo_prompt:<15} "
            f"{r.ttft_ms:>7.0f}ms {r.tiempo_total_s:>7.1f}s "
            f"{r.tokens_por_segundo:>7.1f} {protocolo:>10}"
        )
    print(f"{'═'*60}\n")


def main() -> None:
    print("\n" + "═" * 60)
    print("  BENCHMARK LLM LOCAL — RAG Emergencias Viales")
    print("═" * 60)
    print(f"  Modelos: {', '.join(MODELS)}")
    print(f"  Endpoint: {OLLAMA_URL}")
    print("  Cada modelo se prueba con y sin contexto de protocolo.")
    print("═" * 60)

    resultados: list[ResultadoBenchmark] = []
    contador = 1

    for modelo in MODELS:
        for tipo, prompt in [("SIN CONTEXTO", PROMPT_SIN_CONTEXTO), ("CON CONTEXTO", PROMPT_CON_CONTEXTO)]:
            print(f"\n  Probando {modelo} [{tipo}]...", flush=True)
            r = ejecutar_stream(modelo, prompt)
            r.tipo_prompt = tipo
            if tipo == "CON CONTEXTO":
                evaluar_seguimiento_protocolo(r)
            imprimir_resultado(r, contador)
            resultados.append(r)
            contador += 1

    imprimir_tabla_resumen(resultados)


if __name__ == "__main__":
    main()
