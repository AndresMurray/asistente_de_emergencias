# Resumen de latencia

Eventos: 81

## all

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 221.43 | 231.464 | — |
| end_of_turn_delay_ms | 2 | 1525.291 | 2308.705 | — |
| on_user_turn_completed_delay_ms | 2 | 1.855 | 3.307 | — |
| e2e_latency_ms | 2 | 6981.973 | 8381.753 | — |
| llm_node_ttft_ms | 2 | 1087.655 | 1145.311 | — |
| tts_node_ttfb_ms | 2 | 309.625 | 317.338 | — |
| playback_latency_ms | 2 | 59.264 | 81.254 | — |

## rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 221.43 | 231.464 | — |
| end_of_turn_delay_ms | 2 | 1525.291 | 2308.705 | — |
| on_user_turn_completed_delay_ms | 2 | 1.855 | 3.307 | — |
| e2e_latency_ms | 2 | 6981.973 | 8381.753 | — |
| llm_node_ttft_ms | 2 | 1087.655 | 1145.311 | — |
| tts_node_ttfb_ms | 2 | 309.625 | 317.338 | — |
| playback_latency_ms | 2 | 59.264 | 81.254 | — |

## no_rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 0 | — | — | — |
| end_of_turn_delay_ms | 0 | — | — | — |
| on_user_turn_completed_delay_ms | 0 | — | — | — |
| e2e_latency_ms | 0 | — | — | — |
| llm_node_ttft_ms | 0 | — | — | — |
| tts_node_ttfb_ms | 0 | — | — | — |
| playback_latency_ms | 0 | — | — | — |

## cold

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 233.972 | 233.972 | — |
| end_of_turn_delay_ms | 1 | 546.024 | 546.024 | — |
| on_user_turn_completed_delay_ms | 1 | 3.67 | 3.67 | — |
| e2e_latency_ms | 1 | 8731.698 | 8731.698 | — |
| llm_node_ttft_ms | 1 | 1159.725 | 1159.725 | — |
| tts_node_ttfb_ms | 1 | 319.266 | 319.266 | — |
| playback_latency_ms | 1 | 31.776 | 31.776 | — |

## warm

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 208.888 | 208.888 | — |
| end_of_turn_delay_ms | 1 | 2504.558 | 2504.558 | — |
| on_user_turn_completed_delay_ms | 1 | 0.039 | 0.039 | — |
| e2e_latency_ms | 1 | 5232.248 | 5232.248 | — |
| llm_node_ttft_ms | 1 | 1015.586 | 1015.586 | — |
| tts_node_ttfb_ms | 1 | 299.983 | 299.983 | — |
| playback_latency_ms | 1 | 86.752 | 86.752 | — |

## Saludo inicial

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| greeting_scheduled_ms | 1 | 31.552 | 31.552 | — |
| first_agent_speaking_ms | 1 | 1840.103 | 1840.103 | — |

## Etapas RAG

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| total_ms | 3 | 830.0 | 978.0 | — |
| embedding_ms | 3 | 367.0 | 514.2 | — |
| vector_ms | 3 | 463.0 | 468.6 | — |
| rerank_ms | 0 | — | — | — |
