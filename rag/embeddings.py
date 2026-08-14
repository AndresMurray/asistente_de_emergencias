"""Embeddings de Cohere.

Dos arreglos respecto de la versión que estaba inline en agent.py:

1. Reusa la ClientSession compartida del SDK (utils.http_context.http_session())
   en lugar de crear una nueva por llamada. Esa session ya trae un TCPConnector
   con keepalive de 120s, así que se ahorra el handshake TLS con Cohere en cada
   turno (~50-150 ms).
2. Tiene timeout. Antes no había ninguno.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from .config import RagSettings
from .errors import RetrievalError

logger = logging.getLogger("rag.embeddings")


def _session() -> aiohttp.ClientSession:
    """Session compartida del job; cae a una propia fuera del worker.

    Dentro de un job de LiveKit, http_session() devuelve la session del proceso.
    Fuera (tests, scripts de metricas/) levanta RuntimeError, así que ahí
    creamos una al vuelo — el caller la cierra.
    """
    from livekit.agents.utils import http_context

    return http_context.http_session()


async def embed_query(text: str, settings: RagSettings) -> list[float]:
    """Embebe la consulta del usuario. input_type asimétrico respecto de la ingesta."""
    return await _embed(text, settings, input_type="search_query")


async def embed_documents(texts: list[str], settings: RagSettings) -> list[list[float]]:
    """Embebe chunks para ingesta. Cohere acepta hasta 96 textos por llamada."""
    if len(texts) > 96:
        raise ValueError(f"Cohere acepta 96 textos por llamada, recibí {len(texts)}")
    return await _embed_many(texts, settings, input_type="search_document")


async def _embed(text: str, settings: RagSettings, *, input_type: str) -> list[float]:
    vectors = await _embed_many([text], settings, input_type=input_type)
    return vectors[0]


async def _embed_many(
    texts: list[str], settings: RagSettings, *, input_type: str
) -> list[list[float]]:
    payload = {
        "texts": texts,
        "model": settings.embed_model,
        "input_type": input_type,
        "embedding_types": ["float"],
    }
    headers = {
        "Authorization": f"Bearer {settings.cohere_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=settings.embed_timeout_s, connect=0.5)

    # Un solo reintento: más allá de eso ya se agotó la paciencia de quien llama,
    # y conviene fallar a RetrievalError para que el agente lo diga y derive.
    last_error: Exception | None = None
    for attempt in (1, 2):
        try:
            async with _session().post(
                settings.cohere_embed_url, headers=headers, json=payload, timeout=timeout
            ) as response:
                if response.status >= 500 or response.status == 429:
                    last_error = RetrievalError(
                        f"Cohere devolvió {response.status}: {(await response.text())[:200]}"
                    )
                elif response.status != 200:
                    # 4xx que no es rate limit: reintentar no va a ayudar.
                    raise RetrievalError(
                        f"Cohere devolvió {response.status}: {(await response.text())[:200]}"
                    )
                else:
                    data = await response.json()
                    return data["embeddings"]["float"]
        except asyncio.TimeoutError as exc:
            last_error = RetrievalError(
                f"timeout de {settings.embed_timeout_s}s embebiendo en Cohere"
            )
            last_error.__cause__ = exc
        except aiohttp.ClientError as exc:
            last_error = RetrievalError(f"error de red hablando con Cohere: {exc}")
            last_error.__cause__ = exc

        if attempt == 1:
            logger.warning("embedding falló (intento 1), reintentando: %s", last_error)
            await asyncio.sleep(0.15)

    raise last_error or RetrievalError("no se pudo embeber la consulta")
