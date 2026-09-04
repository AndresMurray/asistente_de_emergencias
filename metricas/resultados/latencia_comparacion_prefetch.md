# Comparación de latencia

| Corrida | p50 E2E (ms) | Δ vs baseline (ms) | Mejora |
| --- | ---: | ---: | ---: |
| baseline (metricas/resultados/latencia_raw/turnos_fijo_preemptivo_hemorragia.jsonl) | 2155.143 | — | — |
| metricas/resultados/latencia_raw/rag_prefetch_hemorragia.jsonl | 5712.649 | 3557.506 | -165.07% |

## Etapas p50: metricas/resultados/latencia_raw/rag_prefetch_hemorragia.jsonl

| Grupo | Métrica | Baseline | Candidata | Δ ms |
| --- | --- | ---: | ---: | ---: |
| all | transcription_delay_ms | 236.017 | 306.772 | 70.755 |
| all | end_of_turn_delay_ms | 631.878 | 2501.17 | 1869.292 |
| all | on_user_turn_completed_delay_ms | 0.009 | 0.022 | 0.013 |
| all | e2e_latency_ms | 2155.143 | 5712.649 | 3557.506 |
| all | llm_node_ttft_ms | 1206.545 | 1108.845 | -97.7 |
| all | tts_node_ttfb_ms | 303.5 | 256.589 | -46.911 |
| all | playback_latency_ms | 85.318 | 82.232 | -3.086 |
| rag | transcription_delay_ms | 366.282 | 290.432 | -75.85 |
| rag | end_of_turn_delay_ms | 631.878 | 2500.88 | 1869.002 |
| rag | on_user_turn_completed_delay_ms | 2.811 | 1.869 | -0.942 |
| rag | e2e_latency_ms | 8620.999 | 7532.64 | -1088.359 |
| rag | llm_node_ttft_ms | 1152.451 | 950.475 | -201.976 |
| rag | tts_node_ttfb_ms | 296.087 | 251.53 | -44.557 |
| rag | playback_latency_ms | 98.348 | 42.252 | -56.096 |
| no_rag | transcription_delay_ms | 222.677 | 329.982 | 107.305 |
| no_rag | end_of_turn_delay_ms | 829.716 | 2501.17 | 1671.454 |
| no_rag | on_user_turn_completed_delay_ms | 0.009 | 0.022 | 0.013 |
| no_rag | e2e_latency_ms | 1998.064 | 4762.791 | 2764.727 |
| no_rag | llm_node_ttft_ms | 1289.67 | 1861.23 | 571.56 |
| no_rag | tts_node_ttfb_ms | 318.31 | 258.311 | -59.999 |
| no_rag | playback_latency_ms | 81.26 | 87.104 | 5.844 |
| cold | transcription_delay_ms | 366.282 | 306.772 | -59.51 |
| cold | end_of_turn_delay_ms | 631.878 | 2500.559 | 1868.681 |
| cold | on_user_turn_completed_delay_ms | 2.811 | 3.717 | 0.906 |
| cold | e2e_latency_ms | 8620.999 | 9352.631 | 731.632 |
| cold | llm_node_ttft_ms | 1152.451 | 1108.845 | -43.606 |
| cold | tts_node_ttfb_ms | 296.087 | 256.589 | -39.498 |
| cold | playback_latency_ms | 98.348 | 2.273 | -96.075 |
| warm | transcription_delay_ms | 222.677 | 302.037 | 79.36 |
| warm | end_of_turn_delay_ms | 829.716 | 2501.186 | 1671.47 |
| warm | on_user_turn_completed_delay_ms | 0.009 | 0.021 | 0.012 |
| warm | e2e_latency_ms | 1998.064 | 5237.72 | 3239.656 |
| warm | llm_node_ttft_ms | 1289.67 | 1326.668 | 36.998 |
| warm | tts_node_ttfb_ms | 318.31 | 252.391 | -65.919 |
| warm | playback_latency_ms | 81.26 | 84.668 | 3.408 |
| rag_stages | total | 1745.0 | 863.0 | -882.0 |
| rag_stages | embedding | 1189.0 | 416.0 | -773.0 |
| rag_stages | vector | 555.0 | 446.0 | -109.0 |
| rag_stages | rerank | — | — | — |

Configuración: `[{"stt_model": "deepgram/nova-3", "stt_language": "es", "llm_model": "openai/gpt-4.1-mini", "tts_model": "cartesia/sonic-3.6", "endpointing": {"mode": "fixed", "max_delay": 2.5, "min_delay": 0.3}, "preemptive_tts": true, "rag_prefetch_critical": true}]`
