# AGENTS.md

## Project overview

LiveKit Agents voice assistant for Argentine road emergency first aid. Real-time WebRTC voice + RAG over emergency protocol PDFs stored in Supabase pgvector.

**Stack:** LiveKit Agents 1.6.8 (pinned) · Deepgram STT · OpenAI/Cartesia TTS · Google AI Studio embeddings (768d) · Cohere rerank (optional) · Supabase pgvector.

## Essential commands

```bash
# Run agent locally (dev mode)
python agent.py dev

# Run agent in production mode
python agent.py start

# Tests (chunking quality)
python -m pytest tests/ -v

# Ingestion pipeline (PDF -> Supabase)
python ingestion/chunking.py data/raw/        # chunk PDFs (old script)
python -m ingestion.ingest                     # embed + insert to Supabase
python -m ingestion.ingest --dry-run           # preview without DB writes

# Text-only agent test (no audio/STT/TTS, cheap iteration)
python ensayo.py                              # all scripted scenarios
python ensayo.py --escenario critico          # single scenario
python ensayo.py --interactivo                # manual input

# Regenerate the precomputed query cache (rag/cache_consultas.json).
# Run after every re-ingestion or after changing protocolos.py topics.
python -m ingestion.cache_consultas --mostrar

# Metrics (each prints detail + saves JSON to metricas/resultados/)
python metricas/mrr.py
python metricas/recall_at_5.py
python metricas/answer_relevancy.py
python metricas/critical_information_coverage.py

# Deploy to LiveKit Cloud
lk cloud auth
lk agent deploy
```

## Requirements split

- **`requirements.txt`**: Runtime only (LiveKit Agents, psycopg2, pgvector, aiohttp, httpx, dotenv). Used in Docker image — keep lean for cold start.
- **`requirements-dev.txt`**: Ingestion + metrics + tests (pymupdf, pytest, pandas, numpy). Not in Docker image.

`livekit-agents` is pinned to 1.6.8 (the version in the local venv) on purpose — agent.py uses `AgentServer`, `inference.*`, and `turn_handling` APIs that change between versions. Do not bump without verifying behavior.

## Architecture notes

- **`agent.py`**: Main entrypoint. Defines `Assistant` (the Agent subclass), `entrypoint` (LiveKit job handler), and chat backchannel. Loads `.env.local` via dotenv.
- **`triage.py`**: State machine in `TriageState` (userdata). Deterministic critical-signals detection (per turn, per category) and automatic 911 dispatch — does NOT depend on the LLM calling tools. There is no `derivar_a_emergencias` tool anymore.
- **`protocolos.py`**: Critical first-aid topics (CPR, bleeding, helmet, trapped, fire...), each with trigger words, a canonical manual query (precomputed) and a fallback text written from the manual, used if retrieval fails.
- **`agent.py` → `contexto_del_turno()`**: runs before the LLM on every turn (voice, chat and test scripts): triage + attaches the manual protocol for detected topics (0 ms from cache) so the LLM answers in one pass. It is appended to the user message (edits to `turn_ctx` are per-turn only and were lost on the next turn).
- **`habla.py`**: deterministic jargon/voseo fixes applied in `Assistant.llm_node` before TTS.
- **`rag/`**: Shared retrieval package. `Retriever.connect()` (called in the process `prewarm`) loads the whole corpus into an in-memory index (numpy cosine + BM25) and `rag/cache_consultas.json`. Search order: cached result → Gemini embedding + in-memory cosine + Cohere rerank (only if quota is free, never waits) → BM25 lexical fallback if the embedding fails. `search()` returns `RetrievalResult` with three statuses: `ok`, `no_match`, `error` — never raises to the caller.
- **`ingestion/chunker.py`**: New chunker (sentence-aware, metadata-rich). `ingestion/chunking.py` is the old chunker (legacy, still importable). `ingestion/ingest.py` handles embed + upsert.
- **`metricas/`**: Evaluation scripts. Dataset source of truth is `metricas/dataset_evaluacion.json`. Gold chunk labels resolved at runtime via keyword matching (silver labels).
- **`src/`**: Empty package directories (legacy, can be ignored).

## Critical domain constraints

- **Emergency number:** The Spanish corpus says 112. Argentine callers need 119 ("nueve once"). The chunker neutralizes 112 in text; the prompt forbids reading any phone number from retrieved context. The ONLY number the agent may say is "nueve once".
- **RCP safety:** If a person is unconscious, the agent MUST verify breathing before ordering chest compressions. RCP on a breathing person is harmful. This is enforced both in the prompt and by deterministic logic in `triage.py` (`generar_aviso_critico`).
- **No location questions:** The system geolocalizes automatically. The agent never asks for address or street names.
- **Spanish with "vos":** Argentine rioplatense Spanish. The prompt enforces accent consistency for TTS (Cartesia) to pronounce correctly.

## Environment

`.env.local` (gitignored) with: `DATABASE_URL`, `GEMINI_API_KEY` (or `COHERE_API_KEY`), `LIVEKIT_URL/API_KEY/API_SECRET`, `CARTESIA_VOICE_ID` (optional). See `.env.example` for template.

`LLM_MODEL` env var defaults to `google/gemma-4-31b-it`. Can be overridden for testing.

## Deployment

Changes to `agent.py`, `requirements.txt`, or `livekit.toml` require `lk agent deploy`. Database ingestion changes (new PDFs) do NOT — Supabase is consumed dynamically. Production env vars are set in LiveKit Cloud Dashboard, not via `.env.local`.

## Running tests

`python -m pytest tests/ -v` — tests chunking quality against `data/processed/corpus_reconstruido.txt`. Generate corpus first: `python -m ingestion.reconstruir -o data/processed/corpus_reconstruido.txt`.

## Gotchas

- `ingestion/chunking.py` (old) vs `ingestion/chunker.py` (new): the new chunker is what `ingest.py` imports. The old one is still there for backward compat but produces worse chunks.
- `rag/store.py` uses `ThreadedConnectionPool` (1-4 conns). In the hot path the DB is only a fallback: the corpus (~170 chunks) lives in memory.
- Google embeddings (free tier) return 429 on ~70% of calls (measured 2026-09). That is why critical queries are precomputed and BM25 is the fallback. Enabling billing on the Google AI Studio key removes it.
- Cohere Trial key: 10 calls/min, 1000/month. Live turns use `intentar_turno()` (never waits); offline scripts can wait.
- `gpt-oss-120b` on Groq must run with `reasoning_effort="low"` (set in `create_llm`); the default spends ~2 s reasoning per call.
- `metricas/README.md` has detailed explanation of why retrieval is evaluated at chunk level (not document level).
- Docker image uses Python 3.11-slim. Build stage installs gcc/g++ for native extensions; production stage does not.
