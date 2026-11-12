"""Acompañamiento de la RCP en el orquestador propio: metrónomo y aliento.

Misma regla que en agent.py: lo prende y lo apaga la sesión a partir del estado
de triage (triage.rcp_en_curso), nunca el modelo.

Diferencia con LiveKit: allá el clic viaja como audio en un track aparte. Acá
el servidor solo avisa «prendé el ritmo a tantos golpes por minuto» y el clic
lo genera el cliente con su propio reloj de audio. El ritmo sale parejo aunque
la red tenga saltos, y una interrupción (que vacía el audio de la voz) no lo
corta.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from metronomo import _env_float
from nucleo import FRASE_FIN_METRONOMO, FRASES_ALIENTO_RCP

if TYPE_CHECKING:
    from .sesion import Sesion

logger = logging.getLogger("orquestador.rcp")


class MetronomoRemoto:
    def __init__(self, avisar: Callable[[dict[str, Any]], None]) -> None:
        self._avisar = avisar
        self.bpm = _env_float("METRONOMO_BPM", 110.0)
        self.volumen = _env_float("METRONOMO_VOLUMEN", 0.35)
        self.habilitado = os.getenv("METRONOMO", "on").strip().lower() not in {"0", "off", "false", "no"}
        self.max_s = _env_float("METRONOMO_MAX_MIN", 5.0) * 60
        self._desde: float | None = None

    @property
    def activo(self) -> bool:
        return self._desde is not None

    @property
    def encendido_hace(self) -> float:
        return time.monotonic() - self._desde if self._desde is not None else 0.0

    def iniciar(self) -> bool:
        """Empieza a sonar. Devuelve True solo si arrancó en esta llamada."""
        if self.activo or not self.habilitado:
            return False
        self._desde = time.monotonic()
        self._avisar({"type": "metronomo", "activo": True, "bpm": self.bpm, "volumen": self.volumen})
        logger.info("metrónomo encendido | bpm=%s volumen=%s", self.bpm, self.volumen)
        return True

    def detener(self) -> bool:
        """Deja de sonar. Devuelve True solo si estaba sonando."""
        if not self.activo:
            return False
        self._desde = None
        self._avisar({"type": "metronomo", "activo": False})
        logger.info("metrónomo apagado")
        return True


class AlientoRCP:
    """Una frase corta de aliento cada tanto mientras la persona comprime en
    silencio, y el tope de tiempo del metrónomo. Mismo comportamiento que
    AlientoRCP de agent.py."""

    def __init__(self, sesion: Sesion, metronomo: MetronomoRemoto, cada_s: float = 20.0) -> None:
        self._sesion = sesion
        self._metronomo = metronomo
        self._cada_s = cada_s
        self._ultima_actividad = time.monotonic()
        self._siguiente = 0
        self._tarea: asyncio.Task[None] | None = None

    def actividad(self) -> None:
        self._ultima_actividad = time.monotonic()

    def iniciar(self) -> None:
        if self._tarea is None or self._tarea.done():
            self.actividad()
            self._tarea = asyncio.create_task(self._bucle(), name="aliento-rcp")

    def cerrar(self) -> None:
        if self._tarea is not None:
            self._tarea.cancel()

    async def _bucle(self) -> None:
        sesion = self._sesion
        while self._metronomo.activo:
            await asyncio.sleep(1.0)
            if self._metronomo.encendido_hace >= self._metronomo.max_s:
                # Tope de tiempo: no puede quedar sonando indefinidamente.
                self._metronomo.detener()
                sesion.estado.metronomo_activo = False
                sesion.estado.metronomo_silenciado = True
                logger.info("metrónomo: se cumplió el tope de %.0f s", self._metronomo.max_s)
                sesion.decir(FRASE_FIN_METRONOMO)
                return
            quieto = sesion.estado_agente == "escuchando" and sesion.estado_usuario != "hablando"
            if quieto and time.monotonic() - self._ultima_actividad >= self._cada_s:
                sesion.decir(FRASES_ALIENTO_RCP[self._siguiente % len(FRASES_ALIENTO_RCP)])
                self._siguiente += 1
                self.actividad()
