# Comparación de latencia

| Corrida | p50 E2E (ms) | Δ vs baseline (ms) | Mejora |
| --- | ---: | ---: | ---: |
| baseline (metricas/resultados/latencia_raw/turnos_fijo_preemptivo_hemorragia.jsonl) | 2155.143 | — | — |
| metricas/resultados/latencia_raw/stt_flux_hemorragia.jsonl | 2744.467 | 589.324 | -27.35% |

## Etapas p50: metricas/resultados/latencia_raw/stt_flux_hemorragia.jsonl

| Grupo | Métrica | Baseline | Candidata | Δ ms |
| --- | --- | ---: | ---: | ---: |
| all | transcription_delay_ms | 236.017 | 0.0 | -236.017 |
| all | end_of_turn_delay_ms | 631.878 | 0.213 | -631.665 |
| all | on_user_turn_completed_delay_ms | 0.009 | 0.011 | 0.002 |
| all | e2e_latency_ms | 2155.143 | 2744.467 | 589.324 |
| all | llm_node_ttft_ms | 1206.545 | 792.475 | -414.07 |
| all | tts_node_ttfb_ms | 303.5 | 301.163 | -2.337 |
| all | playback_latency_ms | 85.318 | 12.246 | -73.072 |
| rag | transcription_delay_ms | 366.282 | 0.0 | -366.282 |
| rag | end_of_turn_delay_ms | 631.878 | 0.185 | -631.693 |
| rag | on_user_turn_completed_delay_ms | 2.811 | 2.806 | -0.005 |
| rag | e2e_latency_ms | 8620.999 | 8909.73 | 288.731 |
| rag | llm_node_ttft_ms | 1152.451 | 688.819 | -463.632 |
| rag | tts_node_ttfb_ms | 296.087 | 269.949 | -26.138 |
| rag | playback_latency_ms | 98.348 | 6.314 | -92.034 |
| no_rag | transcription_delay_ms | 222.677 | 0.0 | -222.677 |
| no_rag | end_of_turn_delay_ms | 829.716 | 1.055 | -828.661 |
| no_rag | on_user_turn_completed_delay_ms | 0.009 | 0.009 | 0.0 |
| no_rag | e2e_latency_ms | 1998.064 | 1922.688 | -75.376 |
| no_rag | llm_node_ttft_ms | 1289.67 | 1040.244 | -249.426 |
| no_rag | tts_node_ttfb_ms | 318.31 | 672.393 | 354.083 |
| no_rag | playback_latency_ms | 81.26 | 46.119 | -35.141 |
| cold | transcription_delay_ms | 366.282 | — | — |
| cold | end_of_turn_delay_ms | 631.878 | — | — |
| cold | on_user_turn_completed_delay_ms | 2.811 | — | — |
| cold | e2e_latency_ms | 8620.999 | — | — |
| cold | llm_node_ttft_ms | 1152.451 | — | — |
| cold | tts_node_ttfb_ms | 296.087 | — | — |
| cold | playback_latency_ms | 98.348 | — | — |
| warm | transcription_delay_ms | 222.677 | 0.0 | -222.677 |
| warm | end_of_turn_delay_ms | 829.716 | 0.213 | -829.503 |
| warm | on_user_turn_completed_delay_ms | 0.009 | 0.011 | 0.002 |
| warm | e2e_latency_ms | 1998.064 | 2744.467 | 746.403 |
| warm | llm_node_ttft_ms | 1289.67 | 792.475 | -497.195 |
| warm | tts_node_ttfb_ms | 318.31 | 301.163 | -17.147 |
| warm | playback_latency_ms | 81.26 | 12.246 | -69.014 |
| rag_stages | total | 1745.0 | 1637.0 | -108.0 |
| rag_stages | embedding | 1189.0 | 1138.0 | -51.0 |
| rag_stages | vector | 555.0 | 498.0 | -57.0 |
| rag_stages | rerank | — | — | — |

Configuración: `[{"stt_model": "deepgram/flux-general-multi", "stt_language": "multi", "llm_model": "openai/gpt-4.1-mini", "tts_model": "cartesia/sonic-3.6", "endpointing": {"mode": "fixed", "max_delay": 2.5, "min_delay": 0.0}, "preemptive_tts": true, "rag_prefetch_critical": false}, {"stt_model": "deepgram/flux-general-multi", "stt_language": "multi", "llm_model": "openai/gpt-4.1-mini", "tts_model": "cartesia/sonic-3.6", "endpointing": {"mode": "fixed", "max_delay": 2.5, "min_delay": 0.0}, "preemptive_tts": true, "rag_prefetch_critical": false}]`
