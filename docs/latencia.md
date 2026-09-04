# Medición de latencia

La instrumentación no altera el comportamiento productivo por defecto. Activa
la escritura local al definir `LATENCY_RUN_ID`; el texto de las conversaciones
queda fuera de los resultados salvo con `LATENCY_INCLUDE_TEXT=1`.

El perfil local seleccionado tras las pruebas usa endpointing fijo (`0.3–2.5`
segundos) y TTS preemptivo de hasta 10 segundos. Puede revertirse sin cambios
de código con `ENDPOINTING_MODE=dynamic PREEMPTIVE_TTS=false`.

## Baseline local

Usá una sesión nueva por escenario y repetí cada escenario dos veces. Mantené
el mismo headset, red y persona que lee los turnos.

```bash
LATENCY_RUN_ID=baseline LATENCY_VARIANT=actual LATENCY_SCENARIO=inconsciente_no_respira \
  .venv/bin/python agent.py console --record
```

Los escenarios sugeridos están en `ensayo.py`: `fuera_de_alcance`,
`inconsciente_no_respira`, `hemorragia` e `inconsciente_respira`.

## Perfiles a comparar

El perfil de turn-taking no toca modelos:

```bash
LATENCY_RUN_ID=turnos LATENCY_VARIANT=fijo_preemptivo \
ENDPOINTING_MODE=fixed ENDPOINTING_MIN_DELAY=0.3 ENDPOINTING_MAX_DELAY=2.5 \
PREEMPTIVE_TTS=true PREEMPTIVE_MAX_SPEECH_DURATION=10 \
  .venv/bin/python agent.py console --record
```

Para que la comparación sea válida contra la corrida RAG ya tomada, corré este
perfil con `hemorragia` y repetí literalmente el mismo guion. Incluí una frase
con una pausa natural de uno a dos segundos y una interrupción durante la
respuesta; si el agente corta la frase antes de tiempo, la corrida queda
descartada aunque baje el p50.

```bash
LATENCY_RUN_ID=turnos_fijo_preemptivo_hemorragia \
LATENCY_VARIANT=fijo_preemptivo LATENCY_SCENARIO=hemorragia \
ENDPOINTING_MODE=fixed ENDPOINTING_MIN_DELAY=0.3 ENDPOINTING_MAX_DELAY=2.5 \
PREEMPTIVE_TTS=true PREEMPTIVE_MAX_SPEECH_DURATION=10 \
  uv run agent.py console --record
```

Al cerrar la sesión, generá el reporte y comparalo contra la misma familia de
datos crudos (no contra reportes de escenarios distintos):

```bash
uv run python -m metricas.latencia summarize \
  metricas/resultados/latencia_raw/turnos_fijo_preemptivo_hemorragia.jsonl \
  --json-out metricas/resultados/latencia_turnos_fijo_preemptivo_hemorragia.json \
  --markdown-out metricas/resultados/latencia_turnos_fijo_preemptivo_hemorragia.md

uv run python -m metricas.latencia compare \
  metricas/resultados/latencia_raw/rag_hemorragia.jsonl \
  metricas/resultados/latencia_raw/turnos_fijo_preemptivo_hemorragia.jsonl \
  --markdown-out metricas/resultados/latencia_comparacion_turnos.md
```

Para Flux, usá un escenario crítico y verificá literalmente la transcripción:

```bash
LATENCY_RUN_ID=stt-flux LATENCY_VARIANT=flux \
STT_MODEL=deepgram/flux-general-multi STT_LANGUAGE=multi \
ENDPOINTING_MIN_DELAY=0 \
  .venv/bin/python agent.py console --record
```

El prefetch se compara por separado y sigue apagado por defecto:

```bash
LATENCY_RUN_ID=rag-prefetch LATENCY_VARIANT=prefetch RAG_PREFETCH_CRITICAL=true \
  .venv/bin/python agent.py console --record
```

Antes de llevar un LLM a audio, corré `test_guion_expo.py` con
`openai/gpt-4.1-mini`, `openai/gpt-4.1-nano` y `openai/gpt-4o-mini`. Sólo los
modelos que aprueben todas las reglas clínicas pasan a la comparación de voz.

## Reportes

```bash
.venv/bin/python -m metricas.latencia summarize \
  metricas/resultados/latencia_raw/baseline.jsonl \
  --json-out metricas/resultados/latencia_baseline.json \
  --markdown-out metricas/resultados/latencia_baseline.md

.venv/bin/python -m metricas.latencia compare \
  metricas/resultados/latencia_raw/baseline.jsonl \
  metricas/resultados/latencia_raw/turnos.jsonl \
  --json-out metricas/resultados/latencia_comparacion.json \
  --markdown-out metricas/resultados/latencia_comparacion.md
```

El resumen divide los segmentos útiles entre `rag`, `no_rag`, `cold` y `warm`.
La comparación agrega los p50 y deltas por etapa (EOU, STT, LLM, TTS, E2E y
RAG) junto con las configuraciones observadas. Los archivos de reporte sí se
pueden versionar; los JSONL crudos quedan ignorados.
`playback_latency` es una métrica del pipeline y no reemplaza la validación
perceptual ni el panel Agent Insights en Cloud.
