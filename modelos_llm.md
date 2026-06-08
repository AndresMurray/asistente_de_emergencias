# Modelos LLM — Evaluación Local

Modelos probados para el RAG de emergencias viales. Todos corren vía Ollama.

## Criterios de selección

- Debe funcionar en hardware sin GPU (equipos del equipo)
- Latencia aceptable al primer token en CPU
- Español correcto sin alucinaciones
- Sigue instrucciones del protocolo sin inventar pasos

---

## Modelos instalados

### llama3.2:3b
- **Tamaño:** 2.0 GB
- **Parámetros:** 3B
- **Descarga:** `ollama pull llama3.2:3b`
- **Hardware mínimo:** 4GB RAM (CPU), funciona en GPU con 2GB VRAM
- **Español:** Limpio y coherente
- **Notas:** Respuestas concisas, buena calidad para el tamaño

---

### phi3.5
- **Tamaño:** 2.2 GB
- **Parámetros:** 3.8B
- **Descarga:** `ollama pull phi3.5`
- **Hardware mínimo:** 4GB RAM (CPU), funciona en GPU con 2.3GB VRAM
- **Español:** Presenta errores gramaticales y palabras inventadas
- **Notas:** Respuestas más largas pero menos precisas en español

---

### qwen2.5:3b
- **Tamaño:** 1.9 GB
- **Parámetros:** 3B
- **Descarga:** `ollama pull qwen2.5:3b`
- **Hardware mínimo:** 4GB RAM (CPU), funciona en GPU con 2GB VRAM
- **Español:** Por evaluar — históricamente fuerte en multilingüe
- **Notas:** Alibaba, entrenado con foco en instrucción y multilingüe

---

### ministral-3:3b
- **Tamaño:** 3.0 GB
- **Parámetros:** 3B
- **Descarga:** `ollama pull ministral-3:3b`
- **Hardware mínimo:** 6GB RAM (CPU), funciona en GPU con 3GB VRAM
- **Español:** Por evaluar
- **Notas:** Mistral AI, familia Ministral diseñada para edge devices. El más pesado del grupo

---

## Hardware de referencia para las pruebas

| Equipo | CPU | RAM | GPU |
|--------|-----|-----|-----|
| Principal (benchmark) | AMD Ryzen 7 | 16GB DDR5 | RTX 3050 4GB |
| Equipo del grupo | Varios | 8-16GB | Sin GPU |

---

## Resultados del benchmark (`benchmark.py`)

Hardware usado: AMD Ryzen 7 / 16GB DDR5 / RTX 3050 4GB VRAM

### Metodología

El benchmark corre dos pruebas por modelo en orden secuencial:
1. **SIN CONTEXTO** → cold start: Ollama carga el modelo en VRAM desde cero. TTFT incluye tiempo de carga — **no comparable entre modelos**.
2. **CON CONTEXTO** → warm: el modelo ya está en VRAM. **Esta es la métrica válida para comparar.**

Cuando el benchmark pasa al siguiente modelo, Ollama desaloja el anterior de VRAM para cargar el nuevo. Cada modelo corre en VRAM exclusiva, sin competencia con otros modelos. La comparación CON CONTEXTO es justa.

---

### Resultados — CON CONTEXTO (métrica válida)

| Modelo | TTFT warm | Tiempo total | tok/s | Sigue protocolo | Español | Observaciones |
|--------|-----------|--------------|-------|-----------------|---------|---------------|
| llama3.2:3b | 470ms | **2.9s** | **36.4** | ✅ | ✅ | Omitió mencionar FASE 3 explícitamente |
| qwen2.5:3b | **408ms** | 11.1s | 22.7 | ✅ | ✅ | Respuesta más detallada y precisa |
| ministral-3:3b | 778ms | 16.1s | 10.8 | ✅ | ✅ | Limpia y bien formateada |
| phi3.5 | 895ms | 17.4s | 13.3 | ✅ | ⚠️ | Errores de generación en español |

### Resultados — SIN CONTEXTO (solo referencia, no comparable)

| Modelo | TTFT cold | tok/s |
|--------|-----------|-------|
| llama3.2:3b | 5128ms | 27.9 |
| phi3.5 | 4059ms | 13.3 |
| qwen2.5:3b | 17119ms | 13.6 |
| ministral-3:3b | 9786ms | 10.1 |

> Los TTFT cold varían según el orden de ejecución y el estado de VRAM al momento de carga. No usar para comparar modelos.

---

### Análisis

- **llama3.2:3b**: El más rápido por amplio margen (2.9s total, 36.4 tok/s). En la prueba con contexto omitió enunciar la FASE 3 explícitamente — señal de que el prompt del RAG necesita instrucción explícita para listar todas las fases (responsabilidad del módulo de prompt engineering).
- **qwen2.5:3b**: TTFT casi idéntico (408ms vs 470ms, diferencia imperceptible para el usuario), pero respuesta total 4x más lenta (11.1s). Mejor calidad y precisión en el seguimiento del protocolo.
- **ministral-3:3b**: Correcto y limpio, pero el más lento del grupo en tok/s (10.8). No justifica su tamaño (3GB).
- **phi3.5**: Descartado — errores de generación en español ("segurthy", "involucidos") inaceptables para un sistema de emergencias.

### Modelo seleccionado: `llama3.2:3b`

Velocidad dominante para tiempo real. La omisión de FASE 3 se resuelve con prompt engineering, no cambiando el modelo.
