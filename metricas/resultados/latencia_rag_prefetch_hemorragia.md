# Resumen de latencia

Eventos: 112

## all

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 3 | 306.772 | 325.34 | — |
| end_of_turn_delay_ms | 3 | 2501.17 | 2501.195 | — |
| on_user_turn_completed_delay_ms | 3 | 0.022 | 2.978 | — |
| e2e_latency_ms | 3 | 5712.649 | 8624.635 | — |
| llm_node_ttft_ms | 3 | 1108.845 | 1710.753 | — |
| tts_node_ttfb_ms | 3 | 256.589 | 257.967 | — |
| playback_latency_ms | 3 | 82.232 | 86.13 | — |

## rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 290.432 | 303.504 | — |
| end_of_turn_delay_ms | 2 | 2500.88 | 2501.137 | — |
| on_user_turn_completed_delay_ms | 2 | 1.869 | 3.347 | — |
| e2e_latency_ms | 2 | 7532.64 | 8988.633 | — |
| llm_node_ttft_ms | 2 | 950.475 | 1077.171 | — |
| tts_node_ttfb_ms | 2 | 251.53 | 255.577 | — |
| playback_latency_ms | 2 | 42.252 | 74.236 | — |

## no_rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 329.982 | 329.982 | — |
| end_of_turn_delay_ms | 1 | 2501.17 | 2501.17 | — |
| on_user_turn_completed_delay_ms | 1 | 0.022 | 0.022 | — |
| e2e_latency_ms | 1 | 4762.791 | 4762.791 | — |
| llm_node_ttft_ms | 1 | 1861.23 | 1861.23 | — |
| tts_node_ttfb_ms | 1 | 258.311 | 258.311 | — |
| playback_latency_ms | 1 | 87.104 | 87.104 | — |

## cold

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 306.772 | 306.772 | — |
| end_of_turn_delay_ms | 1 | 2500.559 | 2500.559 | — |
| on_user_turn_completed_delay_ms | 1 | 3.717 | 3.717 | — |
| e2e_latency_ms | 1 | 9352.631 | 9352.631 | — |
| llm_node_ttft_ms | 1 | 1108.845 | 1108.845 | — |
| tts_node_ttfb_ms | 1 | 256.589 | 256.589 | — |
| playback_latency_ms | 1 | 2.273 | 2.273 | — |

## warm

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 302.037 | 324.393 | — |
| end_of_turn_delay_ms | 2 | 2501.186 | 2501.198 | — |
| on_user_turn_completed_delay_ms | 2 | 0.021 | 0.022 | — |
| e2e_latency_ms | 2 | 5237.72 | 5617.663 | — |
| llm_node_ttft_ms | 2 | 1326.668 | 1754.318 | — |
| tts_node_ttfb_ms | 2 | 252.391 | 257.127 | — |
| playback_latency_ms | 2 | 84.668 | 86.617 | — |

## Saludo inicial

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| greeting_scheduled_ms | 1 | 23.185 | 23.185 | — |
| first_agent_speaking_ms | 1 | 1361.602 | 1361.602 | — |

## Etapas RAG

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| total_ms | 2 | 863.0 | 915.8 | — |
| embedding_ms | 2 | 416.0 | 465.6 | — |
| vector_ms | 2 | 446.0 | 449.2 | — |
| rerank_ms | 0 | — | — | — |
