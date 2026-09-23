"""Orquestación del retrieval.

La pieza clave acá es RetrievalResult.status, con tres valores en lugar de dos.
La versión anterior devolvía "" tanto cuando no había match como cuando se
rompía el embedding o la base, y la tool traducía las dos cosas a "no se
encontraron protocolos". O sea: un corte de Cohere le decía a alguien con un
herido que no existía el procedimiento. Ahora son tres caminos distintos, con
tres frases distintas para quien llama.

Orden de búsqueda, del más rápido y confiable al menos:

1. Resultado ya calculado (caché de consultas): 0 ms, sin red. Las consultas
   canónicas de los protocolos críticos vienen precalculadas en
   `cache_consultas.json` (embedding + ranking rerankeado), así que RCP,
   hemorragias, casco, etc. no dependen de ningún servicio externo en vivo.
2. Embedding de la consulta (Google) + coseno en memoria + rerank (Cohere, solo
   si hay cupo, sin esperar).
3. Si el embedding falla (429 frecuente en el plan gratuito de Google):
   búsqueda léxica BM25 en memoria.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from .config import RagSettings, load_settings
from .embeddings import embed_query
from .errors import RetrievalError
from .index import MemoryIndex, texto_hash
from .rerank import rerank
from .store import ChunkStore, Fragment

logger = logging.getLogger("rag.retriever")

Status = Literal["ok", "no_match", "error"]
Modo = Literal["cache", "semantico", "lexico", "db", ""]

CACHE_PATH = Path(__file__).with_name("cache_consultas.json")
_MAX_EMBEDDINGS_EN_MEMORIA = 512


def normalizar_consulta(texto: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn"
    )
    return " ".join(re.findall(r"[a-z0-9ñ]+", sin_acentos))


@dataclass
class RetrievalResult:
    status: Status
    fragments: list[Fragment] = field(default_factory=list)
    error: str | None = None
    latency_ms: int = 0
    top_score: float | None = None
    # Per-phase timing for debug
    embed_ms: int = 0
    vector_search_ms: int = 0
    rerank_ms: int = 0
    candidate_count: int = 0
    reranked: bool = False
    # De dónde salió el resultado: cache, semantico, lexico o db.
    modo: Modo = ""

    def para_llm(self) -> str:
        """Formatea los fragmentos como contexto para el modelo."""
        bloques = []
        for i, frag in enumerate(self.fragments, start=1):
            bloques.append(f"[{i}] {frag.cita()}\n{frag.text}")
        return "\n\n".join(bloques)

    def to_debug_dict(self) -> dict:
        """Serializa el resultado para el frontend de debug."""
        return {
            "status": self.status,
            "error": self.error,
            "modo": self.modo,
            "latency_ms": self.latency_ms,
            "embed_ms": self.embed_ms,
            "vector_search_ms": self.vector_search_ms,
            "rerank_ms": self.rerank_ms,
            "candidate_count": self.candidate_count,
            "reranked": self.reranked,
            "top_score": self.top_score,
            "fragments": [
                {
                    "text": f.text[:300],
                    "score": f.score,
                    "section": f.section,
                    "subsection": f.subsection,
                    "page_start": f.page_start,
                    "page_end": f.page_end,
                }
                for f in self.fragments
            ],
        }


class Retriever:
    def __init__(
        self,
        settings: RagSettings | None = None,
        *,
        esperar_rerank: bool = False,
        cache_path: Path | None = CACHE_PATH,
    ) -> None:
        self._settings = settings or load_settings()
        self._store = ChunkStore(self._settings)
        # En vivo NO se espera cupo del rerank; en scripts offline sí conviene.
        self._esperar_rerank = esperar_rerank
        self._cache_path = cache_path
        self._index: MemoryIndex | None = None
        # consulta normalizada -> embedding (LRU)
        self._embeddings: OrderedDict[str, list[float]] = OrderedDict()
        # consulta normalizada -> fragmentos finales (solo resultados rerankeados
        # o con rerank apagado: son definitivos para la vida del proceso)
        self._resultados: dict[str, list[Fragment]] = {}

    @property
    def settings(self) -> RagSettings:
        return self._settings

    @property
    def index(self) -> MemoryIndex | None:
        return self._index

    def connect(self) -> None:
        """Pool + índice en memoria + caché de consultas. Bloqueante: llamar al
        arrancar el proceso (prewarm), nunca dentro de un turno."""
        self._store.connect()
        t0 = time.monotonic()
        try:
            fragments, embeddings = self._store.cargar_todo()
            self._index = MemoryIndex(fragments, embeddings)
            logger.info(
                "índice en memoria: %d fragmentos en %d ms",
                len(self._index),
                int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:  # la base sigue sirviendo como camino lento
            logger.error("no pude cargar el índice en memoria, sigo contra la base: %s", exc)
            self._index = None
        self._cargar_cache()

    def close(self) -> None:
        self._store.close()

    async def health(self) -> int:
        return await self._store.health()

    # -- caché de consultas -------------------------------------------------

    def _cargar_cache(self) -> None:
        if not self._cache_path or not self._cache_path.exists():
            logger.warning("sin caché de consultas (%s)", self._cache_path)
            return
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("caché de consultas ilegible: %s", exc)
            return
        if data.get("table") != self._settings.table or data.get("embed_model") != self._settings.embed_model:
            logger.warning(
                "caché de consultas generado para %s/%s, no para %s/%s: se ignora",
                data.get("table"), data.get("embed_model"),
                self._settings.table, self._settings.embed_model,
            )
            return

        embeddings = resultados = 0
        for consulta, entrada in data.get("consultas", {}).items():
            clave = normalizar_consulta(consulta)
            if entrada.get("embedding"):
                self._guardar_embedding(clave, entrada["embedding"])
                embeddings += 1
            ranking = entrada.get("ranking") or []
            if self._index is not None and ranking:
                frags = [self._index.por_hash(h, s) for h, s in ranking]
                # Si el corpus cambió (reingesta) el ranking queda viejo: se
                # descarta y en vivo se recalcula con el embedding guardado.
                if all(frags):
                    self._resultados[clave] = frags  # type: ignore[assignment]
                    resultados += 1
        logger.info("caché de consultas: %d embeddings, %d resultados listos", embeddings, resultados)

    def _guardar_embedding(self, clave: str, vector: list[float]) -> None:
        self._embeddings[clave] = vector
        self._embeddings.move_to_end(clave)
        while len(self._embeddings) > _MAX_EMBEDDINGS_EN_MEMORIA:
            self._embeddings.popitem(last=False)

    def exportar_cache(self, consultas: list[str]) -> dict:
        """Arma el contenido de cache_consultas.json para las consultas dadas,
        con lo que haya quedado calculado en este proceso."""
        salida: dict = {
            "table": self._settings.table,
            "embed_model": self._settings.embed_model,
            "consultas": {},
        }
        for consulta in consultas:
            clave = normalizar_consulta(consulta)
            vector = self._embeddings.get(clave)
            if vector is None:
                continue
            frags = self._resultados.get(clave, [])
            salida["consultas"][consulta] = {
                "embedding": [round(float(x), 6) for x in vector],
                "ranking": [[texto_hash(f.text), round(f.score, 4)] for f in frags],
            }
        return salida

    # -- búsqueda -----------------------------------------------------------

    async def search(self, query: str) -> RetrievalResult:
        """Busca protocolos. Nunca levanta: codifica la falla en status."""
        started = time.monotonic()
        clave = normalizar_consulta(query)

        cacheado = self._resultados.get(clave)
        if cacheado is not None:
            return self._resultado(
                query, cacheado, started, modo="cache", reranked=self._settings.rerank_enabled
            )

        try:
            fragments, info = await asyncio.wait_for(
                self._search_inner(query, clave), timeout=self._settings.timeout_s
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

        return self._resultado(query, fragments, started, **info)

    def _resultado(
        self, query: str, fragments: list[Fragment], started: float, **info
    ) -> RetrievalResult:
        elapsed = int((time.monotonic() - started) * 1000)
        fragments = [replace(f) for f in fragments]
        top_score = fragments[0].score if fragments else None
        if not fragments:
            logger.info("sin match | query='%s' latency_ms=%d modo=%s", query, elapsed, info.get("modo"))
            return RetrievalResult(status="no_match", latency_ms=elapsed, **info)
        logger.info(
            "ok | query='%s' latency_ms=%d modo=%s top_score=%.3f n=%d",
            query, elapsed, info.get("modo"), top_score, len(fragments),
        )
        return RetrievalResult(
            status="ok",
            fragments=fragments,
            latency_ms=elapsed,
            top_score=top_score,
            **info,
        )

    async def _search_inner(self, query: str, clave: str) -> tuple[list[Fragment], dict]:
        settings = self._settings
        info: dict = {"modo": "semantico"}

        t0 = time.monotonic()
        vector = self._embeddings.get(clave)
        if vector is None:
            try:
                vector = await embed_query(query, settings)
                self._guardar_embedding(clave, vector)
            except RetrievalError as exc:
                if self._index is None:
                    raise
                logger.warning("embedding falló, uso búsqueda léxica: %s", exc)
                info["embed_ms"] = int((time.monotonic() - t0) * 1000)
                info["modo"] = "lexico"
                frags = self._index.buscar_lexico(query, settings.top_k)
                info["candidate_count"] = len(frags)
                return frags, info
        info["embed_ms"] = int((time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        if self._index is not None:
            candidatos = self._index.buscar_vector(vector, settings.k_vector)
        else:
            info["modo"] = "db"
            candidatos = await self._store.search(vector, settings.k_vector)
        info["vector_search_ms"] = int((time.monotonic() - t0) * 1000)

        if not candidatos:
            return [], info

        rerankeado = False
        if settings.rerank_enabled:
            t0 = time.monotonic()
            candidatos, rerankeado = await self._rerank(query, candidatos)
            info["rerank_ms"] = int((time.monotonic() - t0) * 1000)
        info["reranked"] = rerankeado

        # El piso depende de qué escala tienen los scores. Si el rerank falló y
        # se degradó al coseno, aplicar el piso del reranker (0.08) sobre scores
        # de coseno (0.4-0.7) no filtraría nada y pasaría toda la basura.
        piso = settings.min_rerank_score if rerankeado else settings.min_score
        if piso > 0:
            candidatos = [f for f in candidatos if f.score >= piso]

        info["candidate_count"] = len(candidatos)
        final = candidatos[: settings.top_k]
        if rerankeado or not settings.rerank_enabled:
            self._resultados[clave] = final
        return final, info

    async def _rerank(
        self, query: str, candidatos: list[Fragment]
    ) -> tuple[list[Fragment], bool]:
        """Reordena por relevancia real. Devuelve (fragmentos, se_rerankeó).

        Si el reranker falla o no hay cupo se degrada al orden del coseno,
        deliberadamente: una respuesta con orden peor es mucho mejor que no
        responder, y la regla de grounding del prompt filtra el contexto que no
        sirve. Un fallo del reranker no debería sonar igual que "el manual no
        tiene esto".

        La key de Cohere del proyecto es Trial (10 llamadas por minuto): en una
        llamada real con varias búsquedas seguidas el reranker se saltea solo y
        esta degradación es la que sostiene la conversación.
        """
        try:
            ordenados = await rerank(
                query, [f.text for f in candidatos], self._settings, esperar=self._esperar_rerank
            )
        except RetrievalError as exc:
            logger.info("rerank salteado, sigo con el orden del coseno: %s", exc)
            return candidatos, False

        resultado: list[Fragment] = []
        for indice, score in ordenados:
            if 0 <= indice < len(candidatos):
                # El score pasa a ser el del reranker, que es el que se le
                # muestra al modelo y contra el que se compara el piso.
                resultado.append(replace(candidatos[indice], score=score))
        if not resultado:
            return candidatos, False
        return resultado, True
