"""Embeddings con Google AI Studio (gemini-embedding-001).

Genera vectores de 768 dimensiones optimizados para búsqueda semántica.
Utiliza aiohttp reutilizando la sesión compartida con keepalive.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from .config import RagSettings
from .errors import RetrievalError
from .session import cohere_session

logger = logging.getLogger("rag.embeddings")


async def embed_query(
    text: str, settings: RagSettings, *, intentos: int = 3, pausa_s: float = 0.05
) -> list[float]:
    """Embebe la consulta del usuario usando taskType RETRIEVAL_QUERY.

    El plan gratuito de Google devuelve 429 ("Resource exhausted") en ~70% de
    las llamadas aunque se espacien (medido 2026-09). Cada 429 vuelve en ~260
    ms, así que tres intentos rápidos entran en el presupuesto del turno; si
    igual falla, el retriever cae a la búsqueda léxica en memoria. Para scripts
    offline (generar el caché) conviene pasar más intentos y pausas largas.
    """
    if not settings.gemini_api_key:
        raise RetrievalError("GEMINI_API_KEY no está configurada")

    url = f"{settings.gemini_embed_url}?key={settings.gemini_api_key}"
    payload = {
        "model": f"models/{settings.embed_model}",
        "content": {"parts": [{"text": text}]},
        "taskType": "RETRIEVAL_QUERY",
        "outputDimensionality": 768,
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.gemini_api_key,
    }
    timeout = aiohttp.ClientTimeout(total=settings.embed_timeout_s, connect=0.5)

    last_error: Exception | None = None
    for attempt in range(1, intentos + 1):
        try:
            async with cohere_session().post(
                url, headers=headers, json=payload, timeout=timeout
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["embedding"]["values"]
                elif response.status in (429, 500, 503):
                    last_error = RetrievalError(
                        f"Google AI devolvió {response.status}: {(await response.text())[:120]}"
                    )
                else:
                    raise RetrievalError(
                        f"Google AI devolvió {response.status}: {(await response.text())[:200]}"
                    )
        except asyncio.TimeoutError as exc:
            last_error = RetrievalError(
                f"timeout de {settings.embed_timeout_s}s embebiendo en Google AI"
            )
            last_error.__cause__ = exc
        except aiohttp.ClientError as exc:
            last_error = RetrievalError(f"error de red hablando con Google AI: {exc}")
            last_error.__cause__ = exc

        if attempt < intentos:
            logger.info("embedding falló (intento %d), reintentando: %s", attempt, last_error)
            await asyncio.sleep(pausa_s)

    raise last_error or RetrievalError("no se pudo embeber la consulta con Google AI")


async def embed_documents(texts: list[str], settings: RagSettings) -> list[list[float]]:
    """Embebe documentos para ingesta usando taskType RETRIEVAL_DOCUMENT.

    Google batchEmbedContents acepta hasta 100 textos por llamada.
    """
    if not settings.gemini_api_key:
        raise RetrievalError("GEMINI_API_KEY no está configurada")

    if not texts:
        return []

    url = f"{settings.gemini_batch_embed_url}?key={settings.gemini_api_key}"
    requests_payload = [
        {
            "model": f"models/{settings.embed_model}",
            "content": {"parts": [{"text": t}]},
            "taskType": "RETRIEVAL_DOCUMENT",
            "outputDimensionality": 768,
        }
        for t in texts
    ]

    payload = {"requests": requests_payload}
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.gemini_api_key,
    }
    timeout = aiohttp.ClientTimeout(total=30.0, connect=2.0)

    try:
        async with cohere_session().post(
            url, headers=headers, json=payload, timeout=timeout
        ) as response:
            if response.status != 200:
                raise RetrievalError(
                    f"Google batchEmbedContents devolvió {response.status}: {(await response.text())[:300]}"
                )
            data = await response.json()
            return [emb["values"] for emb in data.get("embeddings", [])]
    except Exception as exc:
        raise RetrievalError(f"error al generar embeddings en lote: {exc}") from exc

