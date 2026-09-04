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
from .rerank import rerank
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
    # Tiempos por etapa para diagnosticar si el cuello está en Google, Supabase
    # o Cohere. Se conservan aun cuando la búsqueda termina en error/timeout.
    timings_ms: dict[str, int | None] = field(
        default_factory=lambda: {
            "total": None,
            "embedding": None,
            "vector": None,
            "rerank": None,
        }
    )

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
        timings: dict[str, int | None] = {
            "total": None,
            "embedding": None,
            "vector": None,
            "rerank": None,
        }
        try:
            fragments = await asyncio.wait_for(
                self._search_inner(query, timings), timeout=self._settings.timeout_s
            )
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - started) * 1000)
            timings["total"] = elapsed
            logger.error("retrieval excedió %.1fs para '%s'", self._settings.timeout_s, query)
            return RetrievalResult(
                status="error",
                error=f"la búsqueda tardó más de {self._settings.timeout_s}s",
                latency_ms=elapsed,
                timings_ms=timings,
            )
        except RetrievalError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            timings["total"] = elapsed
            logger.error("retrieval falló para '%s': %s", query, exc)
            return RetrievalResult(
                status="error", error=str(exc), latency_ms=elapsed, timings_ms=timings
            )

        elapsed = int((time.monotonic() - started) * 1000)
        timings["total"] = elapsed
        top_score = fragments[0].score if fragments else None

        if not fragments:
            logger.info(
                "sin match | query='%s' latency_ms=%d top_score=%s", query, elapsed, top_score
            )
            return RetrievalResult(
                status="no_match",
                latency_ms=elapsed,
                top_score=top_score,
                timings_ms=timings,
            )

        logger.info(
            "ok | query='%s' latency_ms=%d top_score=%.3f n=%d",
            query,
            elapsed,
            top_score,
            len(fragments),
        )
        return RetrievalResult(
            status="ok",
            fragments=fragments,
            latency_ms=elapsed,
            top_score=top_score,
            timings_ms=timings,
        )

    async def _search_inner(
        self, query: str, timings: dict[str, int | None]
    ) -> list[Fragment]:
        settings = self._settings
        started = time.monotonic()
        try:
            vector = await embed_query(query, settings)
        finally:
            timings["embedding"] = int((time.monotonic() - started) * 1000)

        started = time.monotonic()
        try:
            candidatos = await self._store.search(vector, settings.k_vector)
        finally:
            timings["vector"] = int((time.monotonic() - started) * 1000)
        if not candidatos:
            return []

        rerankeado = False
        if settings.rerank_enabled:
            started = time.monotonic()
            try:
                candidatos, rerankeado = await self._rerank(query, candidatos)
            finally:
                timings["rerank"] = int((time.monotonic() - started) * 1000)

        # El piso depende de qué escala tienen los scores. Si el rerank falló y
        # se degradó al coseno, aplicar el piso del reranker (0.08) sobre scores
        # de coseno (0.4-0.7) no filtraría nada y pasaría toda la basura.
        piso = settings.min_rerank_score if rerankeado else settings.min_score

        if piso > 0:
            candidatos = [f for f in candidatos if f.score >= piso]
        return candidatos[: settings.top_k]

    async def _rerank(
        self, query: str, candidatos: list[Fragment]
    ) -> tuple[list[Fragment], bool]:
        """Reordena por relevancia real. Devuelve (fragmentos, se_rerankeó).

        Si el reranker falla se degrada al orden del coseno, deliberadamente: una
        respuesta con orden peor es mucho mejor que no responder, y la regla de
        grounding del prompt filtra el contexto que no sirve. Un fallo del
        reranker no debería sonar igual que "el manual no tiene esto".

        Esto no es hipotético: la key de Cohere del proyecto es Trial, con tope
        de 10 llamadas por minuto, y cada turno gasta 2 (embed + rerank). En una
        llamada real de más de cinco turnos por minuto el reranker se apaga solo
        y esta degradación es la que sostiene la conversación.
        """
        try:
            ordenados = await rerank(query, [f.text for f in candidatos], self._settings)
        except RetrievalError as exc:
            logger.warning("rerank falló, sigo con el orden del coseno: %s", exc)
            return candidatos, False

        resultado: list[Fragment] = []
        for indice, score in ordenados:
            if 0 <= indice < len(candidatos):
                fragmento = candidatos[indice]
                # El score pasa a ser el del reranker, que es el que se le
                # muestra al modelo y contra el que se compara el piso.
                fragmento.score = score
                resultado.append(fragmento)
        if not resultado:
            return candidatos, False
        return resultado, True
