# Resumen de latencia

Eventos: 95

## all

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 3 | 243.238 | 262.03 | — |
| end_of_turn_delay_ms | 3 | 819.016 | 1116.486 | — |
| on_user_turn_completed_delay_ms | 3 | 0.023 | 1.618 | — |
| e2e_latency_ms | 3 | 1730.661 | 6354.737 | — |
| llm_node_ttft_ms | 3 | 939.327 | 1147.818 | — |
| tts_node_ttfb_ms | 3 | 273.134 | 300.126 | — |
| playback_latency_ms | 3 | 18.543 | 41.512 | — |

## rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 243.238 | 243.238 | — |
| end_of_turn_delay_ms | 1 | 819.016 | 819.016 | — |
| on_user_turn_completed_delay_ms | 1 | 2.017 | 2.017 | — |
| e2e_latency_ms | 1 | 7510.756 | 7510.756 | — |
| llm_node_ttft_ms | 1 | 939.209 | 939.209 | — |
| tts_node_ttfb_ms | 1 | 262.148 | 262.148 | — |
| playback_latency_ms | 1 | 18.543 | 18.543 | — |

## no_rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 133.364 | 240.055 | — |
| end_of_turn_delay_ms | 2 | 798.364 | 1112.356 | — |
| on_user_turn_completed_delay_ms | 2 | 0.018 | 0.022 | — |
| e2e_latency_ms | 2 | 1351.613 | 1654.852 | — |
| llm_node_ttft_ms | 2 | 1069.634 | 1173.88 | — |
| tts_node_ttfb_ms | 2 | 290.004 | 303.5 | — |
| playback_latency_ms | 2 | 31.496 | 44.102 | — |

## cold

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 243.238 | 243.238 | — |
| end_of_turn_delay_ms | 1 | 819.016 | 819.016 | — |
| on_user_turn_completed_delay_ms | 1 | 2.017 | 2.017 | — |
| e2e_latency_ms | 1 | 7510.756 | 7510.756 | — |
| llm_node_ttft_ms | 1 | 939.209 | 939.209 | — |
| tts_node_ttfb_ms | 1 | 262.148 | 262.148 | — |
| playback_latency_ms | 1 | 18.543 | 18.543 | — |

## warm

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 133.364 | 240.055 | — |
| end_of_turn_delay_ms | 2 | 798.364 | 1112.356 | — |
| on_user_turn_completed_delay_ms | 2 | 0.018 | 0.022 | — |
| e2e_latency_ms | 2 | 1351.613 | 1654.852 | — |
| llm_node_ttft_ms | 2 | 1069.634 | 1173.88 | — |
| tts_node_ttfb_ms | 2 | 290.004 | 303.5 | — |
| playback_latency_ms | 2 | 31.496 | 44.102 | — |

## Saludo inicial

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| greeting_scheduled_ms | 1 | 31.287 | 31.287 | — |
| first_agent_speaking_ms | 1 | 6766.262 | 6766.262 | — |

## Etapas RAG

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| total_ms | 1 | 921.0 | 921.0 | — |
| embedding_ms | 1 | 455.0 | 455.0 | — |
| vector_ms | 1 | 464.0 | 464.0 | — |
| rerank_ms | 0 | — | — | — |
