"""Síntesis de voz por streaming: Cartesia (WebSocket) y Deepgram Aura (HTTP).

Reemplaza a livekit.plugins.cartesia.TTS. Todos los proveedores entregan PCM de
16 bits, mono, a SAMPLE_RATE, así la sesión y el cliente no tienen que saber
quién habló.

Cartesia además devuelve en qué segundo termina cada palabra. La sesión lo usa
para saber qué se llegó a decir cuando la persona interrumpe: el triage
interpreta un «sí» según la última pregunta que el agente EFECTIVAMENTE hizo.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import aiohttp

logger = logging.getLogger("orquestador.tts")

SAMPLE_RATE = 24000

CARTESIA_URL = "wss://api.cartesia.ai/tts/websocket"
CARTESIA_VERSION = "2025-04-16"
CARTESIA_VOZ = "b4b8e2af-6139-466e-a93a-30c20d2e1fc5"
DEEPGRAM_URL = "https://api.deepgram.com/v1/speak"


class TTSError(RuntimeError):
    """El proveedor de voz falló."""


@dataclass
class Audio:
    pcm: bytes


@dataclass
class Palabras:
    # (palabra, segundo en que termina, contado desde el inicio del audio)
    palabras: list[tuple[str, float]]


EventoTTS = Audio | Palabras


class TTS(Protocol):
    nombre: str

    def sintetizar(self, oraciones: AsyncIterator[str]) -> AsyncIterator[EventoTTS]: ...

    async def cerrar(self) -> None: ...


class TTSCartesia:
    """Una conexión por sesión, reutilizada entre respuestas: abrir el WebSocket
    cuesta unos 200 ms, que se notarían al principio de cada turno."""

    nombre = "cartesia"

    def __init__(
        self,
        api_key: str,
        *,
        voz: str = CARTESIA_VOZ,
        modelo: str = "sonic-3",
        idioma: str = "es",
        espera_s: float = 8.0,
        http: aiohttp.ClientSession | None = None,
    ) -> None:
        self._api_key = api_key
        self._base = {
            "model_id": modelo,
            "voice": {"mode": "id", "id": voz},
            "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": SAMPLE_RATE},
            "language": idioma,
            "add_timestamps": True,
        }
        self._espera_s = espera_s
        self._http = http
        self._http_propio = http is None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._candado = asyncio.Lock()

    async def preparar(self) -> None:
        """Abre la conexión antes de la primera frase (opcional)."""
        async with self._candado:
            await self._conectar()

    async def _conectar(self) -> aiohttp.ClientWebSocketResponse:
        if self._ws is not None and not self._ws.closed:
            return self._ws
        if self._http is None:
            self._http = aiohttp.ClientSession()
        try:
            self._ws = await asyncio.wait_for(
                self._http.ws_connect(
                    f"{CARTESIA_URL}?cartesia_version={CARTESIA_VERSION}",
                    headers={"X-API-Key": self._api_key},
                ),
                self._espera_s,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            raise TTSError(f"no pude conectar con Cartesia: {exc!r}") from exc
        return self._ws

    async def sintetizar(self, oraciones: AsyncIterator[str]) -> AsyncIterator[EventoTTS]:
        contexto = uuid.uuid4().hex
        async with self._candado:
            ws = await self._conectar()
            envio = asyncio.create_task(self._enviar(ws, contexto, oraciones), name="tts-envio")
            completo = False
            roto = False
            try:
                while True:
                    recibir = asyncio.ensure_future(ws.receive(timeout=self._espera_s))
                    # Si falla el envío no hay que quedarse esperando audio.
                    await asyncio.wait({recibir, envio}, return_when=asyncio.FIRST_COMPLETED)
                    if envio.done() and envio.exception() is not None:
                        recibir.cancel()
                        raise envio.exception()  # type: ignore[misc]
                    msg = await recibir
                    if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                        raise TTSError(f"Cartesia cerró la conexión (código {ws.close_code})")
                    if msg.type == aiohttp.WSMsgType.ERROR:
                        raise TTSError(f"error en la conexión con Cartesia: {ws.exception()!r}")
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    datos = json.loads(msg.data)
                    if datos.get("context_id") not in (None, contexto):
                        continue  # restos de una respuesta anterior que se canceló
                    if datos.get("type") == "error":
                        raise TTSError(f"Cartesia devolvió un error: {datos.get('error') or datos}")
                    if datos.get("data"):
                        yield Audio(base64.b64decode(datos["data"]))
                    elif tiempos := datos.get("word_timestamps"):
                        yield Palabras(list(zip(tiempos["words"], tiempos["end"], strict=False)))
                    elif datos.get("done"):
                        completo = True
                        return
            except asyncio.TimeoutError as exc:
                roto = True
                raise TTSError(f"Cartesia no respondió en {self._espera_s:.0f} s") from exc
            except (aiohttp.ClientError, OSError) as exc:
                roto = True
                raise TTSError(f"se cortó la conexión con Cartesia: {exc!r}") from exc
            except TTSError:
                roto = True
                raise
            finally:
                envio.cancel()
                await asyncio.gather(envio, return_exceptions=True)
                if roto:
                    # Conexión en estado dudoso: la próxima frase abre una nueva.
                    self._ws = None
                    try:
                        await ws.close()
                    except Exception:
                        pass
                elif not completo and not ws.closed:
                    # Interrupción: que Cartesia deje de generar (y de cobrar) esta respuesta.
                    try:
                        await ws.send_str(json.dumps({"context_id": contexto, "cancel": True}))
                    except Exception:
                        pass

    async def _enviar(
        self, ws: aiohttp.ClientWebSocketResponse, contexto: str, oraciones: AsyncIterator[str]
    ) -> None:
        async for oracion in oraciones:
            await ws.send_str(json.dumps({
                **self._base,
                "context_id": contexto,
                "transcript": oracion + " ",
                "continue": True,
                # Ya llega cortado por oraciones: que no espere a juntar más texto.
                "max_buffer_delay_ms": 0,
            }))
        await ws.send_str(json.dumps({**self._base, "context_id": contexto, "transcript": " ", "continue": False}))

    async def cerrar(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        if self._http_propio and self._http is not None:
            await self._http.close()
            self._http = None


class TTSDeepgram:
    """Deepgram Aura por HTTP, una oración por pedido. No devuelve tiempos por
    palabra: ante una interrupción la sesión estima lo dicho por duración."""

    nombre = "deepgram"

    def __init__(
        self,
        api_key: str,
        *,
        modelo: str = "aura-2-agustina-es",
        espera_s: float = 8.0,
        http: aiohttp.ClientSession | None = None,
    ) -> None:
        self._api_key = api_key
        self._modelo = modelo
        self._espera_s = espera_s
        self._http = http
        self._http_propio = http is None

    async def sintetizar(self, oraciones: AsyncIterator[str]) -> AsyncIterator[EventoTTS]:
        if self._http is None:
            self._http = aiohttp.ClientSession()
        async for oracion in oraciones:
            try:
                async with self._http.post(
                    DEEPGRAM_URL,
                    params={
                        "model": self._modelo,
                        "encoding": "linear16",
                        "sample_rate": str(SAMPLE_RATE),
                        "container": "none",
                    },
                    headers={"Authorization": f"Token {self._api_key}"},
                    json={"text": oracion},
                    timeout=aiohttp.ClientTimeout(total=30, sock_connect=5, sock_read=self._espera_s),
                ) as resp:
                    if resp.status >= 400:
                        cuerpo = (await resp.text())[:200]
                        raise TTSError(f"Deepgram TTS respondió {resp.status}: {cuerpo}")
                    resto = b""
                    async for datos in resp.content.iter_any():
                        # Las muestras son de 2 bytes: no se parte una al medio.
                        datos = resto + datos
                        completo = len(datos) - (len(datos) % 2)
                        resto = datos[completo:]
                        if completo:
                            yield Audio(datos[:completo])
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                raise TTSError(f"Deepgram TTS: {exc!r}") from exc

    async def cerrar(self) -> None:
        if self._http_propio and self._http is not None:
            await self._http.close()
            self._http = None


class _TextoRepetible:
    """El texto de una respuesta, que se puede volver a leer desde el principio.

    El texto llega de a tramos mientras el LLM genera. Lo lee una tarea aparte:
    si un proveedor falla y su lectura se cancela, la fuente no se pierde y el
    proveedor siguiente arranca desde la primera oración."""

    def __init__(self, fuente: AsyncIterator[str]) -> None:
        self._oraciones: list[str] = []
        self._fin = False
        self._novedad = asyncio.Event()
        self._tarea = asyncio.create_task(self._leer(fuente), name="tts-texto")

    async def _leer(self, fuente: AsyncIterator[str]) -> None:
        try:
            async for oracion in fuente:
                self._oraciones.append(oracion)
                self._novedad.set()
        finally:
            self._fin = True
            self._novedad.set()

    async def desde_el_principio(self) -> AsyncIterator[str]:
        i = 0
        while True:
            while i < len(self._oraciones):
                yield self._oraciones[i]
                i += 1
            if self._fin:
                return
            self._novedad.clear()
            if i < len(self._oraciones) or self._fin:
                continue
            await self._novedad.wait()

    async def cerrar(self) -> None:
        self._tarea.cancel()
        await asyncio.gather(self._tarea, return_exceptions=True)


class TTSConRespaldo:
    """Prueba los proveedores en orden. Si uno falla antes de dar audio, el
    siguiente dice la misma frase desde el principio; si falla a mitad de la
    frase, el error sube (parte ya se escuchó)."""

    def __init__(self, proveedores: list[TTS]) -> None:
        if not proveedores:
            raise ValueError("hace falta al menos un proveedor de TTS")
        self._proveedores = proveedores
        # El que falla dos veces seguidas baja al final: no tiene sentido pagar
        # el error en cada frase. Una sola falla puede ser una conexión que el
        # proveedor cerró por estar ociosa; la frase siguiente abre otra.
        self._orden = list(range(len(proveedores)))
        self._fallos = [0] * len(proveedores)

    @property
    def nombre(self) -> str:
        return " -> ".join(self._proveedores[i].nombre for i in self._orden)

    async def sintetizar(self, oraciones: AsyncIterator[str]) -> AsyncIterator[EventoTTS]:
        texto = _TextoRepetible(oraciones)
        ultimo: Exception | None = None
        try:
            for indice in list(self._orden):
                proveedor = self._proveedores[indice]
                emitio = False
                stream = proveedor.sintetizar(texto.desde_el_principio())
                try:
                    async for evento in stream:
                        emitio = emitio or isinstance(evento, Audio)
                        yield evento
                    self._fallos[indice] = 0
                    return
                except TTSError as exc:
                    ultimo = exc
                    if emitio:
                        raise
                    logger.warning(
                        "TTS %s falló antes de dar audio (%s); pruebo el siguiente", proveedor.nombre, exc
                    )
                    self._fallos[indice] += 1
                    if self._fallos[indice] >= 2:
                        self._orden.remove(indice)
                        self._orden.append(indice)
                finally:
                    await stream.aclose()  # type: ignore[attr-defined]
            raise TTSError(f"ningún proveedor de voz respondió: {ultimo}") from ultimo
        finally:
            await texto.cerrar()

    async def cerrar(self) -> None:
        for proveedor in self._proveedores:
            await proveedor.cerrar()


def crear_tts(http: aiohttp.ClientSession | None = None) -> TTS | None:
    """Arma el TTS desde el entorno. None si no hay ninguna clave (solo texto).

    TTS_PROVIDER elige el principal: «cartesia» (por defecto) o «deepgram». El
    otro, si tiene clave, queda de respaldo.
    """
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    preferido = os.getenv("TTS_PROVIDER", "cartesia").strip().lower()

    cartesia = (
        TTSCartesia(cartesia_key, voz=os.getenv("CARTESIA_VOICE_ID") or CARTESIA_VOZ, http=http)
        if cartesia_key
        else None
    )
    deepgram = (
        TTSDeepgram(deepgram_key, modelo=os.getenv("DEEPGRAM_TTS_MODEL") or "aura-2-agustina-es", http=http)
        if deepgram_key
        else None
    )
    orden = [deepgram, cartesia] if preferido == "deepgram" else [cartesia, deepgram]
    proveedores: list[TTS] = [p for p in orden if p is not None]
    if not proveedores:
        return None
    if len(proveedores) == 1:
        return proveedores[0]
    return TTSConRespaldo(proveedores)
