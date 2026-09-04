# Resumen de latencia

Eventos: 89

## all

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 3 | 0.0 | 0.0 | — |
| end_of_turn_delay_ms | 3 | 0.213 | 1.561 | — |
| on_user_turn_completed_delay_ms | 3 | 0.011 | 2.247 | — |
| e2e_latency_ms | 3 | 2744.467 | 7676.677 | — |
| llm_node_ttft_ms | 3 | 792.475 | 1188.905 | — |
| tts_node_ttfb_ms | 3 | 301.163 | 895.131 | — |
| playback_latency_ms | 3 | 12.246 | 66.444 | — |

## rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 0.0 | 0.0 | — |
| end_of_turn_delay_ms | 1 | 0.185 | 0.185 | — |
| on_user_turn_completed_delay_ms | 1 | 2.806 | 2.806 | — |
| e2e_latency_ms | 1 | 8909.73 | 8909.73 | — |
| llm_node_ttft_ms | 1 | 688.819 | 688.819 | — |
| tts_node_ttfb_ms | 1 | 269.949 | 269.949 | — |
| playback_latency_ms | 1 | 6.314 | 6.314 | — |

## no_rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 0.0 | 0.0 | — |
| end_of_turn_delay_ms | 2 | 1.055 | 1.73 | — |
| on_user_turn_completed_delay_ms | 2 | 0.009 | 0.011 | — |
| e2e_latency_ms | 2 | 1922.688 | 2580.111 | — |
| llm_node_ttft_ms | 2 | 1040.244 | 1238.459 | — |
| tts_node_ttfb_ms | 2 | 672.393 | 969.377 | — |
| playback_latency_ms | 2 | 46.119 | 73.218 | — |

## cold

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 0 | — | — | — |
| end_of_turn_delay_ms | 0 | — | — | — |
| on_user_turn_completed_delay_ms | 0 | — | — | — |
| e2e_latency_ms | 0 | — | — | — |
| llm_node_ttft_ms | 0 | — | — | — |
| tts_node_ttfb_ms | 0 | — | — | — |
| playback_latency_ms | 0 | — | — | — |

## warm

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 3 | 0.0 | 0.0 | — |
| end_of_turn_delay_ms | 3 | 0.213 | 1.561 | — |
| on_user_turn_completed_delay_ms | 3 | 0.011 | 2.247 | — |
| e2e_latency_ms | 3 | 2744.467 | 7676.677 | — |
| llm_node_ttft_ms | 3 | 792.475 | 1188.905 | — |
| tts_node_ttfb_ms | 3 | 301.163 | 895.131 | — |
| playback_latency_ms | 3 | 12.246 | 66.444 | — |

## Saludo inicial

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| greeting_scheduled_ms | 2 | 26.023 | 27.569 | — |
| first_agent_speaking_ms | 2 | 1165.901 | 1402.711 | — |

## Etapas RAG

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| total_ms | 1 | 1637.0 | 1637.0 | — |
| embedding_ms | 1 | 1138.0 | 1138.0 | — |
| vector_ms | 1 | 498.0 | 498.0 | — |
| rerank_ms | 0 | — | — | — |
