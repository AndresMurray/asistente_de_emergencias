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

### Promedio de 3 corridas — CON CONTEXTO (métrica válida)

| Modelo | TTFT promedio | Total promedio | tok/s promedio | Protocolo completo | Español |
|--------|---------------|----------------|----------------|--------------------|---------|
| **llama3.2:3b** | 370ms | **2.4s** | **44.3** | ⚠️ mezcla fases | ✅ |
| **qwen2.5:3b** | 372ms | 8.7s | 39.9 | ✅ siempre correcto | ✅ |
| ministral-3:3b | 664ms | 11.2s | 16.5 | ✅ | ✅ |
| phi3.5 | 711ms | 15.4s | 18.7 | ✅ | ⚠️ errores |
| llama3:8b | 712ms | 22.7s | 10.0 | ✅ | ✅ |

### Resultados — SIN CONTEXTO (solo referencia, no comparable entre modelos)

| Modelo | TTFT cold (rango) | tok/s |
|--------|-------------------|-------|
| llama3.2:3b | 5128–7499ms | 27–34 |
| phi3.5 | 4059–4732ms | 13–22 |
| qwen2.5:3b | 4827–17119ms | 13–35 |
| ministral-3:3b | 8887–9959ms | 12–15 |
| llama3:8b | 11854ms | 7.6 |

> TTFT cold incluye tiempo de carga del modelo en VRAM. Varía según estado del sistema. No usar para comparar modelos.

---

### Análisis final

- **llama3.2:3b**: Más rápido en tiempo total (2.4s promedio). En todas las corridas mezcló pasos bajo el título de FASE 1 en vez de listar las tres fases separadas. No es un defecto del modelo — el prompt de prueba no exige estructura por fases. Se corrige con prompt engineering explícito.
- **qwen2.5:3b**: TTFT prácticamente igual al líder (372ms vs 370ms — imperceptible). Tiempo total 3.6x más lento. En las tres corridas listó las tres fases correctamente y con detalle. Mejor calidad de protocolo del grupo.
- **ministral-3:3b**: Sólido y consistente. Respuestas limpias y bien formateadas. Tercer lugar claro.
- **phi3.5**: Descartado — errores de generación en español en todas las corridas ("involucidos", "segurthy", "atenzymedio") inaceptables para un sistema de emergencias.
- **llama3:8b**: Descartado — no entra en 4GB VRAM, corre en modo mixto GPU+CPU. 22.7s de respuesta total, inutilizable en tiempo real. Era el modelo default del proyecto pero no es viable para este hardware.

---

### Ranking final

| # | Modelo | Motivo |
|---|--------|--------|
| 1 | **llama3.2:3b** | Más rápido. El error de protocolo se resuelve con prompt engineering. |
| 2 | **qwen2.5:3b** | Mejor calidad de protocolo. Viable si el prompt engineering no alcanza para corregir llama. |
| 3 | ministral-3:3b | Correcto pero más lento. Reserva. |
| — | phi3.5 | Descartado. Errores de español consistentes. |
| — | llama3:8b | Descartado. No compatible con el hardware disponible. |

### Modelo seleccionado para producción: `llama3.2:3b`

Tiempo de respuesta dominante (2.4s promedio). TTFT idéntico a qwen2.5:3b. La diferencia de calidad de protocolo se delega al módulo de prompt engineering — no es responsabilidad del modelo LLM sino de cómo se construye el prompt.
