"""Session HTTP compartida para llamadas a Cohere.

Dentro de un job de LiveKit se usa la session del proceso (http_context).
Fuera (tests, scripts de metricas/) no existe y hay que crear una propia;
el docstring anterior lo prometía pero no lo implementaba, y cada llamada
explotaba con RuntimeError.
"""

from __future__ import annotations

import aiohttp

_fallback: aiohttp.ClientSession | None = None


def cohere_session() -> aiohttp.ClientSession:
    """Session del job si hay, o una propia cacheada si se corre fuera."""
    global _fallback

    from livekit.agents.utils import http_context

    try:
        return http_context.http_session()
    except RuntimeError:
        if _fallback is None:
            _fallback = aiohttp.ClientSession()
        return _fallback


async def close_fallback() -> None:
    """Cierra la session propia si se creó (para scripts que corren y terminan)."""
    global _fallback
    if _fallback is not None:
        await _fallback.close()
        _fallback = None