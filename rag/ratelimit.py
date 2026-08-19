"""Throttle compartido de Cohere.

La key del proyecto es Trial, con tope de ~10 llamadas por minuto entre TODOS
los endpoints (embed y rerank gastan de la misma cuota). Hay varios consumidores
en el mismo proceso: el retriever (embed + rerank) y las métricas (STS, coverage).
Sin un límite compartido, cada uno espera su propio 429 y entre todos pegan
rate limit en cadena.

La solución es serializar: una llamada cada `intervalo_s` como mínimo, a nivel
proceso. El intervalo se eligió con margen sobre las 10 llamadas por minuto:
    60 s / 10 llamadas = 6 s  ->  intervalo de 7 s  ->  ~8.5 llamadas/min
"""

from __future__ import annotations

import asyncio
import time

_INTERVALO_S = 7.0

_lock = asyncio.Lock()
_proxima = 0.0


async def esperar_turno() -> None:
    """Espera el tiempo que falte para que la ventana tenga lugar libre."""
    global _proxima
    async with _lock:
        ahora = time.monotonic()
        espera = _proxima - ahora
        if espera > 0:
            await asyncio.sleep(espera)
        _proxima = max(_proxima + _INTERVALO_S, time.monotonic() + _INTERVALO_S)
