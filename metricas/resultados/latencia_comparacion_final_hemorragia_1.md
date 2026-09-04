# Comparación de latencia

| Corrida | p50 E2E (ms) | Δ vs baseline (ms) | Mejora |
| --- | ---: | ---: | ---: |
| baseline (metricas/resultados/latencia_raw/rag_hemorragia.jsonl) | 2534.566 | — | — |
| metricas/resultados/latencia_raw/final_hemorragia_1.jsonl | 1730.661 | -803.905 | 31.72% |

## Etapas p50: metricas/resultados/latencia_raw/final_hemorragia_1.jsonl

| Grupo | Métrica | Baseline | Candidata | Δ ms |
| --- | --- | ---: | ---: | ---: |
| all | transcription_delay_ms | 244.975 | 243.238 | -1.737 |
| all | end_of_turn_delay_ms | 676.36 | 819.016 | 142.656 |
| all | on_user_turn_completed_delay_ms | 0.011 | 0.023 | 0.012 |
| all | e2e_latency_ms | 2534.566 | 1730.661 | -803.905 |
| all | llm_node_ttft_ms | 1089.818 | 939.327 | -150.491 |
| all | tts_node_ttfb_ms | 287.908 | 273.134 | -14.774 |
| all | playback_latency_ms | 80.739 | 18.543 | -62.196 |
| rag | transcription_delay_ms | 244.975 | 243.238 | -1.737 |
| rag | end_of_turn_delay_ms | 4501.155 | 819.016 | -3682.139 |
| rag | on_user_turn_completed_delay_ms | 1.952 | 2.017 | 0.065 |
| rag | e2e_latency_ms | 13564.627 | 7510.756 | -6053.871 |
| rag | llm_node_ttft_ms | 982.891 | 939.209 | -43.682 |
| rag | tts_node_ttfb_ms | 291.114 | 262.148 | -28.966 |
| rag | playback_latency_ms | 80.739 | 18.543 | -62.196 |
| no_rag | transcription_delay_ms | 167.237 | 133.364 | -33.873 |
| no_rag | end_of_turn_delay_ms | 616.87 | 798.364 | 181.494 |
| no_rag | on_user_turn_completed_delay_ms | 0.011 | 0.018 | 0.007 |
| no_rag | e2e_latency_ms | 2042.783 | 1351.613 | -691.17 |
| no_rag | llm_node_ttft_ms | 1387.751 | 1069.634 | -318.117 |
| no_rag | tts_node_ttfb_ms | 287.235 | 290.004 | 2.769 |
| no_rag | playback_latency_ms | 74.093 | 31.496 | -42.597 |
| cold | transcription_delay_ms | 244.975 | 243.238 | -1.737 |
| cold | end_of_turn_delay_ms | 4501.155 | 819.016 | -3682.139 |
| cold | on_user_turn_completed_delay_ms | 1.952 | 2.017 | 0.065 |
| cold | e2e_latency_ms | 13564.627 | 7510.756 | -6053.871 |
| cold | llm_node_ttft_ms | 982.891 | 939.209 | -43.682 |
| cold | tts_node_ttfb_ms | 291.114 | 262.148 | -28.966 |
| cold | playback_latency_ms | 80.739 | 18.543 | -62.196 |
| warm | transcription_delay_ms | 167.237 | 133.364 | -33.873 |
| warm | end_of_turn_delay_ms | 616.87 | 798.364 | 181.494 |
| warm | on_user_turn_completed_delay_ms | 0.011 | 0.018 | 0.007 |
| warm | e2e_latency_ms | 2042.783 | 1351.613 | -691.17 |
| warm | llm_node_ttft_ms | 1387.751 | 1069.634 | -318.117 |
| warm | tts_node_ttfb_ms | 287.235 | 290.004 | 2.769 |
| warm | playback_latency_ms | 74.093 | 31.496 | -42.597 |
| rag_stages | total | 1240.0 | 921.0 | -319.0 |
| rag_stages | embedding | 762.5 | 455.0 | -307.5 |
| rag_stages | vector | 477.0 | 464.0 | -13.0 |
| rag_stages | rerank | — | — | — |

Configuración: `[{"stt_model": "deepgram/nova-3", "stt_language": "es", "llm_model": "openai/gpt-4.1-mini", "tts_model": "cartesia/sonic-3.6", "endpointing": {"mode": "fixed", "max_delay": 2.5, "min_delay": 0.3}, "preemptive_tts": true, "rag_prefetch_critical": false}]`
