"""Reranking con Cohere.

Por qué hace falta: el coseno sobre embeddings separa bien cuando la consulta
está bien escrita, pero se cae con frases telegráficas, que es exactamente cómo
habla alguien asustado por teléfono. Medido sobre el corpus anterior, las
distribuciones se solapaban: consultas legítimas desde 0.472 y basura hasta
0.518, así que no existía un piso limpio. Un reranker resuelve eso mejor que
cualquier umbral, porque puntúa la relación consulta-documento en lugar de la
distancia entre dos vectores.

Estrategia: pgvector trae k_vector candidatos (recall alto, cuesta poco), el
reranker los ordena y se le pasan al modelo solo los mejores top_k.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from .config import RagSettings
from .errors import RetrievalError
from .ratelimit import esperar_turno
from .session import cohere_session

logger = logging.getLogger("rag.rerank")


async def rerank(
    query: str, documentos: list[str], settings: RagSettings
) -> list[tuple[int, float]]:
    """Ordena los documentos por relevancia real contra la consulta.

    Devuelve [(indice_original, score)] ordenado de mejor a peor. Si el reranker
    falla, se levanta RetrievalError y el caller decide si degrada al orden del
    coseno: preferimos una respuesta con orden peor a no responder nada.
    """
    if not documentos:
        return []

    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": documentos,
        "top_n": min(settings.rerank_top_n, len(documentos)),
    }
    headers = {
        "Authorization": f"Bearer {settings.cohere_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=settings.rerank_timeout_s, connect=0.5)

    try:
        await esperar_turno()
        async with cohere_session().post(
            settings.cohere_rerank_url, headers=headers, json=payload, timeout=timeout
        ) as response:
            if response.status != 200:
                raise RetrievalError(
                    f"Cohere rerank devolvió {response.status}: "
                    f"{(await response.text())[:200]}"
                )
            data = await response.json()
    except asyncio.TimeoutError as exc:
        raise RetrievalError(
            f"timeout de {settings.rerank_timeout_s}s rerankeando"
        ) from exc
    except aiohttp.ClientError as exc:
        raise RetrievalError(f"error de red rerankeando: {exc}") from exc

    return [
        (int(r["index"]), float(r["relevance_score"]))
        for r in data.get("results", [])
    ]
