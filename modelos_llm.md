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

## Hardware de referencia para las pruebas

| Equipo | CPU | RAM | GPU |
|--------|-----|-----|-----|
| Principal (benchmark) | AMD Ryzen 7 | 16GB DDR5 | RTX 3050 4GB |
| Equipo del grupo | Varios | 8-16GB | Sin GPU |

---

## Resultados del benchmark (`benchmark.py`)

Hardware usado: AMD Ryzen 7 / 16GB DDR5 / RTX 3050 4GB VRAM

| Modelo | TTFT warm | tok/s | Sigue protocolo | Español | Veredicto |
|--------|-----------|-------|-----------------|---------|-----------|
| llama3.2:3b | **489ms** | **35.3** | SI | ✅ Sin errores | ✅ ELEGIDO |
| phi3.5 | 6984ms | 11.3 | SI | ⚠️ Errores de generación | ❌ Descartado |

> TTFT warm = tiempo al primer token con el modelo ya cargado en VRAM (cold start descartado, es costo único al arrancar Ollama).

### Notas del benchmark

- `phi3.5` genera palabras mal formadas en español ("segurthy", "involucidos") incluso siguiendo el protocolo
- `llama3.2:3b` con contexto inyectado responde en **489ms** al primer token y a **35 tok/s** — aceptable para tiempo real
- Ambos modelos **sí se quedan dentro del protocolo** cuando el contexto está inyectado correctamente
- El cold start (primera carga en VRAM) toma ~40s — normal, Ollama mantiene el modelo caliente en memoria

### Modelo seleccionado: `llama3.2:3b`
