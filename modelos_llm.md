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
- **Español:** Correcto, bien formateado
- **Notas:** Mistral AI, familia Ministral diseñada para edge devices. El más pesado del grupo

---

### llama3:8b
- **Tamaño:** 4.7 GB
- **Parámetros:** 8B
- **Descarga:** `ollama pull llama3:8b`
- **Hardware mínimo:** 8GB RAM (CPU), requiere 5GB+ VRAM para correr completo en GPU
- **Español:** Bueno
- **Notas:** Modelo default original del proyecto. No entra en 4GB VRAM — corre en modo mixto GPU+CPU. Descartado para este hardware.

---

### gemma2:2b
- **Tamaño:** 1.6 GB
- **Parámetros:** 2B
- **Descarga:** `ollama pull gemma2:2b`
- **Hardware mínimo:** 4GB RAM (CPU), funciona en GPU con 2GB VRAM
- **Español:** Limpio, bien formateado, sin errores
- **Notas:** Google DeepMind. El más pequeño del grupo. Más rápido en warm que llama3.2:3b en total y tok/s. Lista las 3 fases del protocolo correctamente con sus labels. **Modelo seleccionado para producción.**

---

### gemma3:4b
- **Tamaño:** 3.3 GB
- **Parámetros:** 4B
- **Descarga:** `ollama pull gemma3:4b`
- **Hardware mínimo:** 6GB RAM (CPU), funciona en GPU con 4GB VRAM (justo)
- **Español:** Limpio
- **Notas:** Sucesor de gemma2. Decepciona — 2.6x más lento que gemma2:2b (3.9s vs 1.5s) y solo 20 tok/s. Además droppeó los labels de fase en la respuesta, listando solo las acciones sin encabezados. Más parámetros no implica mejor resultado para esta tarea. Descartado.

---

### qwen2.5:1.5b
- **Tamaño:** 1.0 GB
- **Parámetros:** 1.5B
- **Descarga:** `ollama pull qwen2.5:1.5b`
- **Hardware mínimo:** 3GB RAM (CPU), funciona en GPU con 1.5GB VRAM
- **Español:** Correcto
- **Notas:** TTFT más rápido del grupo (269ms) pero generó 355 tokens — 4x más que gemma2:2b. Alucinó pasos que no están en el protocolo ("cerrar la avenida afectada", "transportados en un vehículo seguro para traslado al hospital"). Inaceptable para sistema de emergencias. Descartado.

---

### phi4-mini
- **Tamaño:** 2.5 GB
- **Parámetros:** 3.8B
- **Descarga:** `ollama pull phi4-mini`
- **Hardware mínimo:** 5GB RAM (CPU), funciona en GPU con 3GB VRAM
- **Español:** Limpio, sin errores (mejora considerable sobre phi3.5)
- **Notas:** Microsoft. Respuestas limpias con fases correctas y sin alucinaciones. Pero 3.4s total — 2.3x más lento que gemma2:2b. Cold start muy alto (20s). No supera al líder en ninguna métrica. Descartado.

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

### Resultados — CON CONTEXTO (métrica válida para comparar)

> tok/s medido con `eval_count` / `eval_duration` de Ollama (valores reales). Corrida única warm.

| Modelo | TTFT | Total | tok/s | Protocolo | Español | Observación |
|--------|------|-------|-------|-----------|---------|-------------|
| **gemma2:2b** | 325ms | **1.5s** | **80.4** | ✅ 3 fases con labels | ✅ | Ganador |
| **llama3.2:3b** | 337ms | 1.7s | 73.7 | ⚠️ mezcla fases | ✅ | Tratable con prompt engineering |
| phi4-mini | 384ms | 3.4s | 37.8 | ✅ 3 fases con labels | ✅ | Buena calidad, 2.3x más lento |
| qwen2.5:3b | 286ms | 3.8s | 73.4 | ✅ 3 fases con labels | ✅ | TTFT rápido, total lento |
| gemma3:4b | 814ms | 3.9s | 20.3 | ⚠️ sin labels de fase | ✅ | Peor que su predecesor gemma2 |
| ministral-3:3b | 473ms | 5.5s | 27.0 | ✅ 3 fases con labels | ✅ | Sólido, lento |
| qwen2.5:1.5b | 269ms | 6.3s | 59.2 | ⚠️ alucinaciones | ✅ | Inventa pasos fuera del protocolo |
| llama3:8b | 704ms | 6.9s | 10.9 | ⚠️ solo fase 1 | ✅ | Inconsistente, hardware limitante |
| phi3.5 | 383ms | 11.1s | 25.8 | ✅ | ⚠️ errores | "involucidos", descartado |

### Resultados — SIN CONTEXTO (solo referencia, no comparable entre modelos)

| Modelo | TTFT cold | Total | tok/s |
|--------|-----------|-------|-------|
| qwen2.5:1.5b | 2968ms | 10.3s | 59.1 |
| phi3.5 | 4955ms | 23.4s | 27.8 |
| qwen2.5:3b | 5454ms | 11.0s | 72.3 |
| gemma2:2b | 5865ms | 12.0s | 79.0 |
| llama3.2:3b | 6160ms | 13.1s | 73.1 |
| ministral-3:3b | 9026ms | 28.1s | 26.9 |
| llama3:8b | 9951ms | 57.8s | 10.7 |
| gemma3:4b | 11371ms | 37.8s | 19.4 |
| phi4-mini | 20909ms | 30.2s | 37.5 |

> TTFT cold incluye tiempo de carga del modelo en VRAM. Varía mucho según el estado del sistema. No usar para comparar modelos entre sí.

---

### Análisis final

- **gemma2:2b**: Ganador confirmado tras evaluar 9 modelos. 1.5s total, 80 tok/s, 3 fases con labels correctos, 1.6GB. El cold start alto (5.9s en esta corrida) es irrelevante en producción — Ollama mantiene el modelo en VRAM entre requests.
- **llama3.2:3b**: Segundo lugar por velocidad (1.7s). Sigue mezclando las fases bajo FASE 1 — resoluble con prompt engineering explícito (responsabilidad del Integrante 4).
- **phi4-mini**: Sorpresa positiva — respuesta más limpia y estructurada que la mayoría, sin alucinaciones. Pero 3.4s total lo deja fuera de la carrera principal. Buena opción de reserva si la calidad del prompt engineering lo requiere.
- **qwen2.5:3b**: TTFT rápido (286ms) pero total lento (3.8s). Queda desplazado por phi4-mini en calidad y por gemma2:2b en velocidad.
- **gemma3:4b**: Decepción — es el sucesor de gemma2 pero fue 2.6x más lento y además droppeó los labels de fase. Demuestra que más parámetros no garantiza mejor resultado en tareas específicas.
- **qwen2.5:1.5b**: TTFT más rápido del grupo (269ms) pero **descartado por alucinaciones** — inventó pasos que no están en el protocolo. Inaceptable para un sistema de emergencias donde una instrucción inventada puede costar vidas.
- **ministral-3:3b**: Correcto y bien formateado, pero 5.5s lo deja como reserva lejana.
- **phi3.5**: Descartado definitivamente — errores de español en todas las corridas.
- **llama3:8b**: Descartado — modo mixto GPU+CPU, inconsistente en seguimiento de protocolo.

---

### Ranking final

| # | Modelo | Total | tok/s | Motivo |
|---|--------|-------|-------|--------|
| 1 | **gemma2:2b** | 1.5s | 80 | Más rápido, protocolo correcto con labels, modelo más pequeño. |
| 2 | **llama3.2:3b** | 1.7s | 74 | Prácticamente igual en velocidad. Mezcla fases — resoluble con prompt engineering. |
| 3 | **phi4-mini** | 3.4s | 38 | Mejor calidad de respuesta del grupo, sin alucinaciones. Reserva de calidad. |
| 4 | **qwen2.5:3b** | 3.8s | 73 | TTFT rápido pero total lento. Desplazado por phi4-mini en calidad. |
| — | gemma3:4b | 3.9s | 20 | Descartado. Más lento que su predecesor, pierde labels de fase. |
| — | ministral-3:3b | 5.5s | 27 | Correcto pero demasiado lento para producción. |
| — | qwen2.5:1.5b | 6.3s | 59 | Descartado. Alucinaciones de protocolo — inaceptable para emergencias. |
| — | llama3:8b | 6.9s | 11 | Descartado. Hardware y comportamiento inconsistente. |
| — | phi3.5 | 11.1s | 26 | Descartado. Errores de español en todas las corridas. |

### Modelo seleccionado para producción: `gemma2:2b`

Confirmado tras evaluar 9 modelos. Más rápido en tiempo total (1.5s), más alto en tok/s (80), protocolo correcto con labels, footprint más pequeño (1.6GB). Ningún modelo nuevo lo superó en ninguna métrica relevante.
