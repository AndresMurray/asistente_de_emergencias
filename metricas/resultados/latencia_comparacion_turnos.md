# Comparación de latencia

| Corrida | p50 E2E (ms) | Δ vs baseline (ms) | Mejora |
| --- | ---: | ---: | ---: |
| baseline (metricas/resultados/latencia_raw/rag_hemorragia.jsonl) | 2534.566 | — | — |
| metricas/resultados/latencia_raw/turnos_fijo_preemptivo_hemorragia.jsonl | 2155.143 | -379.423 | 14.97% |

## Etapas p50: metricas/resultados/latencia_raw/turnos_fijo_preemptivo_hemorragia.jsonl

| Grupo | Métrica | Baseline | Candidata | Δ ms |
| --- | --- | ---: | ---: | ---: |
| all | transcription_delay_ms | 244.975 | 236.017 | -8.958 |
| all | end_of_turn_delay_ms | 676.36 | 631.878 | -44.482 |
| all | on_user_turn_completed_delay_ms | 0.011 | 0.009 | -0.002 |
| all | e2e_latency_ms | 2534.566 | 2155.143 | -379.423 |
| all | llm_node_ttft_ms | 1089.818 | 1206.545 | 116.727 |
| all | tts_node_ttfb_ms | 287.908 | 303.5 | 15.592 |
| all | playback_latency_ms | 80.739 | 85.318 | 4.579 |
| rag | transcription_delay_ms | 244.975 | 366.282 | 121.307 |
| rag | end_of_turn_delay_ms | 4501.155 | 631.878 | -3869.277 |
| rag | on_user_turn_completed_delay_ms | 1.952 | 2.811 | 0.859 |
| rag | e2e_latency_ms | 13564.627 | 8620.999 | -4943.628 |
| rag | llm_node_ttft_ms | 982.891 | 1152.451 | 169.56 |
| rag | tts_node_ttfb_ms | 291.114 | 296.087 | 4.973 |
| rag | playback_latency_ms | 80.739 | 98.348 | 17.609 |
| no_rag | transcription_delay_ms | 167.237 | 222.677 | 55.44 |
| no_rag | end_of_turn_delay_ms | 616.87 | 829.716 | 212.846 |
| no_rag | on_user_turn_completed_delay_ms | 0.011 | 0.009 | -0.002 |
| no_rag | e2e_latency_ms | 2042.783 | 1998.064 | -44.719 |
| no_rag | llm_node_ttft_ms | 1387.751 | 1289.67 | -98.081 |
| no_rag | tts_node_ttfb_ms | 287.235 | 318.31 | 31.075 |
| no_rag | playback_latency_ms | 74.093 | 81.26 | 7.167 |
| cold | transcription_delay_ms | 244.975 | 366.282 | 121.307 |
| cold | end_of_turn_delay_ms | 4501.155 | 631.878 | -3869.277 |
| cold | on_user_turn_completed_delay_ms | 1.952 | 2.811 | 0.859 |
| cold | e2e_latency_ms | 13564.627 | 8620.999 | -4943.628 |
| cold | llm_node_ttft_ms | 982.891 | 1152.451 | 169.56 |
| cold | tts_node_ttfb_ms | 291.114 | 296.087 | 4.973 |
| cold | playback_latency_ms | 80.739 | 98.348 | 17.609 |
| warm | transcription_delay_ms | 167.237 | 222.677 | 55.44 |
| warm | end_of_turn_delay_ms | 616.87 | 829.716 | 212.846 |
| warm | on_user_turn_completed_delay_ms | 0.011 | 0.009 | -0.002 |
| warm | e2e_latency_ms | 2042.783 | 1998.064 | -44.719 |
| warm | llm_node_ttft_ms | 1387.751 | 1289.67 | -98.081 |
| warm | tts_node_ttfb_ms | 287.235 | 318.31 | 31.075 |
| warm | playback_latency_ms | 74.093 | 81.26 | 7.167 |
| rag_stages | total | 1240.0 | 1745.0 | 505.0 |
| rag_stages | embedding | 762.5 | 1189.0 | 426.5 |
| rag_stages | vector | 477.0 | 555.0 | 78.0 |
| rag_stages | rerank | — | — | — |

Configuración: `[{"stt_model": "deepgram/nova-3", "stt_language": "es", "llm_model": "openai/gpt-4.1-mini", "tts_model": "cartesia/sonic-3.6", "endpointing": {"mode": "fixed", "max_delay": 2.5, "min_delay": 0.3}, "preemptive_tts": true, "rag_prefetch_critical": false}]`
