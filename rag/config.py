"""Configuración de retrieval, en un solo lugar.

Antes estaba repartida en os.getenv() por todo agent.py e ingest.py, y los
scripts de metricas/ pisaban DATABASE_URL a mano. Tener un único objeto de
settings es lo que permite que el agente y las métricas midan lo mismo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class RagSettings:
    database_url: str
    gemini_api_key: str | None = None
    cohere_api_key: str | None = None

    table: str = "chunks_gemini"

    # Fragmentos que terminan en el prompt del LLM.
    top_k: int = 3
    # Candidatos que trae pgvector antes de rerankear.
    k_vector: int = 20

    # Presupuesto total de la tool de búsqueda.
    timeout_s: float = 4.0
    # Timeout de la llamada a embeddings.
    embed_timeout_s: float = 2.5

    # Piso de similitud coseno por debajo del cual un fragmento se descarta.
    min_score: float = 0.50

    embed_model: str = "gemini-embedding-001"
    gemini_embed_url: str = (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"
    )
    gemini_batch_embed_url: str = (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
    )

    # --- reranking ---
    rerank_enabled: bool = False
    rerank_model: str = "rerank-v3.5"
    rerank_top_n: int = 5
    rerank_timeout_s: float = 2.0
    cohere_rerank_url: str = "https://api.cohere.ai/v1/rerank"
    min_rerank_score: float = 0.08


def load_settings() -> RagSettings:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL no está configurada (ver .env.example)")

    gemini_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    cohere_api_key = os.environ.get("COHERE_API_KEY")

    if not gemini_api_key and not cohere_api_key:
        raise ValueError(
            "Se requiere GEMINI_API_KEY o COHERE_API_KEY configurada (ver .env.example)"
        )

    defaults = {f.name: f.default for f in fields(RagSettings)}

    def _env(name: str, field: str, cast):
        raw = os.getenv(name)
        return cast(raw) if raw else defaults[field]

    return RagSettings(
        database_url=database_url,
        gemini_api_key=gemini_api_key,
        cohere_api_key=cohere_api_key,
        table=_env("RAG_TABLE", "table", str),
        top_k=_env("TOP_K", "top_k", int),
        k_vector=_env("RAG_K_VECTOR", "k_vector", int),
        timeout_s=_env("RAG_TIMEOUT_S", "timeout_s", float),
        embed_timeout_s=_env("RAG_EMBED_TIMEOUT_S", "embed_timeout_s", float),
        min_score=_env("RAG_MIN_SCORE", "min_score", float),
        rerank_enabled=_env("RAG_RERANK", "rerank_enabled", lambda v: v not in ("0", "false")),
        rerank_model=_env("RAG_RERANK_MODEL", "rerank_model", str),
        rerank_top_n=_env("RAG_RERANK_TOP_N", "rerank_top_n", int),
        min_rerank_score=_env("RAG_MIN_RERANK_SCORE", "min_rerank_score", float),
    )
