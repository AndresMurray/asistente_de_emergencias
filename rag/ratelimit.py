"""Throttle compartido de Cohere.

La key del proyecto es Trial, con tope de 10 llamadas por minuto (confirmado
por los headers `x-trial-endpoint-call-limit`) y 1000 por mes. Hay varios
consumidores en el mismo proceso: el retriever (rerank) y las métricas (STS,
coverage). Sin un límite compartido, cada uno espera su propio 429 y entre
todos pegan rate limit en cadena.

La solución es espaciar: una llamada cada `intervalo_s` como mínimo, a nivel
proceso. El intervalo se eligió con margen sobre las 10 llamadas por minuto:
    60 s / 10 llamadas = 6 s  ->  intervalo de 7 s  ->  ~8.5 llamadas/min

Hay dos formas de pedir turno:
- `esperar_turno()` bloquea hasta que haya lugar. Sirve para scripts offline
  (métricas, generación del caché), donde esperar no le cuesta nada a nadie.
- `intentar_turno()` NO espera: si no hay lugar devuelve False y el caller
  sigue sin rerankear. Es la que usa el turno en vivo. Antes el retriever
  usaba la versión bloqueante, y como el presupuesto total de la búsqueda es de
  4 s, una segunda búsqueda dentro de los 7 s terminaba en timeout y el agente
  decía "perdí el acceso al manual".
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


def intentar_turno() -> bool:
    """Toma el turno si está libre ya mismo; si no, devuelve False sin esperar."""
    global _proxima
    ahora = time.monotonic()
    if _lock.locked() or ahora < _proxima:
        return False
    _proxima = ahora + _INTERVALO_S
    return True
