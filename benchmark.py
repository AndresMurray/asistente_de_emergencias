"""
Benchmark de latencia y calidad para modelos LLM locales vía Ollama.

Métricas medidas:
- TTFT: Time To First Token (tiempo al primer token)
- Tiempo total de respuesta
- Tokens por segundo
- Seguimiento de protocolo (menciona las fases del protocolo)
- Detección de pasos inventados (contenido que NO está en el protocolo)

Metodología:
- Warmup por modelo antes de medir: el primer request a un modelo paga su
  carga a VRAM, lo que infla el TTFT. Se hace un request mínimo previo.
- Cada condición se corre N_REPETICIONES veces y se reporta la mediana.

Uso:
    python benchmark.py
"""

import time
import json
import statistics
import requests
from dataclasses import dataclass, field

OLLAMA_URL = "http://localhost:11434/api/generate"
MODELS = ["llama3.2:3b", "phi3.5", "qwen2.5:3b", "ministral-3:3b", "llama3:8b", "gemma2:2b", "gemma3:4b", "qwen2.5:1.5b", "phi4-mini", "qwen3:8b"]
N_REPETICIONES = 3

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

# Marcadores de contenido típico de primeros auxilios que NO figura en el
# protocolo: si aparecen en la respuesta CON CONTEXTO, el modelo está inventando.
FRASES_FUERA_DE_PROTOCOLO = [
    "911",
    "112",
    "llamar a emergencia",
    "servicios de emergencia",
    "foto",
    "documentar",
    "rcp",
    "reanimación",
    "triángulo",
    "policía",
    "seguro",
    "torniquete",
    "venda",
    "luces de emergencia",
]


@dataclass
class ResultadoCorrida:
    """Métricas de UNA corrida individual contra Ollama."""

    modelo: str
    ttft_ms: float = 0.0
    tiempo_total_s: float = 0.0
    tokens_generados: int = 0
    tokens_por_segundo: float = 0.0
    respuesta: str = ""
    error: str = ""


@dataclass
class ResultadoBenchmark:
    """Agregado de N corridas para una condición (modelo + tipo de prompt)."""

    modelo: str
    tipo_prompt: str
    corridas: int = 0
    ttft_ms: float = 0.0            # mediana
    tiempo_total_s: float = 0.0     # mediana
    tokens_por_segundo: float = 0.0  # mediana
    respuesta: str = ""             # de la primera corrida exitosa
    sigue_protocolo: bool = False
    palabras_inventadas: list[str] = field(default_factory=list)
    error: str = ""


def warmup(modelo: str) -> str:
    """Carga el modelo a VRAM con un request mínimo. Devuelve error o ''."""
    payload = {
        "model": modelo,
        "prompt": "Hola",
        "stream": False,
        "options": {"num_predict": 1},
    }
    try:
        # timeout de lectura amplio: la carga a VRAM puede tardar
        response = requests.post(OLLAMA_URL, json=payload, timeout=(10, 300))
        if response.status_code != 200:
            return f"HTTP {response.status_code} en warmup"
        return ""
    except requests.exceptions.ConnectionError:
        return "Ollama no está corriendo en http://localhost:11434"
    except Exception as e:
        return str(e)


def ejecutar_stream(modelo: str, prompt: str) -> ResultadoCorrida:
    resultado = ResultadoCorrida(modelo=modelo)
    payload: dict = {
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
                # eval_count y eval_duration son los valores reales de Ollama
                eval_count = data.get("eval_count", 0)
                eval_duration_ns = data.get("eval_duration", 0)
                if eval_count and eval_duration_ns:
                    resultado.tokens_generados = eval_count
                    resultado.tokens_por_segundo = eval_count / (eval_duration_ns / 1e9)
                break

        t_fin = time.perf_counter()
        resultado.respuesta = "".join(tokens)
        resultado.tiempo_total_s = t_fin - t_inicio
        # fallback si Ollama no devolvió eval_count (no debería pasar)
        if resultado.tokens_generados == 0:
            resultado.tokens_generados = len(tokens)
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


def agregar_corridas(modelo: str, tipo_prompt: str, corridas: list[ResultadoCorrida]) -> ResultadoBenchmark:
    resultado = ResultadoBenchmark(modelo=modelo, tipo_prompt=tipo_prompt)
    exitosas = [c for c in corridas if not c.error]

    if not exitosas:
        resultado.error = corridas[0].error if corridas else "sin corridas"
        return resultado

    resultado.corridas = len(exitosas)
    resultado.ttft_ms = statistics.median(c.ttft_ms for c in exitosas)
    resultado.tiempo_total_s = statistics.median(c.tiempo_total_s for c in exitosas)
    resultado.tokens_por_segundo = statistics.median(c.tokens_por_segundo for c in exitosas)
    resultado.respuesta = exitosas[0].respuesta
    return resultado


def evaluar_calidad(resultado: ResultadoBenchmark, corridas: list[ResultadoCorrida]) -> None:
    """Evalúa protocolo e invenciones sobre TODAS las corridas exitosas.

    - sigue_protocolo: mayoría de corridas menciona >= 2 palabras clave
    - palabras_inventadas: unión de invenciones detectadas en cualquier corrida
    """
    exitosas = [c for c in corridas if not c.error]
    if not exitosas:
        return

    cumple = 0
    inventadas: set[str] = set()
    for c in exitosas:
        respuesta_lower = c.respuesta.lower()
        encontradas = [p for p in PALABRAS_CLAVE_PROTOCOLO if p in respuesta_lower]
        if len(encontradas) >= 2:
            cumple += 1
        inventadas.update(f for f in FRASES_FUERA_DE_PROTOCOLO if f in respuesta_lower)

    resultado.sigue_protocolo = cumple > len(exitosas) / 2
    resultado.palabras_inventadas = sorted(inventadas)


def imprimir_resultado(r: ResultadoBenchmark, numero: int) -> None:
    print(f"\n{'─'*60}")
    print(f"  [{numero}] {r.modelo.upper()} — {r.tipo_prompt}")
    print(f"{'─'*60}")

    if r.error:
        print(f"  ERROR: {r.error}")
        return

    print(f"  Corridas:             {r.corridas} (se reporta la mediana)")
    print(f"  TTFT (primer token):  {r.ttft_ms:.0f} ms")
    print(f"  Tiempo total:         {r.tiempo_total_s:.2f} s")
    print(f"  Velocidad:            {r.tokens_por_segundo:.1f} tok/s")
    if r.tipo_prompt == "CON CONTEXTO":
        protocolo_str = "SI" if r.sigue_protocolo else "NO"
        print(f"  Sigue protocolo:      {protocolo_str}")
        if r.palabras_inventadas:
            print(f"  Fuera de protocolo:   {', '.join(r.palabras_inventadas)}")
    print(f"\n  Respuesta (primera corrida):\n")
    for linea in r.respuesta.strip().split("\n"):
        print(f"    {linea}")


def imprimir_tabla_resumen(resultados: list[ResultadoBenchmark]) -> None:
    print(f"\n\n{'═'*72}")
    print("  RESUMEN COMPARATIVO (medianas)")
    print(f"{'═'*72}")
    print(f"  {'Modelo':<18} {'Prompt':<15} {'TTFT':>8} {'Total':>8} {'tok/s':>8} {'Protocolo':>10} {'Inventa':>8}")
    print(f"  {'─'*18} {'─'*15} {'─'*8} {'─'*8} {'─'*8} {'─'*10} {'─'*8}")
    for r in resultados:
        if r.error:
            print(f"  {r.modelo:<18} {r.tipo_prompt:<15} {'ERROR':>8}")
            continue
        if r.tipo_prompt == "CON CONTEXTO":
            protocolo = "SI" if r.sigue_protocolo else "NO"
            inventa = str(len(r.palabras_inventadas)) if r.palabras_inventadas else "—"
        else:
            protocolo = "—"
            inventa = "—"
        print(
            f"  {r.modelo:<18} {r.tipo_prompt:<15} "
            f"{r.ttft_ms:>7.0f}ms {r.tiempo_total_s:>7.1f}s "
            f"{r.tokens_por_segundo:>7.1f} {protocolo:>10} {inventa:>8}"
        )
    print(f"{'═'*72}\n")


def main() -> None:
    print("\n" + "═" * 60)
    print("  BENCHMARK LLM LOCAL — RAG Emergencias Viales")
    print("═" * 60)
    print(f"  Modelos: {', '.join(MODELS)}")
    print(f"  Endpoint: {OLLAMA_URL}")
    print(f"  Repeticiones por condición: {N_REPETICIONES} (se reporta mediana)")
    print("  Warmup previo por modelo para excluir la carga a VRAM del TTFT.")
    print("═" * 60)

    resultados: list[ResultadoBenchmark] = []
    contador = 1

    for modelo in MODELS:
        print(f"\n  Cargando {modelo} (warmup)...", flush=True)
        error_warmup = warmup(modelo)
        if error_warmup:
            for tipo in ("SIN CONTEXTO", "CON CONTEXTO"):
                r = ResultadoBenchmark(modelo=modelo, tipo_prompt=tipo, error=error_warmup)
                imprimir_resultado(r, contador)
                resultados.append(r)
                contador += 1
            continue

        for tipo, prompt in [("SIN CONTEXTO", PROMPT_SIN_CONTEXTO), ("CON CONTEXTO", PROMPT_CON_CONTEXTO)]:
            corridas: list[ResultadoCorrida] = []
            for i in range(N_REPETICIONES):
                print(f"  Probando {modelo} [{tipo}] corrida {i + 1}/{N_REPETICIONES}...", flush=True)
                corridas.append(ejecutar_stream(modelo, prompt))

            r = agregar_corridas(modelo, tipo, corridas)
            if tipo == "CON CONTEXTO":
                evaluar_calidad(r, corridas)
            imprimir_resultado(r, contador)
            resultados.append(r)
            contador += 1

    imprimir_tabla_resumen(resultados)


if __name__ == "__main__":
    main()


