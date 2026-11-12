"""Reconocimiento de voz en vivo con Deepgram, por WebSocket directo.

Reemplaza a livekit.plugins.deepgram.STT. Además de transcribir, acá Deepgram
hace de detector de fin de turno: LiveKit usa su propio VAD y un modelo de fin
de turno; el orquestador se apoya en `speech_final` (silencio después de
hablar) y en `UtteranceEnd` (respaldo cuando hay ruido de fondo), y la sesión
decide cuánto más esperar antes de dar el turno por terminado.

Referencia de los eventos:
https://developers.deepgram.com/docs/understand-endpointing-interim-results
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import urlencode

import aiohttp

logger = logging.getLogger("orquestador.stt")

URL = "wss://api.deepgram.com/v1/listen"
_KEEPALIVE = json.dumps({"type": "KeepAlive"})
_CERRAR = json.dumps({"type": "CloseStream"})
_MAX_REINTENTOS = 5
# Audio en espera de salir mientras la conexión se rearma (~4 s a 20 ms por bloque).
_MAX_COLA = 200


@dataclass
class EventoSTT:
    # habla: Deepgram detectó voz (sin texto todavía).
    # transcripcion: texto parcial o final.
    # fin_enunciado: pasó el silencio de utterance_end_ms.
    # error: no se pudo (re)conectar; el reconocimiento quedó caído.
    tipo: Literal["habla", "transcripcion", "fin_enunciado", "error"]
    texto: str = ""
    # El tramo ya no va a cambiar (is_final).
    final: bool = False
    # Deepgram detectó silencio después de este tramo (speech_final).
    fin_de_habla: bool = False
    # Momento (reloj monotónico) en que terminó la última palabra del tramo.
    fin_audio: float | None = None


class STT(Protocol):
    async def iniciar(self) -> None: ...

    def enviar_audio(self, pcm: bytes) -> None: ...

    def eventos(self) -> AsyncIterator[EventoSTT]: ...

    async def cerrar(self) -> None: ...


class STTDeepgram:
    def __init__(
        self,
        api_key: str,
        *,
        sample_rate: int = 16000,
        modelo: str = "nova-3",
        idioma: str = "es",
        keyterms: Sequence[str] = (),
        # Silencio que Deepgram espera para avisar «dejó de hablar». Corto a
        # propósito: el aviso solo dispara el borrador de la respuesta; cuánto
        # silencio cierra el turno lo decide la sesión (Config.silencio_*).
        endpointing_ms: int = 25,
        utterance_end_ms: int = 1000,
        http: aiohttp.ClientSession | None = None,
    ) -> None:
        self._api_key = api_key
        self._sample_rate = sample_rate
        parametros: dict[str, object] = {
            "model": modelo,
            "language": idioma,
            "encoding": "linear16",
            "sample_rate": sample_rate,
            "channels": 1,
            "interim_results": "true",
            # La puntuación es la pista de que la frase terminó («Sí.» cierra
            # el turno antes que «Sí, pero»).
            "punctuate": "true",
            "smart_format": "false",
            "vad_events": "true",
            "endpointing": endpointing_ms,
            "utterance_end_ms": utterance_end_ms,
            # «eh», «mmm»: no aportan al triage y contarían como palabras para interrumpir.
            "filler_words": "false",
        }
        if keyterms and modelo.startswith("nova-3"):
            parametros["keyterm"] = list(keyterms)
        self._url = f"{URL}?{urlencode(parametros, doseq=True)}"
        self._http = http
        self._http_propio = http is None
        self._salida: asyncio.Queue[bytes] = asyncio.Queue(maxsize=_MAX_COLA)
        self._eventos: asyncio.Queue[EventoSTT | None] = asyncio.Queue()
        self._tarea: asyncio.Task[None] | None = None
        self._cerrado = False
        # Segundos de audio mandados por esta conexión. Sirve para pasar del
        # tiempo del audio (el «end» de cada palabra) al reloj: si ya se
        # mandaron 12,0 s y la palabra terminó en 11,4, terminó hace 0,6 s.
        # No se usa la hora del primer bloque: mientras la conexión se abre el
        # audio se acumula y sale de golpe, y eso corría el reloj medio segundo.
        self._enviado_s = 0.0

    async def iniciar(self) -> None:
        if self._http is None:
            self._http = aiohttp.ClientSession()
        self._tarea = asyncio.create_task(self._bucle(), name="stt-deepgram")

    def enviar_audio(self, pcm: bytes) -> None:
        if self._cerrado:
            return
        if self._salida.full():
            # Conexión caída o lenta: se pierde el audio más viejo, no el nuevo.
            self._salida.get_nowait()
        self._salida.put_nowait(pcm)

    async def eventos(self) -> AsyncIterator[EventoSTT]:
        while True:
            evento = await self._eventos.get()
            if evento is None:
                return
            yield evento

    async def cerrar(self) -> None:
        self._cerrado = True
        if self._tarea is not None:
            self._tarea.cancel()
            await asyncio.gather(self._tarea, return_exceptions=True)
            self._tarea = None
        if self._http_propio and self._http is not None:
            await self._http.close()
            self._http = None
        self._eventos.put_nowait(None)

    # -- conexión ---------------------------------------------------------------

    async def _bucle(self) -> None:
        assert self._http is not None
        fallos = 0
        while not self._cerrado:
            try:
                async with self._http.ws_connect(
                    self._url, headers={"Authorization": f"Token {self._api_key}"}
                ) as ws:
                    logger.info("Deepgram STT conectado")
                    fallos = 0
                    self._enviado_s = 0.0
                    auxiliares = [
                        asyncio.create_task(self._enviar(ws), name="stt-envio"),
                        asyncio.create_task(self._mantener(ws), name="stt-keepalive"),
                    ]
                    try:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    self._procesar(json.loads(msg.data))
                                except Exception:
                                    # Un mensaje raro no puede tirar la conexión
                                    # (y con ella lo que la persona está diciendo).
                                    logger.exception("no pude procesar un mensaje de Deepgram")
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                break
                    finally:
                        for t in auxiliares:
                            t.cancel()
                        await asyncio.gather(*auxiliares, return_exceptions=True)
                        if not ws.closed:
                            try:
                                await ws.send_str(_CERRAR)
                            except Exception:
                                pass
                if self._cerrado:
                    return
                logger.warning("Deepgram STT cerró la conexión (código %s)", ws.close_code)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Deepgram STT: %s", exc)
            fallos += 1
            if fallos > _MAX_REINTENTOS:
                logger.error("Deepgram STT: no pude reconectar después de %d intentos", _MAX_REINTENTOS)
                self._eventos.put_nowait(EventoSTT("error", texto="el reconocimiento de voz no responde"))
                return
            await asyncio.sleep(min(0.25 * 2**fallos, 4.0))

    async def _enviar(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while True:
            pcm = await self._salida.get()
            await ws.send_bytes(pcm)
            self._enviado_s += len(pcm) / (2 * self._sample_rate)

    async def _mantener(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        # Deepgram corta a los 10 s sin audio; antes del saludo el micrófono
        # del navegador todavía está apagado.
        while True:
            await asyncio.sleep(4.0)
            await ws.send_str(_KEEPALIVE)

    # -- eventos ----------------------------------------------------------------

    def _procesar(self, datos: dict) -> None:
        tipo = datos.get("type")
        if logger.isEnabledFor(logging.DEBUG) and tipo != "Metadata":
            # En «Results» channel es un objeto; en los demás eventos, una lista.
            canal = datos.get("channel")
            alt = (canal.get("alternatives") or [{}])[0] if isinstance(canal, dict) else {}
            if tipo != "Results" or alt.get("transcript") or datos.get("speech_final"):
                logger.debug(
                    "deepgram %s final=%s fin_de_habla=%s «%s»",
                    tipo, datos.get("is_final"), datos.get("speech_final"), alt.get("transcript", ""),
                )
        if tipo == "SpeechStarted":
            self._eventos.put_nowait(EventoSTT("habla"))
        elif tipo == "UtteranceEnd":
            self._eventos.put_nowait(EventoSTT("fin_enunciado"))
        elif tipo == "Results":
            canal = datos.get("channel")
            alt = (canal.get("alternatives") or [{}])[0] if isinstance(canal, dict) else {}
            texto = (alt.get("transcript") or "").strip()
            fin_de_habla = bool(datos.get("speech_final"))
            if not texto and not fin_de_habla:
                return
            fin_audio = None
            palabras = alt.get("words") or []
            if palabras:
                hace = max(0.0, self._enviado_s - float(palabras[-1].get("end", 0.0)))
                fin_audio = time.monotonic() - hace
            self._eventos.put_nowait(EventoSTT(
                "transcripcion",
                texto=texto,
                final=bool(datos.get("is_final")),
                fin_de_habla=fin_de_habla,
                fin_audio=fin_audio,
            ))
        elif tipo == "Error":
            logger.error("Deepgram STT devolvió un error: %s", datos)
