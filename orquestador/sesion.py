"""La sesión de una llamada: lo que en LiveKit hace AgentSession.

Recibe audio de quien llama, decide cuándo terminó de hablar, arma el contexto
del turno con nucleo.preparar_turno (el mismo triage que el agente de LiveKit),
le pide la respuesta al LLM y la dice por TTS. También maneja las
interrupciones, las frases fijas del sistema, el metrónomo de RCP y el chat de
texto de la pestaña Test.

Cómo se decide un turno por voz:

1. Deepgram manda texto parcial y final. Cuando detecta silencio
   (`speech_final`) se programa el cierre del turno: enseguida si la frase
   parece completa («Sí.»), un poco después si no («Sí, pero»).
2. Mientras se espera, la respuesta ya se empieza a generar sobre una COPIA
   del estado (generación anticipada). Si la persona sigue hablando, el
   borrador se descarta y nada cambió.
3. Al cerrar el turno se actualiza el estado real. Si el borrador se generó
   con el mismo contexto se usa tal cual; si no, se genera de nuevo.
4. Si la persona habla mientras el agente habla (dos palabras o más), el agente
   se calla y en el historial queda solo lo que llegó a decir.

La sesión no sabe de WebSockets: habla con el cliente por un `Canal`.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from habla import EstadoAviso, NormalizadorStream, aplicar_aviso_911, aviso_ya_dicho
from nucleo import (
    FRASE_FALLA_LLM,
    FRASE_INICIO_METRONOMO,
    Turno,
    preparar_turno,
    retriever_actual,
    turno_anticipado,
)
from prompts import SALUDO, SYSTEM_INSTRUCTIONS
from rag import load_settings
from triage import TriageState, rcp_en_curso

from . import herramientas
from .llm import LLM, LlamadaTool, LLMError, Texto, Tools, Uso
from .rcp import AlientoRCP, MetronomoRemoto
from .stt import STT, EventoSTT
from .texto import contar_palabras, parece_completa, por_oraciones
from .tts import SAMPLE_RATE, TTS, Palabras, TTSError

logger = logging.getLogger("orquestador.sesion")

FRASE_AUSENCIA = "Seguí, te escucho. ¿Cómo va?"
SIN_RESPUESTA = "No se pudo generar respuesta."

# Sin tiempos por palabra del TTS, lo dicho se estima por duración.
_PALABRAS_POR_SEGUNDO = 2.7


def _env_float(nombre: str, defecto: float) -> float:
    valor = os.getenv(nombre)
    return float(valor) if valor and valor.strip() else defecto


def _env_bool(nombre: str, defecto: bool) -> bool:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        return defecto
    return valor.strip().lower() not in {"0", "off", "false", "no"}


@dataclass
class Config:
    # Silencio que cierra el turno: 0,5 s si la frase parece completa («Sí.») y
    # 1,2 s si no («Sí, pero»). Son los valores que se midieron con LiveKit
    # (endpointing min_delay / max_delay).
    silencio_min_s: float = 0.5
    silencio_max_s: float = 1.2
    # Silencio que espera Deepgram antes de avisar que la persona dejó de
    # hablar. Con ese aviso arranca el borrador de la respuesta, así que
    # conviene que llegue cuanto antes; cuándo se cierra el turno lo deciden
    # los dos valores de arriba. 25 ms es lo que usaba el plugin de LiveKit.
    stt_endpointing_ms: int = 25
    # Palabras que tiene que decir la persona para callar al agente. Con una
    # sola, un «sí» de fondo o un ruido cortaban cada indicación.
    interrupcion_min_palabras: int = 2
    # Empezar a generar la respuesta antes de dar el turno por cerrado.
    generacion_anticipada: bool = True
    max_pasos_tools: int = 4
    # Segundos de silencio de la persona antes de preguntarle cómo va.
    ausencia_s: float = 20.0
    # Cuánto audio se le adelanta al cliente por sobre el tiempo real.
    adelanto_audio_s: float = 0.5
    # Una respuesta corta («Sí.») mientras el agente habla se ignora, salvo
    # que al agente le quede menos que esto: ahí es la respuesta a su pregunta.
    cola_respuesta_s: float = 1.0

    @classmethod
    def desde_entorno(cls) -> Config:
        base = cls()
        return cls(
            silencio_min_s=_env_float("TURNO_SILENCIO_MIN_S", base.silencio_min_s),
            silencio_max_s=_env_float("TURNO_SILENCIO_MAX_S", base.silencio_max_s),
            stt_endpointing_ms=int(_env_float("STT_ENDPOINTING_MS", base.stt_endpointing_ms)),
            interrupcion_min_palabras=int(_env_float("INTERRUPCION_MIN_PALABRAS", base.interrupcion_min_palabras)),
            generacion_anticipada=_env_bool("GENERACION_ANTICIPADA", base.generacion_anticipada),
            ausencia_s=_env_float("AUSENCIA_S", base.ausencia_s),
        )


class Canal(Protocol):
    """Cómo le llega al cliente lo que produce la sesión."""

    async def audio(self, pcm: bytes) -> None: ...

    async def evento(self, datos: dict[str, Any]) -> None: ...


class Habla:
    """Algo que el agente va a decir: una frase fija o la respuesta del LLM.

    El texto entra por `cola` de a tramos (None marca el final). Al terminar,
    `terminada` se resuelve con lo que efectivamente se dijo."""

    def __init__(self, *, origen: str, guardar: bool = True) -> None:
        self.origen = origen
        # Si lo dicho queda en el historial que ve el LLM.
        self.guardar = guardar
        self.cola: asyncio.Queue[str | None] = asyncio.Queue()
        self.texto = ""
        self.texto_completo = False
        self.dicho = ""
        self.interrumpida = False
        # Llamadas a tools de esta respuesta: van al historial antes que el texto.
        self.previos: list[dict[str, Any]] = []
        self.terminada: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self.tarea: asyncio.Task[None] | None = None
        # Reproducción
        self.inicio: float | None = None  # cuándo salió el primer audio
        self.enviado_s = 0.0
        self.palabras: list[tuple[str, float]] = []
        self.sintesis_completa = False
        self.primer_texto: float | None = None

    @classmethod
    def fija(cls, texto: str, *, origen: str, guardar: bool = True) -> Habla:
        habla = cls(origen=origen, guardar=guardar)
        habla.agregar(texto)
        habla.cola.put_nowait(None)
        return habla

    def agregar(self, tramo: str) -> None:
        if self.primer_texto is None:
            self.primer_texto = time.monotonic()
        self.cola.put_nowait(tramo)

    async def tramos(self) -> AsyncIterator[str]:
        """El texto, a medida que llega. Se puede volver a llamar: sigue desde
        donde quedó (si el TTS falla, el resto del texto igual se junta)."""
        while not self.texto_completo:
            tramo = await self.cola.get()
            if tramo is None:
                self.texto_completo = True
                return
            self.texto += tramo
            yield tramo

    def reproducido(self) -> float:
        """Segundos de audio que ya sonaron del lado del cliente (estimado)."""
        if self.inicio is None:
            return 0.0
        return max(0.0, min(self.enviado_s, time.monotonic() - self.inicio))

    def restante(self) -> float:
        """Segundos que le faltan para terminar de sonar; infinito si todavía se está generando."""
        if not self.sintesis_completa or self.inicio is None:
            return float("inf")
        return max(0.0, self.enviado_s - (time.monotonic() - self.inicio))


@dataclass(eq=False)
class _Respuesta:
    """La respuesta del LLM a un turno: primero puede ser un borrador."""

    texto: str  # lo que dijo la persona
    previo: list[dict[str, Any]]  # el historial antes de este turno
    ultima: str  # lo último que dijo el agente
    habla: Habla
    # None mientras el borrador calcula su contexto sobre la copia del estado.
    turno: Turno | None = None
    derivado: bool = False
    contexto_listo: asyncio.Event = field(default_factory=asyncio.Event)
    confirmada: asyncio.Event = field(default_factory=asyncio.Event)
    tarea: asyncio.Task[None] | None = None
    fallo: bool = False
    emitio: bool = False
    # Métricas
    fin_habla: float | None = None
    cierre: float | None = None
    ttft: float | None = None

    def cancelar(self) -> None:
        if self.tarea is not None and not self.tarea.done():
            self.tarea.cancel()


class Sesion:
    def __init__(
        self,
        canal: Canal,
        *,
        llm: LLM,
        stt: STT | None = None,
        tts: TTS | None = None,
        config: Config | None = None,
    ) -> None:
        self.canal = canal
        self.cfg = config or Config.desde_entorno()
        self.estado = TriageState()
        # Mensajes en formato OpenAI, sin el de sistema.
        self.historial: list[dict[str, Any]] = []
        self.estado_agente = "iniciando"
        self.estado_usuario = "escuchando"
        # Con el chat de texto se apaga: la pestaña Test no reproduce audio.
        self.audio_habilitado = tts is not None

        self._llm = llm
        self._stt = stt
        self._tts = tts
        self._salida: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._cola_voz: asyncio.Queue[Habla] = asyncio.Queue()
        self._habla_actual: Habla | None = None
        self._respuesta: _Respuesta | None = None
        self._borrador: _Respuesta | None = None
        self._cierre: asyncio.Task[None] | None = None
        self._ausencia: asyncio.Task[None] | None = None
        self._tareas: list[asyncio.Task[None]] = []
        self._candado_turno = asyncio.Lock()
        self._candado_texto = asyncio.Lock()
        self._cerrada = False
        # Turno de voz en curso
        self._finales: list[str] = []
        self._interino = ""
        self._fin_habla: float | None = None

        self._metronomo = MetronomoRemoto(self._enviar_evento)
        self._aliento = AlientoRCP(self, self._metronomo)
        self._ya_sono = False

    # -- ciclo de vida ----------------------------------------------------------

    async def iniciar(self, *, saludar: bool = True) -> None:
        self._tareas.append(asyncio.create_task(self._bucle_salida(), name="sesion-salida"))
        self._tareas.append(asyncio.create_task(self._bucle_voz(), name="sesion-voz"))
        if self._stt is not None:
            await self._stt.iniciar()
            self._tareas.append(asyncio.create_task(self._bucle_stt(), name="sesion-stt"))
        self._enviar_evento({"type": "listo", "sample_rate": SAMPLE_RATE, "audio": self.audio_habilitado})
        # Mientras suena el saludo se abre la conexión con el LLM: el primer
        # turno no paga el saludo TLS.
        self._tareas.append(asyncio.create_task(self._llm.precalentar(), name="llm-precalentar"))
        if saludar:
            self.decir(SALUDO, origen="saludo")
        else:
            self._poner_estado_agente("escuchando")

    async def cerrar(self) -> None:
        if self._cerrada:
            return
        self._cerrada = True
        self._aliento.cerrar()
        self._metronomo.detener()
        self.estado.metronomo_activo = False
        pendientes: list[asyncio.Task[Any]] = list(self._tareas)
        for extra in (self._cierre, self._ausencia):
            if extra is not None:
                pendientes.append(extra)
        for r in (self._respuesta, self._borrador):
            if r is not None and r.tarea is not None:
                pendientes.append(r.tarea)
        if self._habla_actual is not None and self._habla_actual.tarea is not None:
            pendientes.append(self._habla_actual.tarea)
        for tarea in pendientes:
            tarea.cancel()
        await asyncio.gather(*pendientes, return_exceptions=True)
        if self._stt is not None:
            await self._stt.cerrar()
        if self._tts is not None:
            await self._tts.cerrar()

    # -- salida hacia el cliente ------------------------------------------------
    #
    # Todo sale por una sola cola y en orden: un «limpiar» nunca le gana al
    # audio que tiene que borrar, y la sesión no se frena esperando a la red.

    def enviar(self, datos: dict[str, Any]) -> None:
        """Manda un mensaje al cliente, en orden con el resto de lo que sale de la sesión."""
        self._salida.put_nowait(("evento", datos))

    _enviar_evento = enviar

    def _enviar_audio(self, pcm: bytes) -> None:
        self._salida.put_nowait(("audio", pcm))

    async def _bucle_salida(self) -> None:
        while True:
            tipo, datos = await self._salida.get()
            try:
                if tipo == "audio":
                    await self.canal.audio(datos)
                else:
                    await self.canal.evento(datos)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("no pude enviar al cliente (%s); dejo de enviar", exc)
                return

    def _avisar_estado(self) -> None:
        self._aliento.actividad()
        self._enviar_evento({"type": "estado", "agente": self.estado_agente, "usuario": self.estado_usuario})

    def _poner_estado_agente(self, nuevo: str) -> None:
        if self.estado_agente != nuevo:
            self.estado_agente = nuevo
            self._avisar_estado()

    def _poner_estado_usuario(self, nuevo: str) -> None:
        if self.estado_usuario != nuevo:
            self.estado_usuario = nuevo
            self._avisar_estado()

    # -- historial ----------------------------------------------------------------

    def respuestas_del_agente(self, historial: list[dict[str, Any]] | None = None) -> list[str]:
        mensajes = self.historial if historial is None else historial
        return [m["content"] for m in mensajes if m["role"] == "assistant" and isinstance(m.get("content"), str)]

    def ultima_respuesta(self) -> str:
        """Lo último que el agente le DIJO a la persona (no lo que generó y se descartó)."""
        dichas = self.respuestas_del_agente()
        return dichas[-1] if dichas else ""

    def saludo_de_texto(self) -> str:
        """Para el chat de texto: el saludo queda en el historial sin decirse."""
        self.audio_habilitado = False
        self.historial.append({"role": "assistant", "content": SALUDO})
        return SALUDO

    # -- lo que dice el agente ----------------------------------------------------

    def decir(self, texto: str, *, origen: str = "sistema", guardar: bool = True) -> Habla:
        """Dice una frase fija, sin pasar por el LLM. Se encola detrás de lo que esté sonando."""
        habla = Habla.fija(texto, origen=origen, guardar=guardar)
        self._cola_voz.put_nowait(habla)
        return habla

    def _agente_ocupado(self) -> bool:
        return self._habla_actual is not None or not self._cola_voz.empty()

    async def _bucle_voz(self) -> None:
        while True:
            habla = await self._cola_voz.get()
            self._habla_actual = habla
            habla.tarea = asyncio.create_task(self._reproducir(habla), name=f"habla-{habla.origen}")
            await asyncio.wait({habla.tarea})
            if not habla.tarea.cancelled() and habla.tarea.exception() is not None:
                logger.error("falló una respuesta hablada", exc_info=habla.tarea.exception())
            self._habla_actual = None
            if self._cola_voz.empty():
                self._poner_estado_agente("escuchando")
                self._reiniciar_ausencia()

    async def _reproducir(self, habla: Habla) -> None:
        try:
            if self.audio_habilitado and self._tts is not None:
                await self._hablar(habla)
            else:
                async for _ in habla.tramos():
                    pass
            habla.dicho = habla.texto
        except asyncio.CancelledError:
            if not habla.interrumpida:
                raise  # se cierra la sesión: no es una interrupción
        finally:
            self._terminar_habla(habla)

    async def _hablar(self, habla: Habla) -> None:
        assert self._tts is not None
        stream = self._tts.sintetizar(por_oraciones(habla.tramos()))
        try:
            async for evento in stream:
                if isinstance(evento, Palabras):
                    habla.palabras.extend(evento.palabras)
                    continue
                if habla.inicio is None:
                    habla.inicio = time.monotonic()
                    self._primer_audio(habla)
                self._enviar_audio(evento.pcm)
                habla.enviado_s += len(evento.pcm) / (2 * SAMPLE_RATE)
                # Se manda un poco adelantado y después al ritmo en que suena:
                # así se sabe cuánto se escuchó si la persona interrumpe.
                adelanto = habla.enviado_s - (time.monotonic() - habla.inicio)
                if adelanto > self.cfg.adelanto_audio_s:
                    await asyncio.sleep(adelanto - self.cfg.adelanto_audio_s)
            habla.sintesis_completa = True
            # El turno del agente termina cuando terminó de sonar, no de generarse.
            if (resto := habla.restante()) != float("inf") and resto > 0:
                await asyncio.sleep(resto)
        except TTSError as exc:
            # Sin voz: que al menos el texto llegue al cliente y quede en el historial.
            logger.error("no se pudo decir una frase (%s): %s", habla.origen, exc)
            self._enviar_evento({"type": "error", "codigo": "tts", "mensaje": "No se pudo generar la voz."})
            async for _ in habla.tramos():
                pass
        finally:
            await stream.aclose()  # type: ignore[attr-defined]

    def _primer_audio(self, habla: Habla) -> None:
        self._poner_estado_agente("hablando")
        r = self._respuesta
        if r is None or r.habla is not habla:
            return
        ahora = time.monotonic()
        metricas = {
            "e2e_latency_ms": ahora - r.fin_habla if r.fin_habla else None,
            "llm_ttft_ms": r.ttft,
            "tts_ttfb_ms": ahora - habla.primer_texto if habla.primer_texto else None,
            "playback_latency_ms": None,
            "end_of_turn_delay_ms": r.cierre - r.fin_habla if r.cierre and r.fin_habla else None,
        }
        # Los nombres terminan en _ms pero van en segundos, como en agent.py: el
        # panel de debug del frontend los multiplica por mil.
        self.estado.last_llm_metrics = metricas
        logger.info(
            "latencia | e2e=%s ttft=%s tts_ttfb=%s fin_de_turno=%s",
            _ms(metricas["e2e_latency_ms"]),
            _ms(metricas["llm_ttft_ms"]),
            _ms(metricas["tts_ttfb_ms"]),
            _ms(metricas["end_of_turn_delay_ms"]),
        )

    def _texto_dicho(self, habla: Habla) -> str:
        """Lo que se llegó a escuchar de una frase interrumpida."""
        sonado = habla.reproducido()
        if sonado <= 0:
            return ""
        palabras = habla.texto.split()
        if habla.palabras:
            n = sum(1 for _, fin in habla.palabras if fin <= sonado + 0.05)
        elif habla.sintesis_completa and habla.enviado_s > 0:
            n = int(len(palabras) * sonado / habla.enviado_s)
        else:
            n = int(sonado * _PALABRAS_POR_SEGUNDO)
        return " ".join(palabras[:n])

    def _terminar_habla(self, habla: Habla) -> None:
        if habla.terminada.done():
            return
        if habla.interrumpida:
            habla.dicho = self._texto_dicho(habla)
            if habla.inicio is not None:
                self._enviar_evento({"type": "limpiar"})
        dicho = habla.dicho.strip()
        if habla.guardar:
            self.historial.extend(habla.previos)
            if dicho:
                self.historial.append({"role": "assistant", "content": dicho})
        if dicho:
            self._enviar_evento({
                "type": "transcripcion",
                "rol": "asistente",
                "texto": dicho,
                "final": True,
                "interrumpida": habla.interrumpida,
            })
        habla.terminada.set_result(dicho)
        if dicho and not self._cerrada:
            self._sincronizar_metronomo("assistant")

    async def interrumpir(self, motivo: str = "") -> None:
        """Calla al agente: corta lo que suena, lo que estaba por decir y la
        respuesta que se estaba generando."""
        ocupado = self._agente_ocupado() or self._respuesta is not None
        while not self._cola_voz.empty():
            pendiente = self._cola_voz.get_nowait()
            pendiente.interrumpida = True
            self._terminar_habla(pendiente)
        respuesta, self._respuesta = self._respuesta, None
        if respuesta is not None:
            respuesta.cancelar()
        habla = self._habla_actual
        if habla is not None and habla.tarea is not None and not habla.tarea.done():
            habla.interrumpida = True
            habla.tarea.cancel()
            await asyncio.wait({habla.tarea})
        if ocupado and motivo:
            logger.info("interrupción: %s", motivo)

    # -- audio de quien llama -----------------------------------------------------

    def recibir_audio(self, pcm: bytes) -> None:
        if self._stt is not None and not self._cerrada:
            self._stt.enviar_audio(pcm)

    async def _bucle_stt(self) -> None:
        assert self._stt is not None
        async for evento in self._stt.eventos():
            try:
                await self._en_stt(evento)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("falló el manejo de un evento de voz")

    def _texto_en_curso(self) -> str:
        return " ".join([*self._finales, self._interino]).strip()

    async def _en_stt(self, ev: EventoSTT) -> None:
        if ev.tipo == "error":
            self._enviar_evento({"type": "error", "codigo": "stt", "mensaje": "Se cortó el reconocimiento de voz."})
            return
        if ev.tipo == "habla":
            # Voz sin texto todavía. No alcanza para interrumpir al agente (se
            # esperan palabras), pero sí para no cerrar el turno: la persona
            # volvió a hablar. Si era un ruido, lo cierra «fin_enunciado».
            if self._cierre is not None:
                self._cancelar_cierre()
            return
        if ev.tipo == "fin_enunciado":
            if self._finales and self._cierre is None:
                self._programar_cierre()
            return

        if ev.texto:
            if ev.final:
                self._finales.append(ev.texto)
                self._interino = ""
            else:
                self._interino = ev.texto
            if ev.fin_audio is not None:
                self._fin_habla = ev.fin_audio
            self._poner_estado_usuario("hablando")
            self._cancelar_ausencia()
            # Siguió hablando: el cierre programado y su borrador ya no valen.
            self._cancelar_cierre()
            self._enviar_evento({
                "type": "transcripcion", "rol": "usuario", "texto": self._texto_en_curso(), "final": False,
            })
            if (self._agente_ocupado() or self._respuesta_en_curso()) and (
                contar_palabras(self._texto_en_curso()) >= self.cfg.interrupcion_min_palabras
            ):
                await self.interrumpir("la persona empezó a hablar")
        # Un fin de habla sin texto nuevo no reinicia una espera que ya corre.
        if ev.fin_de_habla and self._finales and (ev.texto or self._cierre is None):
            self._programar_cierre()

    def _respuesta_en_curso(self) -> bool:
        r = self._respuesta
        return r is not None and r.tarea is not None and not r.tarea.done()

    def _cancelar_cierre(self) -> None:
        if self._cierre is not None:
            self._cierre.cancel()
            self._cierre = None
        borrador, self._borrador = self._borrador, None
        if borrador is not None:
            borrador.cancelar()

    def _programar_cierre(self) -> None:
        self._cancelar_cierre()
        texto = " ".join(self._finales).strip()
        silencio = self.cfg.silencio_min_s if parece_completa(texto) else self.cfg.silencio_max_s
        # El silencio se cuenta desde que terminó la última palabra, no desde
        # ahora: el aviso de Deepgram llega unos 0,5 s después, y sumarle la
        # espera entera dejaba cada turno 1 s en silencio (medido por voz).
        desde = self._fin_habla if self._fin_habla is not None else time.monotonic()
        espera = max(0.0, desde + silencio - time.monotonic())
        if self.cfg.generacion_anticipada and not self._agente_ocupado():
            self._borrador = self._lanzar(
                texto, previo=list(self.historial), ultima=self.ultima_respuesta(), turno=None
            )
        self._cierre = asyncio.create_task(self._cerrar_en(espera, texto), name="cierre-de-turno")

    async def _cerrar_en(self, espera: float, texto: str) -> None:
        await asyncio.sleep(espera)
        # Desde acá el cierre ya no se cancela: actualizar el estado a medias
        # sería peor que responderle a una frase que la persona después amplió.
        self._cierre = None
        borrador, self._borrador = self._borrador, None
        try:
            await self._cerrar_turno(texto, borrador)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("falló el cierre del turno")

    async def _cerrar_turno(self, texto: str, borrador: _Respuesta | None) -> None:
        fin_habla, self._fin_habla = self._fin_habla, None
        self._finales.clear()
        self._interino = ""
        self._enviar_evento({"type": "transcripcion", "rol": "usuario", "texto": texto, "final": True})
        self._poner_estado_usuario("escuchando")

        if self._agente_ocupado():
            # El agente sigue hablando (o está por hablar): la persona dijo algo
            # corto que no llegó a interrumpirlo.
            habla = self._habla_actual
            if habla is not None and self._cola_voz.empty() and habla.restante() <= self.cfg.cola_respuesta_s:
                await asyncio.wait({habla.terminada})
            else:
                logger.info("se ignora «%s»: el agente estaba hablando", texto)
                if borrador is not None:
                    borrador.cancelar()
                return
        await self._responder(texto, borrador=borrador, fin_habla=fin_habla)

    # -- respuesta a un turno -----------------------------------------------------

    def _lanzar(
        self, texto: str, *, previo: list[dict[str, Any]], ultima: str, turno: Turno | None
    ) -> _Respuesta:
        r = _Respuesta(texto=texto, previo=previo, ultima=ultima, habla=Habla(origen="respuesta"), turno=turno)
        r.tarea = asyncio.create_task(self._generar(r), name="respuesta")
        return r

    async def _responder(
        self, texto: str, *, borrador: _Respuesta | None = None, fin_habla: float | None = None
    ) -> Habla:
        """Confirma el turno: actualiza el estado y deja la respuesta en camino."""
        async with self._candado_turno:
            previo = list(self.historial)
            ultima = self.ultima_respuesta()
            turno = await preparar_turno(texto, self.estado, ultima)
            self.historial.append({"role": "user", "content": turno.con_protocolos(texto)})
            # Antes del LLM: si volvió a respirar, el metrónomo se apaga ya.
            self._sincronizar_metronomo("user")

            respuesta: _Respuesta | None = None
            if borrador is not None:
                if await self._sirve(borrador, turno, previo):
                    respuesta = borrador
                    respuesta.turno = turno
                else:
                    logger.info("el borrador no sirve para el turno confirmado: se genera de nuevo")
                    borrador.cancelar()
            if respuesta is None:
                respuesta = self._lanzar(texto, previo=previo, ultima=ultima, turno=turno)
            respuesta.fin_habla = fin_habla
            respuesta.cierre = time.monotonic()
            respuesta.confirmada.set()
            self._respuesta = respuesta
            if self._habla_actual is None:
                self._poner_estado_agente("pensando")
            self._cola_voz.put_nowait(respuesta.habla)
            return respuesta.habla

    async def _sirve(self, borrador: _Respuesta, turno: Turno, previo: list[dict[str, Any]]) -> bool:
        """El borrador se generó con el mismo contexto que el turno confirmado.

        preparar_turno es determinística (mismo texto, mismo estado, mismo
        contexto), pero no se confía en eso: se compara."""
        await borrador.contexto_listo.wait()
        if borrador.fallo or borrador.turno is None or (borrador.tarea is not None and borrador.tarea.cancelled()):
            return False
        return (
            borrador.previo == previo
            and borrador.turno.completo() == turno.completo()
            and borrador.turno.respuesta_fija == turno.respuesta_fija
        )

    def _mensajes(self, previo: list[dict[str, Any]], texto: str, turno: Turno) -> list[dict[str, Any]]:
        """Lo que ve el LLM: los protocolos quedan en el historial; el estado y
        los avisos van solo en esta llamada (ver nucleo.Turno)."""
        contenido = turno.con_protocolos(texto)
        if directivas := turno.texto_directivas():
            contenido = f"{contenido}\n\n{directivas}"
        return [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            *previo,
            {"role": "user", "content": contenido},
        ]

    async def _generar(self, r: _Respuesta) -> None:
        habla = r.habla
        try:
            try:
                if r.turno is None:
                    # Borrador: el turno todavía puede cambiar, así que el
                    # contexto se calcula sobre una copia del estado.
                    copia = copy.deepcopy(self.estado)
                    with turno_anticipado():
                        r.turno = await preparar_turno(r.texto, copia, r.ultima)
                    r.derivado = copia.derivado
                else:
                    r.derivado = self.estado.derivado
            finally:
                r.contexto_listo.set()
            turno = r.turno

            aviso = EstadoAviso(
                derivado=r.derivado,
                aviso_911_dicho=aviso_ya_dicho(self.respuestas_del_agente(r.previo)),
            )

            def emitir(texto: str) -> None:
                """Un tramo de la respuesta, ya corregido, rumbo al TTS."""
                listo = aplicar_aviso_911(texto, aviso) if texto else texto
                if listo:
                    r.emitio = True
                    habla.agregar(listo)

            def frase_de_espera(frase: str) -> None:
                r.emitio = True
                habla.agregar(frase + " ")

            if turno.respuesta_fija:
                # Momento crítico: la frase es fija y sale al instante, sin LLM.
                emitir(turno.respuesta_fija)
                return

            mensajes = self._mensajes(r.previo, r.texto, turno)
            norm = NormalizadorStream()
            for paso in range(self.cfg.max_pasos_tools + 1):
                llamadas: list[LlamadaTool] = []
                async for evento in self._llm.generar(mensajes, herramientas.ESQUEMAS):
                    if isinstance(evento, Texto):
                        emitir(norm.push(evento.delta))
                    elif isinstance(evento, Tools):
                        llamadas = evento.llamadas
                    elif isinstance(evento, Uso):
                        self._anotar_uso(r, evento)
                emitir(norm.flush())
                if not llamadas:
                    break
                if paso == self.cfg.max_pasos_tools:
                    logger.warning("el modelo siguió pidiendo tools después de %d pasos", paso)
                    break
                # Las tools cambian el estado: no se corren para un borrador.
                await r.confirmada.wait()
                resultados = [await self._ejecutar_tool(llamada, frase_de_espera) for llamada in llamadas]
                pedido = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": llamada.id,
                            "type": "function",
                            "function": {"name": llamada.nombre, "arguments": llamada.argumentos or "{}"},
                        }
                        for llamada in llamadas
                    ],
                }
                intercambio = [pedido] + [
                    {"role": "tool", "tool_call_id": llamada.id, "content": resultado}
                    for llamada, resultado in zip(llamadas, resultados, strict=True)
                ]
                mensajes.extend(intercambio)
                habla.previos.extend(intercambio)
        except LLMError as exc:
            r.fallo = True
            logger.error("el LLM no respondió este turno: %s", exc)
            # En una emergencia el silencio es lo peor: si no se llegó a decir
            # nada, sale una frase que no pasa por el LLM.
            if r.confirmada.is_set() and not r.emitio:
                habla.agregar(FRASE_FALLA_LLM)
        except asyncio.CancelledError:
            raise
        except Exception:
            r.fallo = True
            logger.exception("falló la generación de la respuesta")
            if r.confirmada.is_set() and not r.emitio:
                habla.agregar(FRASE_FALLA_LLM)
        finally:
            habla.cola.put_nowait(None)

    async def _ejecutar_tool(self, llamada: LlamadaTool, al_demorar: Any) -> str:
        try:
            argumentos = llamada.args()
        except ValueError:
            return "Los argumentos de la herramienta no son JSON válido. Respondé sin usarla."
        logger.info("tool %s(%s)", llamada.nombre, llamada.argumentos)
        return await herramientas.ejecutar(llamada.nombre, argumentos, self.estado, al_demorar=al_demorar)

    def _anotar_uso(self, r: _Respuesta, uso: Uso) -> None:
        if r.ttft is None:
            r.ttft = uso.ttft
        self.estado.last_llm_tokens = {
            "prompt_tokens": uso.prompt_tokens,
            "completion_tokens": uso.completion_tokens,
            "total_tokens": uso.total_tokens,
            "cached_tokens": uso.cached_tokens,
            "tokens_per_second": uso.tokens_per_second,
        }

    # -- chat de texto --------------------------------------------------------------

    async def turno_de_texto(self, texto: str, *, debug: bool = False) -> dict[str, Any]:
        """Un turno escrito (pestaña Test, consola, pruebas). Devuelve el mismo
        mensaje que publicaba el agente de LiveKit por el canal «test-chat»."""
        async with self._candado_texto:
            if self.audio_habilitado:
                self.audio_habilitado = False
                logger.info("chat de texto: salida de audio desactivada para esta sesión")
            st = self.estado
            st.tool_calls.clear()
            st.last_llm_metrics = None
            st.last_llm_tokens = None
            inicio = time.monotonic()
            self._enviar_evento({
                "type": "chat_status",
                "status": "thinking",
                "message": "Asistente analizando la situación...",
            })
            await self.interrumpir()
            habla = await self._responder(texto)
            respuesta = self._respuesta
            dicho = await asyncio.shield(habla.terminada)
            total_ms = int((time.monotonic() - inicio) * 1000)
            mensaje = dicho or SIN_RESPUESTA
            logger.info("respondiendo chat: %s", mensaje)
            if not debug:
                return {"type": "chat_reply", "message": mensaje}

            metricas: dict[str, Any] = dict(st.last_llm_metrics or {})
            metricas.setdefault("llm_ttft_ms", respuesta.ttft if respuesta else None)
            if st.last_llm_tokens:
                metricas.update(st.last_llm_tokens)
            llamadas = list(st.tool_calls)
            return {
                "type": "chat_reply_debug",
                "message": mensaje,
                "total_response_ms": total_ms,
                "search_count": sum(
                    1 for tc in llamadas if tc.get("tool") in ("buscar_protocolo", "prefetch_protocolo")
                ),
                "tool_calls": llamadas,
                "llm_metrics": metricas,
                "config": self._config_para_debug(),
            }

    def _config_para_debug(self) -> dict[str, Any]:
        config: dict[str, Any] = {"llm_model": self._llm.modelo, "indice_cargado": retriever_actual() is not None}
        try:
            cargado = retriever_actual()
            ajustes = cargado.settings if cargado is not None else load_settings()
        except Exception:
            return config  # sin base configurada: se muestra lo que hay
        config.update({
            "embed_model": ajustes.embed_model,
            "rerank_enabled": ajustes.rerank_enabled,
            "rerank_model": ajustes.rerank_model if ajustes.rerank_enabled else None,
            "top_k": ajustes.top_k,
            "k_vector": ajustes.k_vector,
            "min_score": ajustes.min_score,
            "rerank_min_score": ajustes.min_rerank_score if ajustes.rerank_enabled else None,
        })
        return config

    # -- silencio de la persona -----------------------------------------------------

    def _cancelar_ausencia(self) -> None:
        if self._ausencia is not None:
            self._ausencia.cancel()
            self._ausencia = None

    def _reiniciar_ausencia(self) -> None:
        self._cancelar_ausencia()
        # Se avisa una sola vez: hasta que la persona vuelva a hablar no se repite.
        if self._stt is None or not self.audio_habilitado or self.estado_usuario != "escuchando" or self._cerrada:
            return
        self._ausencia = asyncio.create_task(self._esperar_ausencia(), name="ausencia")

    async def _esperar_ausencia(self) -> None:
        await asyncio.sleep(self.cfg.ausencia_s)
        self._ausencia = None
        if self.estado_agente != "escuchando" or self.estado_usuario != "escuchando":
            return
        self._poner_estado_usuario("ausente")
        # Con el 911 ya avisado no se le pregunta nada: puede estar comprimiendo.
        if not self.estado.derivado:
            self.decir(FRASE_AUSENCIA)

    # -- metrónomo de RCP -----------------------------------------------------------

    def _sincronizar_metronomo(self, rol: str) -> None:
        """Prende el metrónomo cuando ya se DIJO la indicación de comprimir y lo
        apaga apenas el turno de la persona cambia el estado (volvió a
        respirar, llegó la ayuda o pidió sacar el sonido)."""
        st = self.estado
        sonar = rcp_en_curso(st) and not st.metronomo_silenciado and self.audio_habilitado
        if rol == "assistant" and sonar and self._metronomo.iniciar():
            st.metronomo_activo = True
            if not self._ya_sono:
                self.decir(FRASE_INICIO_METRONOMO)
            self._ya_sono = True
            self._aliento.iniciar()
        elif not sonar and self._metronomo.detener():
            st.metronomo_activo = False


def _ms(valor: float | None) -> str:
    return "—" if valor is None else f"{valor * 1000:.0f}ms"
