# Resumen de latencia

Eventos: 117

## all

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 3 | 244.975 | 294.165 | — |
| end_of_turn_delay_ms | 3 | 676.36 | 3736.196 | — |
| on_user_turn_completed_delay_ms | 3 | 0.011 | 1.564 | — |
| e2e_latency_ms | 3 | 2534.566 | 11358.615 | — |
| llm_node_ttft_ms | 3 | 1089.818 | 1566.512 | — |
| tts_node_ttfb_ms | 3 | 287.908 | 290.473 | — |
| playback_latency_ms | 3 | 80.739 | 93.892 | — |

## rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 244.975 | 244.975 | — |
| end_of_turn_delay_ms | 1 | 4501.155 | 4501.155 | — |
| on_user_turn_completed_delay_ms | 1 | 1.952 | 1.952 | — |
| e2e_latency_ms | 1 | 13564.627 | 13564.627 | — |
| llm_node_ttft_ms | 1 | 982.891 | 982.891 | — |
| tts_node_ttfb_ms | 1 | 291.114 | 291.114 | — |
| playback_latency_ms | 1 | 80.739 | 80.739 | — |

## no_rag

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 167.237 | 278.618 | — |
| end_of_turn_delay_ms | 2 | 616.87 | 664.462 | — |
| on_user_turn_completed_delay_ms | 2 | 0.011 | 0.011 | — |
| e2e_latency_ms | 2 | 2042.783 | 2436.209 | — |
| llm_node_ttft_ms | 2 | 1387.751 | 1626.098 | — |
| tts_node_ttfb_ms | 2 | 287.235 | 287.773 | — |
| playback_latency_ms | 2 | 74.093 | 92.562 | — |

## cold

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 1 | 244.975 | 244.975 | — |
| end_of_turn_delay_ms | 1 | 4501.155 | 4501.155 | — |
| on_user_turn_completed_delay_ms | 1 | 1.952 | 1.952 | — |
| e2e_latency_ms | 1 | 13564.627 | 13564.627 | — |
| llm_node_ttft_ms | 1 | 982.891 | 982.891 | — |
| tts_node_ttfb_ms | 1 | 291.114 | 291.114 | — |
| playback_latency_ms | 1 | 80.739 | 80.739 | — |

## warm

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| transcription_delay_ms | 2 | 167.237 | 278.618 | — |
| end_of_turn_delay_ms | 2 | 616.87 | 664.462 | — |
| on_user_turn_completed_delay_ms | 2 | 0.011 | 0.011 | — |
| e2e_latency_ms | 2 | 2042.783 | 2436.209 | — |
| llm_node_ttft_ms | 2 | 1387.751 | 1626.098 | — |
| tts_node_ttfb_ms | 2 | 287.235 | 287.773 | — |
| playback_latency_ms | 2 | 74.093 | 92.562 | — |

## Saludo inicial

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| greeting_scheduled_ms | 1 | 23.849 | 23.849 | — |
| first_agent_speaking_ms | 1 | 2111.779 | 2111.779 | — |

## Etapas RAG

| Métrica | n | p50 | p90 | p95 |
| --- | ---: | ---: | ---: | ---: |
| total_ms | 2 | 1240.0 | 1602.4 | — |
| embedding_ms | 2 | 762.5 | 1099.7 | — |
| vector_ms | 2 | 477.0 | 501.8 | — |
| rerank_ms | 0 | — | — | — |
