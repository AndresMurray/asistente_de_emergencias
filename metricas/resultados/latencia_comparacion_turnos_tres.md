# Comparación de latencia

| Corrida | p50 E2E (ms) | Δ vs baseline (ms) | Mejora |
| --- | ---: | ---: | ---: |
| baseline (metricas/resultados/latencia_raw/turnos_fijo_sin_preemptivo_hemorragia.jsonl) | 6981.973 | — | — |
| metricas/resultados/latencia_raw/turnos_fijo_preemptivo_hemorragia.jsonl | 2155.143 | -4826.83 | 69.13% |

## Etapas p50: metricas/resultados/latencia_raw/turnos_fijo_preemptivo_hemorragia.jsonl

| Grupo | Métrica | Baseline | Candidata | Δ ms |
| --- | --- | ---: | ---: | ---: |
| all | transcription_delay_ms | 221.43 | 236.017 | 14.587 |
| all | end_of_turn_delay_ms | 1525.291 | 631.878 | -893.413 |
| all | on_user_turn_completed_delay_ms | 1.855 | 0.009 | -1.846 |
| all | e2e_latency_ms | 6981.973 | 2155.143 | -4826.83 |
| all | llm_node_ttft_ms | 1087.655 | 1206.545 | 118.89 |
| all | tts_node_ttfb_ms | 309.625 | 303.5 | -6.125 |
| all | playback_latency_ms | 59.264 | 85.318 | 26.054 |
| rag | transcription_delay_ms | 221.43 | 366.282 | 144.852 |
| rag | end_of_turn_delay_ms | 1525.291 | 631.878 | -893.413 |
| rag | on_user_turn_completed_delay_ms | 1.855 | 2.811 | 0.956 |
| rag | e2e_latency_ms | 6981.973 | 8620.999 | 1639.026 |
| rag | llm_node_ttft_ms | 1087.655 | 1152.451 | 64.796 |
| rag | tts_node_ttfb_ms | 309.625 | 296.087 | -13.538 |
| rag | playback_latency_ms | 59.264 | 98.348 | 39.084 |
| no_rag | transcription_delay_ms | — | 222.677 | — |
| no_rag | end_of_turn_delay_ms | — | 829.716 | — |
| no_rag | on_user_turn_completed_delay_ms | — | 0.009 | — |
| no_rag | e2e_latency_ms | — | 1998.064 | — |
| no_rag | llm_node_ttft_ms | — | 1289.67 | — |
| no_rag | tts_node_ttfb_ms | — | 318.31 | — |
| no_rag | playback_latency_ms | — | 81.26 | — |
| cold | transcription_delay_ms | 233.972 | 366.282 | 132.31 |
| cold | end_of_turn_delay_ms | 546.024 | 631.878 | 85.854 |
| cold | on_user_turn_completed_delay_ms | 3.67 | 2.811 | -0.859 |
| cold | e2e_latency_ms | 8731.698 | 8620.999 | -110.699 |
| cold | llm_node_ttft_ms | 1159.725 | 1152.451 | -7.274 |
| cold | tts_node_ttfb_ms | 319.266 | 296.087 | -23.179 |
| cold | playback_latency_ms | 31.776 | 98.348 | 66.572 |
| warm | transcription_delay_ms | 208.888 | 222.677 | 13.789 |
| warm | end_of_turn_delay_ms | 2504.558 | 829.716 | -1674.842 |
| warm | on_user_turn_completed_delay_ms | 0.039 | 0.009 | -0.03 |
| warm | e2e_latency_ms | 5232.248 | 1998.064 | -3234.184 |
| warm | llm_node_ttft_ms | 1015.586 | 1289.67 | 274.084 |
| warm | tts_node_ttfb_ms | 299.983 | 318.31 | 18.327 |
| warm | playback_latency_ms | 86.752 | 81.26 | -5.492 |
| rag_stages | total | 830.0 | 1745.0 | 915.0 |
| rag_stages | embedding | 367.0 | 1189.0 | 822.0 |
| rag_stages | vector | 463.0 | 555.0 | 92.0 |
| rag_stages | rerank | — | — | — |

Configuración: `[{"stt_model": "deepgram/nova-3", "stt_language": "es", "llm_model": "openai/gpt-4.1-mini", "tts_model": "cartesia/sonic-3.6", "endpointing": {"mode": "fixed", "max_delay": 2.5, "min_delay": 0.3}, "preemptive_tts": true, "rag_prefetch_critical": false}]`
| metricas/resultados/latencia_raw/rag_prefetch_hemorragia.jsonl | 5712.649 | -1269.324 | 18.18% |

## Etapas p50: metricas/resultados/latencia_raw/rag_prefetch_hemorragia.jsonl

| Grupo | Métrica | Baseline | Candidata | Δ ms |
| --- | --- | ---: | ---: | ---: |
| all | transcription_delay_ms | 221.43 | 306.772 | 85.342 |
| all | end_of_turn_delay_ms | 1525.291 | 2501.17 | 975.879 |
| all | on_user_turn_completed_delay_ms | 1.855 | 0.022 | -1.833 |
| all | e2e_latency_ms | 6981.973 | 5712.649 | -1269.324 |
| all | llm_node_ttft_ms | 1087.655 | 1108.845 | 21.19 |
| all | tts_node_ttfb_ms | 309.625 | 256.589 | -53.036 |
| all | playback_latency_ms | 59.264 | 82.232 | 22.968 |
| rag | transcription_delay_ms | 221.43 | 290.432 | 69.002 |
| rag | end_of_turn_delay_ms | 1525.291 | 2500.88 | 975.589 |
| rag | on_user_turn_completed_delay_ms | 1.855 | 1.869 | 0.014 |
| rag | e2e_latency_ms | 6981.973 | 7532.64 | 550.667 |
| rag | llm_node_ttft_ms | 1087.655 | 950.475 | -137.18 |
| rag | tts_node_ttfb_ms | 309.625 | 251.53 | -58.095 |
| rag | playback_latency_ms | 59.264 | 42.252 | -17.012 |
| no_rag | transcription_delay_ms | — | 329.982 | — |
| no_rag | end_of_turn_delay_ms | — | 2501.17 | — |
| no_rag | on_user_turn_completed_delay_ms | — | 0.022 | — |
| no_rag | e2e_latency_ms | — | 4762.791 | — |
| no_rag | llm_node_ttft_ms | — | 1861.23 | — |
| no_rag | tts_node_ttfb_ms | — | 258.311 | — |
| no_rag | playback_latency_ms | — | 87.104 | — |
| cold | transcription_delay_ms | 233.972 | 306.772 | 72.8 |
| cold | end_of_turn_delay_ms | 546.024 | 2500.559 | 1954.535 |
| cold | on_user_turn_completed_delay_ms | 3.67 | 3.717 | 0.047 |
| cold | e2e_latency_ms | 8731.698 | 9352.631 | 620.933 |
| cold | llm_node_ttft_ms | 1159.725 | 1108.845 | -50.88 |
| cold | tts_node_ttfb_ms | 319.266 | 256.589 | -62.677 |
| cold | playback_latency_ms | 31.776 | 2.273 | -29.503 |
| warm | transcription_delay_ms | 208.888 | 302.037 | 93.149 |
| warm | end_of_turn_delay_ms | 2504.558 | 2501.186 | -3.372 |
| warm | on_user_turn_completed_delay_ms | 0.039 | 0.021 | -0.018 |
| warm | e2e_latency_ms | 5232.248 | 5237.72 | 5.472 |
| warm | llm_node_ttft_ms | 1015.586 | 1326.668 | 311.082 |
| warm | tts_node_ttfb_ms | 299.983 | 252.391 | -47.592 |
| warm | playback_latency_ms | 86.752 | 84.668 | -2.084 |
| rag_stages | total | 830.0 | 863.0 | 33.0 |
| rag_stages | embedding | 367.0 | 416.0 | 49.0 |
| rag_stages | vector | 463.0 | 446.0 | -17.0 |
| rag_stages | rerank | — | — | — |

Configuración: `[{"stt_model": "deepgram/nova-3", "stt_language": "es", "llm_model": "openai/gpt-4.1-mini", "tts_model": "cartesia/sonic-3.6", "endpointing": {"mode": "fixed", "max_delay": 2.5, "min_delay": 0.3}, "preemptive_tts": true, "rag_prefetch_critical": true}]`
