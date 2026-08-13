"""Orquestación del retrieval.

La pieza clave acá es RetrievalResult.status, con tres valores en lugar de dos.
La versión anterior devolvía "" tanto cuando no había match como cuando se
rompía el embedding o la base, y la tool traducía las dos cosas a "no se
encontraron protocolos". O sea: un corte de Cohere le decía a alguien con un
herido que no existía el procedimiento. Ahora son tres caminos distintos, con
tres frases distintas para quien llama.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from .config import RagSettings, load_settings
from .embeddings import embed_query
from .errors import RetrievalError
from .store import ChunkStore, Fragment

logger = logging.getLogger("rag.retriever")

Status = Literal["ok", "no_match", "error"]


@dataclass
class RetrievalResult:
    status: Status
    fragments: list[Fragment] = field(default_factory=list)
    error: str | None = None
    latency_ms: int = 0
    top_score: float | None = None

    def para_llm(self) -> str:
        """Formatea los fragmentos como contexto para el modelo."""
        bloques = []
        for i, frag in enumerate(self.fragments, start=1):
            bloques.append(f"[{i}] {frag.cita()}\n{frag.text}")
        return "\n\n".join(bloques)


class Retriever:
    def __init__(self, settings: RagSettings | None = None) -> None:
        self._settings = settings or load_settings()
        self._store = ChunkStore(self._settings)

    @property
    def settings(self) -> RagSettings:
        return self._settings

    def connect(self) -> None:
        self._store.connect()

    def close(self) -> None:
        self._store.close()

    async def health(self) -> int:
        return await self._store.health()

    async def search(self, query: str) -> RetrievalResult:
        """Busca protocolos. Nunca levanta: codifica la falla en status."""
        started = time.monotonic()
        try:
            fragments = await asyncio.wait_for(
                self._search_inner(query), timeout=self._settings.timeout_s
            )
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - started) * 1000)
            logger.error("retrieval excedió %.1fs para '%s'", self._settings.timeout_s, query)
            return RetrievalResult(
                status="error",
                error=f"la búsqueda tardó más de {self._settings.timeout_s}s",
                latency_ms=elapsed,
            )
        except RetrievalError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            logger.error("retrieval falló para '%s': %s", query, exc)
            return RetrievalResult(status="error", error=str(exc), latency_ms=elapsed)

        elapsed = int((time.monotonic() - started) * 1000)
        top_score = fragments[0].score if fragments else None

        if not fragments:
            logger.info(
                "sin match | query='%s' latency_ms=%d top_score=%s", query, elapsed, top_score
            )
            return RetrievalResult(
                status="no_match", latency_ms=elapsed, top_score=top_score
            )

        logger.info(
            "ok | query='%s' latency_ms=%d top_score=%.3f n=%d",
            query,
            elapsed,
            top_score,
            len(fragments),
        )
        return RetrievalResult(
            status="ok", fragments=fragments, latency_ms=elapsed, top_score=top_score
        )

    async def _search_inner(self, query: str) -> list[Fragment]:
        vector = await embed_query(query, self._settings)
        # Se traen k_vector candidatos y se recortan a top_k. Cuando entre el
        # reranker de Cohere (Fase 4) va justo acá, entre las dos líneas.
        candidatos = await self._store.search(vector, self._settings.k_vector)
        if self._settings.min_score > 0:
            candidatos = [f for f in candidatos if f.score >= self._settings.min_score]
        return candidatos[: self._settings.top_k]
