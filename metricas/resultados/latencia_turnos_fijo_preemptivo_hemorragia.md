# Resumen de latencia

Eventos: 97

## all

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 3 | 236.017 | 340.229 | — |
| end_of_turn_delay_ms | 3 | 631.878 | 1213.547 | — |
| on_user_turn_completed_delay_ms | 3 | 0.009 | 2.251 | — |
| e2e_latency_ms | 3 | 2155.143 | 7327.828 | — |
| llm_node_ttft_ms | 3 | 1206.545 | 1339.545 | — |
| tts_node_ttfb_ms | 3 | 303.5 | 327.197 | — |
| playback_latency_ms | 3 | 85.318 | 95.742 | — |

## rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 366.282 | 366.282 | — |
| end_of_turn_delay_ms | 1 | 631.878 | 631.878 | — |
| on_user_turn_completed_delay_ms | 1 | 2.811 | 2.811 | — |
| e2e_latency_ms | 1 | 8620.999 | 8620.999 | — |
| llm_node_ttft_ms | 1 | 1152.451 | 1152.451 | — |
| tts_node_ttfb_ms | 1 | 296.087 | 296.087 | — |
| playback_latency_ms | 1 | 98.348 | 98.348 | — |

## no_rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 222.677 | 233.349 | — |
| end_of_turn_delay_ms | 2 | 829.716 | 1253.114 | — |
| on_user_turn_completed_delay_ms | 2 | 0.009 | 0.009 | — |
| e2e_latency_ms | 2 | 1998.064 | 2123.727 | — |
| llm_node_ttft_ms | 2 | 1289.67 | 1356.17 | — |
| tts_node_ttfb_ms | 2 | 318.31 | 330.159 | — |
| playback_latency_ms | 2 | 81.26 | 84.506 | — |

## cold

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 366.282 | 366.282 | — |
| end_of_turn_delay_ms | 1 | 631.878 | 631.878 | — |
| on_user_turn_completed_delay_ms | 1 | 2.811 | 2.811 | — |
| e2e_latency_ms | 1 | 8620.999 | 8620.999 | — |
| llm_node_ttft_ms | 1 | 1152.451 | 1152.451 | — |
| tts_node_ttfb_ms | 1 | 296.087 | 296.087 | — |
| playback_latency_ms | 1 | 98.348 | 98.348 | — |

## warm

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 222.677 | 233.349 | — |
| end_of_turn_delay_ms | 2 | 829.716 | 1253.114 | — |
| on_user_turn_completed_delay_ms | 2 | 0.009 | 0.009 | — |
| e2e_latency_ms | 2 | 1998.064 | 2123.727 | — |
| llm_node_ttft_ms | 2 | 1289.67 | 1356.17 | — |
| tts_node_ttfb_ms | 2 | 318.31 | 330.159 | — |
| playback_latency_ms | 2 | 81.26 | 84.506 | — |

## Saludo inicial

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| greeting_scheduled_ms | 1 | 30.287 | 30.287 | — |
| first_agent_speaking_ms | 1 | 2739.886 | 2739.886 | — |

## Etapas RAG

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| total_ms | 1 | 1745.0 | 1745.0 | — |
| embedding_ms | 1 | 1189.0 | 1189.0 | — |
| vector_ms | 1 | 555.0 | 555.0 | — |
| rerank_ms | 0 | — | — | — |
