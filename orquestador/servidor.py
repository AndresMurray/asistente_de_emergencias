"""Servidor del orquestador: una llamada por conexión WebSocket.

Reemplaza a la sala de LiveKit y al worker (`agent.py dev` / `lk agent deploy`).

    python -m orquestador

Protocolo (ws://HOST:PUERTO/ws):

Cliente -> servidor
    {"type": "inicio", "modo": "voz" | "texto", "sample_rate": 16000, "pase": "..."}
        Primer mensaje, obligatorio. `pase` solo si el servidor tiene
        ORQUESTADOR_SECRETO (ver acceso.py).
    <binario>   audio del micrófono: PCM de 16 bits, mono, al sample_rate declarado.
    {"type": "chat_request", "message": "...", "debug": true}   un turno escrito.
    {"type": "fin"}   termina la llamada.

Servidor -> cliente
    {"type": "listo", "sample_rate": 24000, "audio": true}
    <binario>   la voz del agente: PCM de 16 bits, mono, a 24000 Hz.
    {"type": "estado", "agente": "hablando|pensando|escuchando", "usuario": "hablando|escuchando|ausente"}
    {"type": "transcripcion", "rol": "usuario|asistente", "texto": "...", "final": true}
    {"type": "limpiar"}   la persona interrumpió: descartar el audio que quedó sin sonar.
    {"type": "metronomo", "activo": true, "bpm": 110, "volumen": 0.35}
    {"type": "chat_status" | "chat_reply" | "chat_reply_debug", ...}   igual que el canal «test-chat» de LiveKit.
    {"type": "error", "codigo": "...", "mensaje": "..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

import nucleo
from prompts import KEYTERMS_ES
from rag.session import close_fallback

from . import acceso
from .llm import LLM, crear_llm
from .sesion import Config, Sesion
from .stt import STTDeepgram
from .tts import crear_tts

logger = logging.getLogger("orquestador.servidor")

ORIGENES_LOCALES = "http://localhost:3000,http://127.0.0.1:3000"
_ESPERA_INICIO_S = 10.0

LLM_KEY = web.AppKey("llm", LLM)
HTTP_KEY = web.AppKey("http", aiohttp.ClientSession)
ACTIVAS_KEY = web.AppKey("activas", set)


class CanalWS:
    def __init__(self, ws: web.WebSocketResponse) -> None:
        self._ws = ws

    async def audio(self, pcm: bytes) -> None:
        await self._ws.send_bytes(pcm)

    async def evento(self, datos: dict[str, Any]) -> None:
        await self._ws.send_str(json.dumps(datos, ensure_ascii=False))


def _origen_permitido(origen: str | None) -> bool:
    """Solo se controla a los navegadores (que mandan Origin): es lo que evita
    que otra página web abra llamadas usando la sesión de alguien."""
    if origen is None:
        return True
    permitidos = [o.strip().rstrip("/") for o in os.getenv("ORQUESTADOR_ORIGENES", ORIGENES_LOCALES).split(",")]
    return "*" in permitidos or origen.rstrip("/") in permitidos


async def _leer_inicio(ws: web.WebSocketResponse) -> dict[str, Any] | None:
    try:
        msg = await ws.receive(timeout=_ESPERA_INICIO_S)
    except asyncio.TimeoutError:
        return None
    if msg.type != aiohttp.WSMsgType.TEXT:
        return None
    try:
        datos = json.loads(msg.data)
    except ValueError:
        return None
    return datos if isinstance(datos, dict) and datos.get("type") == "inicio" else None


async def manejar_llamada(request: web.Request) -> web.StreamResponse:
    app = request.app
    if not _origen_permitido(request.headers.get("Origin")):
        return web.Response(status=403, text="origen no permitido")
    maximo = int(os.getenv("ORQUESTADOR_MAX_SESIONES", "4"))
    if len(app[ACTIVAS_KEY]) >= maximo:
        return web.Response(status=503, text="hay demasiadas llamadas en curso")

    ws = web.WebSocketResponse(heartbeat=20.0, max_msg_size=256 * 1024)
    await ws.prepare(request)
    canal = CanalWS(ws)
    sesion: Sesion | None = None
    chats: set[asyncio.Task[None]] = set()
    try:
        inicio = await _leer_inicio(ws)
        if inicio is None:
            await canal.evento({"type": "error", "codigo": "inicio", "mensaje": "Falta el mensaje de inicio."})
            return ws
        secreto = os.getenv("ORQUESTADOR_SECRETO")
        if secreto and not acceso.verificar(secreto, inicio.get("pase")):
            await canal.evento({"type": "error", "codigo": "pase", "mensaje": "Pase inválido o vencido."})
            return ws

        modo = "texto" if inicio.get("modo") == "texto" else "voz"
        config = Config.desde_entorno()
        stt = tts = None
        if modo == "voz":
            deepgram_key = os.getenv("DEEPGRAM_API_KEY")
            if not deepgram_key:
                await canal.evento({
                    "type": "error", "codigo": "stt", "mensaje": "Falta DEEPGRAM_API_KEY: no hay reconocimiento de voz.",
                })
                return ws
            try:
                sample_rate = int(inicio.get("sample_rate") or 16000)
            except (TypeError, ValueError):
                sample_rate = 16000
            stt = STTDeepgram(
                deepgram_key,
                sample_rate=sample_rate,
                keyterms=KEYTERMS_ES,
                endpointing_ms=config.stt_endpointing_ms,
                http=app[HTTP_KEY],
            )
            tts = crear_tts(app[HTTP_KEY])

        sesion = Sesion(canal, llm=app[LLM_KEY], stt=stt, tts=tts, config=config)
        app[ACTIVAS_KEY].add(sesion)
        logger.info("llamada nueva | modo=%s | en curso=%d", modo, len(app[ACTIVAS_KEY]))
        if modo == "voz":
            await sesion.iniciar()
        else:
            await sesion.iniciar(saludar=False)
            sesion.enviar({"type": "chat_reply", "message": sesion.saludo_de_texto()})

        # Tope de duración: una pestaña olvidada no puede gastar créditos toda la noche.
        async with asyncio.timeout(float(os.getenv("ORQUESTADOR_MAX_MIN", "30")) * 60):
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    sesion.recibir_audio(msg.data)
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    if not _en_mensaje(sesion, msg.data, chats):
                        break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break
    except TimeoutError:
        logger.info("llamada cortada por el tope de duración")
    except (ConnectionResetError, aiohttp.ClientError) as exc:
        logger.info("el cliente cortó la conexión: %s", exc)
    finally:
        for chat in chats:
            chat.cancel()
        if sesion is not None:
            app[ACTIVAS_KEY].discard(sesion)
            await sesion.cerrar()
            logger.info("llamada terminada | en curso=%d", len(app[ACTIVAS_KEY]))
        if not ws.closed:
            await ws.close()
    return ws


def _en_mensaje(sesion: Sesion, crudo: str, chats: set[asyncio.Task[None]]) -> bool:
    """Procesa un mensaje de texto del cliente. Devuelve False si pidió terminar."""
    try:
        datos = json.loads(crudo)
    except ValueError:
        datos = crudo
    if isinstance(datos, dict):
        if datos.get("type") == "fin":
            return False
        consulta = datos.get("message") or datos.get("text") or datos.get("content")
        debug = bool(datos.get("debug", False))
    else:
        consulta, debug = str(datos), False
    if not isinstance(consulta, str) or not consulta.strip():
        return True
    logger.info("chat recibido: %s (debug=%s)", consulta, debug)

    async def responder() -> None:
        try:
            sesion.enviar(await sesion.turno_de_texto(consulta.strip(), debug=debug))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("falló un turno de chat")
            sesion.enviar({"type": "chat_reply", "message": "No se pudo generar respuesta."})

    # En una tarea aparte: la conexión sigue leyendo mientras el LLM responde.
    chat = asyncio.create_task(responder(), name="chat")
    chats.add(chat)
    chat.add_done_callback(chats.discard)
    return True


async def salud(request: web.Request) -> web.Response:
    return web.json_response({
        "ok": True,
        "llamadas_en_curso": len(request.app[ACTIVAS_KEY]),
        "indice_cargado": nucleo.retriever_actual() is not None,
        "llm": request.app[LLM_KEY].cadena,
    })


async def _al_cerrar(app: web.Application) -> None:
    for sesion in list(app[ACTIVAS_KEY]):
        await sesion.cerrar()
    await app[LLM_KEY].cerrar()
    await app[HTTP_KEY].close()
    await close_fallback()


def crear_app(llm: LLM | None = None, *, cargar_indice: bool = True) -> web.Application:
    """`llm` y `cargar_indice` existen para los tests: por defecto el LLM sale
    del entorno y el índice del manual se carga al arrancar."""

    async def _al_arrancar(app: web.Application) -> None:
        app[HTTP_KEY] = aiohttp.ClientSession()
        app[LLM_KEY] = llm if llm is not None else crear_llm()
        app[ACTIVAS_KEY] = set()
        # Crear el cliente HTTP del LLM (cargar los certificados son ~0,3 s) al
        # arrancar y no en medio de la primera llamada.
        await app[LLM_KEY].precalentar()
        if cargar_indice:
            # En segundo plano: si la base tarda, el servidor igual atiende con
            # los textos de respaldo (ver nucleo.py).
            asyncio.get_running_loop().run_in_executor(None, nucleo.prewarm)

    app = web.Application()
    app.on_startup.append(_al_arrancar)
    app.on_cleanup.append(_al_cerrar)
    app.router.add_get("/ws", manejar_llamada)
    app.router.add_get("/salud", salud)
    app.router.add_get("/", salud)
    return app


def main() -> None:
    load_dotenv(".env.local")
    # En Windows, sin esto los acentos del log salen rotos cuando la salida va
    # a un archivo o a otro programa.
    for salida in (sys.stdout, sys.stderr):
        if hasattr(salida, "reconfigure"):
            salida.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # LOG_DEBUG=orquestador.stt,orquestador.sesion: detalle de esas partes sin
    # prender el DEBUG de todo (el del cliente HTTP vuelca cada pedido entero).
    for nombre in os.getenv("LOG_DEBUG", "").split(","):
        if nombre.strip():
            logging.getLogger(nombre.strip()).setLevel(logging.DEBUG)
    host = os.getenv("ORQUESTADOR_HOST", "127.0.0.1")
    puerto = int(os.getenv("ORQUESTADOR_PUERTO", "8787"))
    if not os.getenv("ORQUESTADOR_SECRETO") and host not in {"127.0.0.1", "localhost", "::1"}:
        logger.warning(
            "ORQUESTADOR_SECRETO no está definido y el servidor escucha en %s: cualquiera que "
            "llegue al puerto puede abrir llamadas y gastar créditos.",
            host,
        )
    logger.info("orquestador en ws://%s:%d/ws (estado en http://%s:%d/salud)", host, puerto, host, puerto)
    web.run_app(crear_app(), host=host, port=puerto, print=lambda *_: None, access_log=None)


if __name__ == "__main__":
    main()
