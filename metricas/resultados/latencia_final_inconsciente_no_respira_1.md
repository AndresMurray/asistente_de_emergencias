# Resumen de latencia

Eventos: 107

## all

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 3 | 285.04 | 319.822 | — |
| end_of_turn_delay_ms | 3 | 612.788 | 2123.45 | — |
| on_user_turn_completed_delay_ms | 3 | 0.013 | 1.026 | — |
| e2e_latency_ms | 3 | 5148.026 | 6988.016 | — |
| llm_node_ttft_ms | 3 | 1403.652 | 2007.321 | — |
| tts_node_ttfb_ms | 3 | 296.943 | 298.032 | — |
| playback_latency_ms | 3 | 55.153 | 72.195 | — |

## rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 306.779 | 324.17 | — |
| end_of_turn_delay_ms | 2 | 1556.951 | 2312.282 | — |
| on_user_turn_completed_delay_ms | 2 | 0.01 | 0.013 | — |
| e2e_latency_ms | 2 | 6298.02 | 7218.015 | — |
| llm_node_ttft_ms | 2 | 1679.024 | 2062.395 | — |
| tts_node_ttfb_ms | 2 | 293.868 | 296.328 | — |
| playback_latency_ms | 2 | 41.91 | 52.504 | — |

## no_rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 221.756 | 221.756 | — |
| end_of_turn_delay_ms | 1 | 402.542 | 402.542 | — |
| on_user_turn_completed_delay_ms | 1 | 1.279 | 1.279 | — |
| e2e_latency_ms | 1 | 4477.918 | 4477.918 | — |
| llm_node_ttft_ms | 1 | 1403.652 | 1403.652 | — |
| tts_node_ttfb_ms | 1 | 298.304 | 298.304 | — |
| playback_latency_ms | 1 | 76.456 | 76.456 | — |

## cold

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 221.756 | 221.756 | — |
| end_of_turn_delay_ms | 1 | 402.542 | 402.542 | — |
| on_user_turn_completed_delay_ms | 1 | 1.279 | 1.279 | — |
| e2e_latency_ms | 1 | 4477.918 | 4477.918 | — |
| llm_node_ttft_ms | 1 | 1403.652 | 1403.652 | — |
| tts_node_ttfb_ms | 1 | 298.304 | 298.304 | — |
| playback_latency_ms | 1 | 76.456 | 76.456 | — |

## warm

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 306.779 | 324.17 | — |
| end_of_turn_delay_ms | 2 | 1556.951 | 2312.282 | — |
| on_user_turn_completed_delay_ms | 2 | 0.01 | 0.013 | — |
| e2e_latency_ms | 2 | 6298.02 | 7218.015 | — |
| llm_node_ttft_ms | 2 | 1679.024 | 2062.395 | — |
| tts_node_ttfb_ms | 2 | 293.868 | 296.328 | — |
| playback_latency_ms | 2 | 41.91 | 52.504 | — |

## Saludo inicial

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| greeting_scheduled_ms | 1 | 24.393 | 24.393 | — |
| first_agent_speaking_ms | 1 | 1861.638 | 1861.638 | — |

## Etapas RAG

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| total_ms | 3 | 858.0 | 899.6 | — |
| embedding_ms | 3 | 397.0 | 439.4 | — |
| vector_ms | 3 | 459.0 | 459.8 | — |
| rerank_ms | 0 | — | — | — |
