"""Metrónomo para marcar el ritmo de las compresiones de RCP.

Por qué un clic y no que el agente cuente «uno, dos, tres»: el TTS tiene
latencia y prosodia irregular, y el ritmo se corta cada vez que el modelo
piensa. El clic va en un track de audio aparte (BackgroundAudioPlayer), así que
sigue parejo aunque el agente hable encima.

Lo prende y lo apaga entrypoint en agent.py a partir del estado de triage
(triage.rcp_en_curso), nunca el modelo: con un inconsciente al que todavía no
se le verificó la respiración no puede sonar.

Ritmo: el manual dice «casi dos compresiones por segundo»; las guías, de 100 a
120 por minuto. 110 queda en el medio y no cae debajo de 100 cuando quien
comprime se cansa.

En `agent.py console` LiveKit no reproduce el audio de fondo, así que ahí el
clic sale directo por los parlantes de la compu (sounddevice, que ya viene con
livekit-agents). En ensayo.py no hay sala ni audio: iniciar() y detener() no
hacen nada.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import AsyncIterator, Iterator

import numpy as np

from livekit import rtc
from livekit.agents import AudioConfig, BackgroundAudioPlayer, PlayHandle, get_job_context

logger = logging.getLogger("metronomo")

SAMPLE_RATE = 48000
_FRAME_MS = 20


def clic(sample_rate: int = SAMPLE_RATE, frecuencia: float = 1000.0, duracion: float = 0.03) -> np.ndarray:
    """Un golpe corto y seco: seno de 1 kHz con caída exponencial, en int16."""
    t = np.arange(int(sample_rate * duracion)) / sample_rate
    onda = np.sin(2 * np.pi * frecuencia * t) * np.exp(-t / 0.006)
    return (onda * 0.9 * 32767).astype(np.int16)


def bloques(bpm: float, sample_rate: int = SAMPLE_RATE, frame_ms: int = _FRAME_MS) -> Iterator[np.ndarray]:
    """Bloques de audio infinitos con un clic cada 60/bpm segundos.

    Cada clic se ubica en round(k * período) a partir de la muestra 0, no
    sumando períodos: así el ritmo no acumula error de redondeo con el tiempo."""
    golpe = clic(sample_rate)
    periodo = sample_rate * 60.0 / bpm
    n = sample_rate * frame_ms // 1000
    inicio = 0
    while True:
        buf = np.zeros(n, dtype=np.int16)
        # Clics que tocan [inicio, inicio + n), incluida la cola de uno anterior.
        k = max(0, int(np.ceil((inicio - len(golpe) + 1) / periodo)))
        while (pos := round(k * periodo)) < inicio + n:
            desde, hasta = max(pos, inicio), min(pos + len(golpe), inicio + n)
            if desde < hasta:
                buf[desde - inicio : hasta - inicio] = golpe[desde - pos : hasta - pos]
            k += 1
        yield buf
        inicio += n


async def frames_metronomo(bpm: float, sample_rate: int = SAMPLE_RATE) -> AsyncIterator[rtc.AudioFrame]:
    """Los bloques como AudioFrame. El ritmo en tiempo real lo impone el
    AudioSource del BackgroundAudioPlayer, que frena cuando su cola se llena."""
    for buf in bloques(bpm, sample_rate):
        yield rtc.AudioFrame(buf.tobytes(), sample_rate, 1, len(buf))


# «Pará el sonido», «sacá ese ruido»: la persona puede apagarlo a voluntad.
_APAGAR = re.compile(
    r"\b(par[aá]|apag[aá]|sac[aá]|cort[aá]|quit[aá]|baj[aá]|silenci[aá])\w*\b[^.?!]{0,20}"
    r"\b(sonido|ruido|ritmo|metr[oó]nomo|pitido|clic|tic)",
    re.IGNORECASE,
)
_PRENDER = re.compile(
    r"\b(pon[eé]|prend[eé]|volv[eé] a poner|activ[aá])\w*\b[^.?!]{0,20}"
    r"\b(sonido|ritmo|metr[oó]nomo|pitido|clic|tic)",
    re.IGNORECASE,
)


def pide_apagar(texto: str) -> bool:
    return bool(_APAGAR.search(texto))


def pide_prender(texto: str) -> bool:
    return bool(_PRENDER.search(texto)) and not pide_apagar(texto)


def _env_float(nombre: str, defecto: float) -> float:
    valor = os.getenv(nombre)
    return float(valor) if valor and valor.strip() else defecto


class Metronomo:
    def __init__(self, bpm: float | None = None, volumen: float | None = None) -> None:
        self.bpm = bpm or _env_float("METRONOMO_BPM", 110.0)
        self.volumen = volumen if volumen is not None else _env_float("METRONOMO_VOLUMEN", 0.35)
        self.habilitado = os.getenv("METRONOMO", "on").strip().lower() not in {"0", "off", "false", "no"}
        # Tope de tiempo seguido sonando: un clic eterno molesta y termina
        # tapando la conversación. Al vencer se apaga y el agente lo avisa.
        self.max_s = _env_float("METRONOMO_MAX_MIN", 5.0) * 60
        self._desde: float | None = None
        self._player: BackgroundAudioPlayer | None = None
        self._handle: PlayHandle | None = None
        # Modo consola: el clic va directo a los parlantes locales.
        self._consola = False
        self._parlante = None  # sounddevice.OutputStream mientras suena

    async def start(self, room: rtc.Room) -> None:
        """Publica el track de audio. Si no se puede (sala caída), el
        metrónomo queda deshabilitado: la llamada sigue igual, sin clic."""
        if not self.habilitado:
            logger.info("metrónomo deshabilitado por METRONOMO")
            return
        try:
            self._consola = get_job_context().is_fake_job()
        except RuntimeError:
            self._consola = False
        if self._consola:
            logger.info("modo consola: el metrónomo suena por los parlantes de la compu")
            return
        try:
            player = BackgroundAudioPlayer()
            await player.start(room=room)
            self._player = player
        except Exception:
            logger.exception("no pude publicar el track del metrónomo; sigo sin metrónomo")

    @property
    def activo(self) -> bool:
        if self._parlante is not None:
            return True
        return self._handle is not None and not self._handle.done()

    @property
    def encendido_hace(self) -> float:
        """Segundos que lleva sonando sin cortar (0 si está apagado)."""
        return time.monotonic() - self._desde if self.activo and self._desde is not None else 0.0

    def iniciar(self) -> bool:
        """Empieza a sonar. Devuelve True solo si arrancó en esta llamada."""
        if self.activo:
            return False
        if self._consola:
            arranco = self._iniciar_en_parlantes()
            if arranco:
                self._desde = time.monotonic()
            return arranco
        if self._player is None:
            return False
        self._desde = time.monotonic()
        self._handle = self._player.play(
            AudioConfig(frames_metronomo(self.bpm), volume=self.volumen, fade_in=0.15)
        )
        logger.info("metrónomo encendido | bpm=%s volumen=%s", self.bpm, self.volumen)
        return True

    def _iniciar_en_parlantes(self) -> bool:
        try:
            import sounddevice as sd

            generador = bloques(self.bpm)
            volumen = self.volumen

            def llenar(salida, _frames, _tiempo, _estado) -> None:
                # Corre en el hilo de audio: cada bloque mide lo mismo que el
                # blocksize del stream (20 ms).
                salida[:, 0] = (next(generador) * volumen).astype(np.int16)

            parlante = sd.OutputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=SAMPLE_RATE * _FRAME_MS // 1000, callback=llenar,
            )
            parlante.start()
        except Exception:
            logger.exception("no pude abrir los parlantes para el metrónomo")
            return False
        self._parlante = parlante
        logger.info("metrónomo encendido (parlantes locales) | bpm=%s volumen=%s", self.bpm, self.volumen)
        return True

    def detener(self) -> bool:
        """Deja de sonar. Devuelve True solo si estaba sonando."""
        if not self.activo:
            return False
        self._desde = None
        if self._parlante is not None:
            self._parlante.stop()
            self._parlante.close()
            self._parlante = None
        else:
            assert self._handle is not None
            self._handle.stop()
            self._handle = None
        logger.info("metrónomo apagado")
        return True

    async def aclose(self) -> None:
        self.detener()
        if self._player is not None:
            await self._player.aclose()
            self._player = None
