import asyncio
import copy
import json
import logging
import os
import time
from collections.abc import Callable

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

from livekit import agents, rtc  # type: ignore
from livekit.agents import (  # type: ignore
    Agent,
    AgentServer,
    AgentSession,
    ModelSettings,
    RunContext,
    ToolError,
    function_tool,
    inference,
    metrics,
    room_io,
)
from livekit.agents import llm as lk_llm
from livekit.agents.llm import ToolFlag
from livekit.plugins import cartesia, deepgram, google, openai

import nucleo
from habla import EstadoAviso, NormalizadorStream, aplicar_aviso_911, aviso_ya_dicho
from metronomo import Metronomo

# El triage, los protocolos y el contexto de cada turno viven en nucleo.py, que
# no depende de LiveKit (lo comparte el orquestador propio). Acá queda lo que es
# de LiveKit: proveedores, tools, Assistant y el entrypoint. Se reexportan los
# nombres que usan los tests y los scripts (ensayo.py, test_guion_expo.py).
from nucleo import (  # noqa: F401
    _ANTICIPADA,
    DESCRIPCION_BUSCAR_PROTOCOLO,
    FRASE_FALLA_LLM,
    FRASE_FIN_METRONOMO,
    FRASE_INICIO_METRONOMO,
    FRASES_ALIENTO_RCP,
    ManualNoDisponible,
    RetrieverNoListo,
    Turno,
    _elegir_frase_espera,
    _get_retriever,
    _ultima_pregunta,
    consultar_manual,
    contexto_del_turno,
    estado_actual,
    preparar_turno,
    prewarm,
)
from prompts import KEYTERMS_ES, SALUDO, SYSTEM_INSTRUCTIONS
from rag import load_settings
from triage import DESCRIPCION_REGISTRAR_DATOS, TriageState, rcp_en_curso, registrar_datos

load_dotenv(".env.local")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("emergency-agent")


# gemini-2.5-flash ya no se habilita para claves nuevas (la API devuelve 404 y
# sugiere gemini-3.8-flash).
GEMINI_MODELO = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def create_llm(model: str | None = None):
    """Crea el LLM: prioriza Groq si está configurado (vía openai plugin),
    o Google Gemini directo con clave propia, o gateway de LiveKit como fallback."""
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    provider = os.getenv("LLM_PROVIDER", "").lower()
    modelo = model or os.getenv("LLM_MODEL", "")

    # Determinar si usar Groq:
    use_groq = bool(groq_key) and (
        provider == "groq"
        or "llama" in modelo.lower()
        or "groq" in modelo.lower()
        or "gpt-oss" in modelo.lower()
        or "qwen" in modelo.lower()
        or (provider != "google" and provider != "gemini" and "gemini" not in modelo.lower())
    )

    if use_groq:
        mod = modelo or "openai/gpt-oss-120b"
        # gpt-oss es un modelo de razonamiento y el plugin solo le fija
        # reasoning_effort a los GPT-5, así que Groq usaba "medium": medido con
        # el prompt real, ~1900 tokens de razonamiento oculto y 2,5 s por
        # llamada. Con "low" baja a ~0,6 s y la calidad de las tools se sostiene.
        extra = {}
        if "gpt-oss" in mod:
            extra["reasoning_effort"] = os.getenv("LLM_REASONING_EFFORT", "low")
        logger.info("usando Groq vía livekit.plugins.openai.LLM (modelo=%s %s)", mod, extra)
        groq = openai.LLM(
            model=mod,
            api_key=groq_key,
            base_url="https://api.groq.com/openai/v1",
            temperature=0.1,
            parallel_tool_calls=True,
            _strict_tool_schema=False,
            **extra,
        )
        # Respaldo: con la cuenta gratuita de Groq (8000 tokens por minuto, ~2
        # turnos) el 429 llegaba enseguida; tras varios turnos fallidos la
        # sesión se cerraba y el agente quedaba mudo en plena RCP. Con el
        # adapter, si Groq falla el mismo turno sale por el gateway de LiveKit
        # (y, si hay clave, por Gemini). Gemini solo no alcanzaba: con la clave
        # gratuita devolvía 503/504 en las pruebas.
        if os.getenv("LLM_FALLBACK", "on").lower() not in {"0", "off", "false", "no"}:
            respaldo = os.getenv("LLM_FALLBACK_MODEL", "openai/gpt-4.1-mini")
            cadena = [
                groq,
                inference.LLM(model=respaldo, extra_kwargs={"temperature": 0.1, "parallel_tool_calls": True}),
            ]
            if gemini_key:
                cadena.append(google.LLM(model=GEMINI_MODELO, api_key=gemini_key, temperature=0.1))
            logger.info("respaldo del LLM: %s", " -> ".join([respaldo] + ([GEMINI_MODELO] if gemini_key else [])))
            # Gemini rechaza plazos menores a 10 s (el default del adapter es 5).
            return lk_llm.FallbackAdapter(cadena, attempt_timeout=10.0)
        return groq

    if gemini_key:
        mod = modelo or GEMINI_MODELO
        if "gemma" in mod or mod.startswith("google/") or "llama" in mod or "oss" in mod:
            mod = GEMINI_MODELO
        logger.info("usando livekit.plugins.google.LLM (modelo=%s)", mod)
        return google.LLM(model=mod, api_key=gemini_key, temperature=0.1)

    return inference.LLM(
        model=modelo or "google/gemma-4-31b-it",
        extra_kwargs={"temperature": 0.1, "parallel_tool_calls": True},
    )


def create_stt():
    """Crea el STT: usa Deepgram con clave propia si existe, sino gateway."""
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    if deepgram_key:
        logger.info("usando livekit.plugins.deepgram.STT directo con clave propia")
        return deepgram.STT(model="nova-3", language="es", api_key=deepgram_key)
    return inference.STT(model="deepgram/nova-3", language="es")


def create_tts():
    """Crea el TTS: usa Cartesia con clave propia si existe, sino gateway."""
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    voice_id = os.getenv("CARTESIA_VOICE_ID", "b4b8e2af-6139-466e-a93a-30c20d2e1fc5")
    if cartesia_key:
        logger.info("usando livekit.plugins.cartesia.TTS directo con clave propia")
        return cartesia.TTS(model="sonic-3", voice=voice_id, language="es", api_key=cartesia_key)
    return inference.TTS(
        model="cartesia/sonic-3.6",
        voice=voice_id,
        extra_kwargs={"language": "es"},
    )


# --- tools del LLM -------------------------------------------------------------
#
# La descripción que lee el modelo y la lógica viven en nucleo.py y triage.py.
# Acá queda solo lo propio de LiveKit: la frase de espera y el ToolError.


@function_tool(
    name="buscar_protocolo",
    description=DESCRIPCION_BUSCAR_PROTOCOLO,
    flags=ToolFlag.IGNORE_ON_ENTER,
    on_duplicate="replace",
)
async def buscar_protocolo(context: RunContext, query: str) -> str:
    st: TriageState = context.userdata
    texto = ""
    error: ManualNoDisponible | None = None
    async with context.with_filler(_elegir_frase_espera(st), delay=0.6, max_steps=1):
        try:
            texto = await consultar_manual(query, st)
        except ManualNoDisponible as exc:
            error = exc
    if error is not None:
        raise ToolError(str(error))
    return texto


@function_tool(
    name="registrar_datos_escena",
    description=DESCRIPCION_REGISTRAR_DATOS,
    flags=ToolFlag.IGNORE_ON_ENTER,
)
async def registrar_datos_escena(
    context: RunContext[TriageState],
    que_paso: str | None = None,
    heridos: str | None = None,
    riesgos: str | None = None,
    consciente: bool | None = None,
    respira: bool | None = None,
    caller_seguro: bool | None = None,
    atrapado: bool | None = None,
) -> str:
    return registrar_datos(
        context.userdata,
        que_paso=que_paso,
        heridos=heridos,
        riesgos=riesgos,
        consciente=consciente,
        respira=respira,
        caller_seguro=caller_seguro,
        atrapado=atrapado,
    )


# --- contexto del turno sobre el historial de LiveKit ---------------------------


def ultima_respuesta_de(chat_ctx) -> str:
    """Lo último que el agente le DIJO a la persona, según el historial.

    Sale del historial confirmado y no de lo que genera el LLM: por voz,
    LiveKit genera la respuesta por adelantado (preemptive generation) antes
    de que termine el turno, y ese borrador puede descartarse. Guardarlo desde
    llm_node hizo que en producción un «Sí» a «¿Estás en un lugar seguro?» se
    tomara como respuesta a un «¿Hay alguien herido?» que nunca se dijo."""
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and item.role == "assistant":
            return item.text_content or ""
    return ""


def _ultimo_mensaje_de_usuario(chat_ctx) -> lk_llm.ChatMessage | None:
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and item.role == "user":
            return item
    return None


def con_contexto(chat_ctx, turno: Turno):
    """Copia de chat_ctx con el contexto del turno pegado al último mensaje de
    la persona. Es la copia que va al LLM: el historial no cambia.

    Los protocolos se agregan solo si el mensaje todavía no los tiene (en una
    respuesta anticipada el turno no se confirmó y el mensaje está pelado)."""
    mensaje = _ultimo_mensaje_de_usuario(chat_ctx)
    if mensaje is None:
        return chat_ctx
    agregado = []
    protocolos = turno.texto_protocolos()
    if protocolos and protocolos not in (mensaje.text_content or ""):
        agregado.append(protocolos)
    if directivas := turno.texto_directivas():
        agregado.append(directivas)
    if not agregado:
        return chat_ctx
    copia = chat_ctx.copy()
    i = next(i for i, item in enumerate(copia.items) if item.id == mensaje.id)
    copia.items[i] = mensaje.model_copy(update={"content": [*mensaje.content, *agregado]})
    return copia


class TurnosConfirmados:
    """Qué contexto le toca a cada respuesta, venga por donde venga.

    - Voz: on_user_turn_completed confirma el turno (actualiza el estado) y lo
      asocia al mensaje de la persona.
    - Chat y ensayos: se confirma antes de session.run() y se asocia al
      próximo mensaje que llegue al LLM.
    - Voz con respuesta anticipada (preemptive generation): LiveKit empieza a
      generar ANTES de que termine el turno, sin pasar por
      on_user_turn_completed, y si la transcripción final coincide usa esa
      respuesta tal cual. Antes el contexto se pegaba al mensaje recién en
      on_user_turn_completed y esas respuestas salían sin el aviso crítico ni
      el protocolo (en producción, más de la mitad de los turnos por voz).
      Ahora se calcula sobre una COPIA del estado, porque el turno todavía
      puede cambiar, y el estado real se actualiza al confirmar. Da lo mismo
      porque preparar_turno es determinística: mismo texto, mismo estado.
    """

    def __init__(self) -> None:
        self._por_mensaje: dict[str, Turno] = {}
        self._siguiente: Turno | None = None
        self._anticipado: str | None = None
        self._confirmando: asyncio.Future[Turno] | None = None
        self._inicio_confirmacion = 0.0

    async def confirmar(
        self, texto: str, st: TriageState, ultima_respuesta: str, mensaje_id: str | None = None
    ) -> Turno:
        """Actualiza el estado con lo que dijo la persona. Sin `mensaje_id`, el
        turno queda para el próximo mensaje que llegue al LLM."""
        confirmando = asyncio.get_running_loop().create_future()
        self._confirmando, self._inicio_confirmacion = confirmando, time.time()
        anticipado, self._anticipado = self._anticipado, None
        try:
            turno = await preparar_turno(texto, st, ultima_respuesta)
        except BaseException:
            confirmando.set_result(Turno())  # que no quede colgada ninguna respuesta
            raise
        confirmando.set_result(turno)
        if mensaje_id is None:
            self._siguiente = turno
        else:
            self._por_mensaje[mensaje_id] = turno
        if anticipado is not None:
            # La respuesta anticipada sigue en curso y, si llama una tool, vuelve
            # a pasar por llm_node: desde ahora usa el turno confirmado.
            self._por_mensaje[anticipado] = turno
        return turno

    async def para_respuesta(self, chat_ctx, st: TriageState) -> tuple[Turno | None, TriageState]:
        """El turno de la respuesta que se va a generar y el estado con el que
        se calculó (para decidir el aviso del 911)."""
        mensaje = _ultimo_mensaje_de_usuario(chat_ctx)
        if mensaje is None:
            return None, st
        if (turno := self._por_mensaje.get(mensaje.id)) is not None:
            return turno, st
        if self._siguiente is not None:
            turno, self._siguiente = self._siguiente, None
            self._por_mensaje[mensaje.id] = turno
            return turno, st
        if self._confirmando is not None and mensaje.created_at <= self._inicio_confirmacion:
            # Respuesta anticipada de un turno que ya se está confirmando.
            turno = await asyncio.shield(self._confirmando)
            self._por_mensaje[mensaje.id] = turno
            return turno, st
        logger.info("respuesta anticipada: contexto calculado sobre una copia del estado")
        copia = copy.deepcopy(st)
        self._anticipado = mensaje.id
        marca = _ANTICIPADA.set(True)
        try:
            turno = await preparar_turno(mensaje.text_content or "", copia, ultima_respuesta_de(chat_ctx))
        finally:
            _ANTICIPADA.reset(marca)
        return turno, copia


class Assistant(Agent):
    def __init__(self, al_actualizar_estado: Callable[[], None] | None = None) -> None:
        super().__init__(
            instructions=SYSTEM_INSTRUCTIONS,
            tools=[buscar_protocolo, registrar_datos_escena],
        )
        # Se llama apenas el turno actualizó el estado de triage, antes del LLM
        # (entrypoint lo usa para apagar el metrónomo si volvió a respirar).
        self._al_actualizar_estado = al_actualizar_estado
        self._turnos = TurnosConfirmados()

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """Camino de audio: confirma el turno.

        Los protocolos se pegan al mensaje para que queden en el historial. El
        estado y los avisos los agrega llm_node solo a esta respuesta. No se
        toca turn_ctx: LiveKit descartaría la respuesta anticipada, que ya
        trae el mismo contexto."""
        turno = await self._turnos.confirmar(
            new_message.text_content or "",
            self.session.userdata,
            ultima_respuesta_de(turn_ctx),
            mensaje_id=new_message.id,
        )
        if protocolos := turno.texto_protocolos():
            new_message.content.append(protocolos)
        if self._al_actualizar_estado is not None:
            self._al_actualizar_estado()

    async def preparar_texto(self, texto: str) -> tuple[str, Turno]:
        """Camino de texto (chat de la web, ensayos): session.run() no pasa por
        on_user_turn_completed. Devuelve lo que hay que pasarle a session.run()."""
        turno = await self._turnos.confirmar(
            texto, self.session.userdata, ultima_respuesta_de(self.session.history)
        )
        if self._al_actualizar_estado is not None:
            self._al_actualizar_estado()
        return turno.con_protocolos(texto), turno

    async def llm_node(self, chat_ctx, tools, model_settings: ModelSettings):
        """Agrega el contexto del turno a esta respuesta y corrige el texto
        antes de hablarlo (ver habla.py): jerga, voseo y el aviso «Ya estás
        geolocalizado y la ayuda va en camino.», que lo pone el sistema una sola
        vez cuando se derivó al 911."""
        turno, estado = await self._turnos.para_respuesta(chat_ctx, self.session.userdata)
        if turno is not None:
            chat_ctx = con_contexto(chat_ctx, turno)
        dichas = (m.text_content or "" for m in chat_ctx.messages() if m.role == "assistant")
        st = EstadoAviso(derivado=estado.derivado, aviso_911_dicho=aviso_ya_dicho(dichas))
        norm = NormalizadorStream()

        def salida(texto: str) -> str:
            return aplicar_aviso_911(texto, st) if texto else texto

        if turno is not None and turno.respuesta_fija:
            # Momento crítico: la frase es fija y sale al instante, sin LLM.
            yield salida(turno.respuesta_fija)
            return

        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            if isinstance(chunk, str):
                if listo := salida(norm.push(chunk)):
                    yield listo
            elif isinstance(chunk, lk_llm.ChatChunk) and chunk.delta and chunk.delta.content:
                listo = salida(norm.push(chunk.delta.content))
                chunk.delta.content = listo or None
                if listo or chunk.delta.tool_calls or chunk.usage:
                    yield chunk
            else:
                if resto := salida(norm.flush()):
                    yield resto
                yield chunk
        if resto := salida(norm.flush()):
            yield resto


# --- metrónomo de RCP ----------------------------------------------------------

class AlientoRCP:
    """Una frase corta de aliento cada tanto mientras la persona comprime en silencio.

    user_away_timeout no alcanza: se dispara una sola vez y no se rearma hasta
    que la persona vuelve a hablar, y en RCP ya se derivó, así que el handler
    de «away» no dice nada. Sin esto, después de la indicación quedaba solo
    el clic durante minutos."""

    def __init__(self, session: AgentSession, metronomo: Metronomo, cada_s: float = 20.0) -> None:
        self._session = session
        self._metronomo = metronomo
        self._cada_s = cada_s
        self._ultima_actividad = time.monotonic()
        self._siguiente = 0
        self._tarea: asyncio.Task[None] | None = None
        session.on("agent_state_changed", self._actividad)
        session.on("user_state_changed", self._actividad)

    def _actividad(self, _ev) -> None:
        self._ultima_actividad = time.monotonic()

    def iniciar(self) -> None:
        if self._tarea is None or self._tarea.done():
            self._ultima_actividad = time.monotonic()
            self._tarea = asyncio.create_task(self._bucle(), name="aliento-rcp")

    def aclose(self) -> None:
        if self._tarea is not None:
            self._tarea.cancel()

    async def _bucle(self) -> None:
        while self._metronomo.activo:
            await asyncio.sleep(1.0)
            if self._metronomo.encendido_hace >= self._metronomo.max_s:
                # Tope de tiempo: no puede quedar sonando indefinidamente.
                self._metronomo.detener()
                st: TriageState = self._session.userdata
                st.metronomo_activo = False
                st.metronomo_silenciado = True
                logger.info("metrónomo: se cumplió el tope de %.0f s", self._metronomo.max_s)
                self._session.say(FRASE_FIN_METRONOMO, allow_interruptions=True)
                return
            quieto = self._session.agent_state == "listening" and self._session.user_state != "speaking"
            if quieto and time.monotonic() - self._ultima_actividad >= self._cada_s:
                frase = FRASES_ALIENTO_RCP[self._siguiente % len(FRASES_ALIENTO_RCP)]
                self._siguiente += 1
                self._session.say(frase, allow_interruptions=True)
                self._ultima_actividad = time.monotonic()


server = AgentServer(setup_fnc=prewarm, initialize_process_timeout=30.0)


# AGENT_NAME permite levantar una copia de prueba (p. ej. con agent.py dev)
# sin competir con el agente desplegado por los despachos de producción.
@server.rtc_session(agent_name=os.getenv("AGENT_NAME", "asistente-emergencias"))
async def entrypoint(ctx: agents.JobContext):
    # Todas las líneas de log del job quedan correlacionables por sala.
    ctx.log_context_fields = {"room": ctx.room.name, "job": ctx.job.id}
    logger.info("conectando a la sala %s", ctx.room.name)

    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    session = AgentSession[TriageState](
        userdata=TriageState(),
        stt=create_stt(),
        llm=create_llm(),
        tts=create_tts(),
        turn_handling={
            # max_delay 3.0 -> 1.2: con respuestas cortas («Sí.») el detector de
            # fin de turno duda y espera el máximo; medido por voz, eso eran 2 s
            # de silencio antes de cada respuesta. Alguien asustado habla en
            # frases cortas; si hace una pausa y sigue, interrumpe al agente y
            # el turno se retoma.
            "endpointing": {"mode": "dynamic", "min_delay": 0.5, "max_delay": 1.2},
            "interruption": {"min_duration": 0.4, "min_words": 2},
            "preemptive_generation": {"preemptive_tts": False, "max_speech_duration": 15.0},
        },
        keyterms_options={
            "keyterms": KEYTERMS_ES,
            "keyterm_detection": {"enabled": True, "turn_interval": 2},
        },
        max_tool_steps=4,
        user_away_timeout=20.0,
        aec_warmup_duration=1.0,
    )

    metronomo = Metronomo()
    aliento = AlientoRCP(session, metronomo)

    ya_sono = False

    def _sincronizar_metronomo(role: str) -> None:
        """Prende el metrónomo cuando ya se DIJO la indicación de comprimir (el
        item del asistente llega después de reproducirse) y lo apaga apenas el
        turno de la persona cambia el estado: volvió a respirar, llegó la ayuda
        o pidió sacar el sonido. Lo segundo se llama desde
        on_user_turn_completed y no desde el item del usuario, que LiveKit no
        emite si la respuesta se interrumpe o falla: con eso, en la consola el
        clic seguía sonando después de «sí, respira»."""
        nonlocal ya_sono
        st = session.userdata
        sonar = rcp_en_curso(st) and not st.metronomo_silenciado and session.output.audio_enabled
        if role == "assistant" and sonar and metronomo.iniciar():
            st.metronomo_activo = True
            if not ya_sono:
                session.say(FRASE_INICIO_METRONOMO, allow_interruptions=True)
            ya_sono = True
            aliento.iniciar()
        elif not sonar and metronomo.detener():
            st.metronomo_activo = False

    @session.on("close")
    def _on_close(_ev):
        # Si la sesión se cierra (por ejemplo, el LLM falló varias veces
        # seguidas), el clic no puede quedar sonando solo.
        aliento.aclose()
        metronomo.detener()
        session.userdata.metronomo_activo = False

    @session.on("conversation_item_added")
    def _on_item(ev):
        item = ev.item
        role = getattr(item, "role", None)
        if role == "assistant":
            _sincronizar_metronomo(role)
        m = getattr(item, "metrics", None) or {}
        if not m:
            return

        if role == "assistant":
            # Save metrics for debug mode
            session.userdata.last_llm_metrics = {
                "e2e_latency_ms": m.get("e2e_latency"),
                "llm_ttft_ms": m.get("llm_node_ttft"),
                "tts_ttfb_ms": m.get("tts_node_ttfb"),
                "playback_latency_ms": m.get("playback_latency"),
            }
            logger.info(
                "latencia | e2e=%s ttft=%s tts_ttfb=%s playback=%s",
                _ms(m.get("e2e_latency")),
                _ms(m.get("llm_node_ttft")),
                _ms(m.get("tts_node_ttfb")),
                _ms(m.get("playback_latency")),
            )
        elif role == "user":
            # end_of_turn_delay solo existe en mensajes del usuario
            eot = m.get("end_of_turn_delay")
            if eot is not None and session.userdata.last_llm_metrics is not None:
                session.userdata.last_llm_metrics["end_of_turn_delay_ms"] = eot

    @session.on("metrics_collected")
    def _on_metrics(ev):
        m = ev.metrics
        if hasattr(m, "completion_tokens"):
            session.userdata.last_llm_tokens = {
                "prompt_tokens": m.prompt_tokens,
                "completion_tokens": m.completion_tokens,
                "total_tokens": m.total_tokens,
                "cached_tokens": m.prompt_cached_tokens,
                "tokens_per_second": m.tokens_per_second,
            }

    @session.on("session_usage_updated")
    def _on_usage(ev):
        logger.debug("uso acumulado: %s", ev.usage)

    @session.on("user_state_changed")
    def _on_user_state(ev):
        if ev.new_state == "away" and not session.userdata.derivado:
            session.say("Seguí, te escucho. ¿Cómo va?")

    @session.on("error")
    def _on_error(ev):
        # Si el LLM (y su respaldo) fallan, el turno se pierde sin decir nada:
        # en una emergencia el silencio es lo peor. Esta frase no pasa por el LLM.
        error = ev.error
        if getattr(error, "type", None) == "llm_error" and not error.recoverable:
            logger.error("el LLM no respondió este turno: %s", getattr(error, "error", error))
            session.say(FRASE_FALLA_LLM, allow_interruptions=True)

    await session.start(
        room=ctx.room,
        agent=Assistant(al_actualizar_estado=lambda: _sincronizar_metronomo("user")),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(),
        ),
    )

    _wire_chat_backchannel(session, ctx)

    participant = await ctx.wait_for_participant()
    logger.info("participante conectado: %s", participant.identity)

    # El saludo va lo antes posible: el frontend no deja hablar ni escribir
    # hasta recibirlo, así que todo lo que se haga antes es espera para quien
    # llama. El metrónomo y el log de configuración pueden ir después.
    try:
        asyncio.create_task(
            ctx.room.local_participant.publish_data(
                payload=json.dumps({"type": "chat_reply", "message": SALUDO}).encode("utf-8"),
                topic="test-chat",
            )
        )
    except Exception:
        pass
    session.say(SALUDO, allow_interruptions=True)

    await metronomo.start(ctx.room)

    async def _cerrar_metronomo() -> None:
        aliento.aclose()
        await metronomo.aclose()

    ctx.add_shutdown_callback(_cerrar_metronomo)

    retriever = nucleo.retriever_actual()
    if retriever is None:
        logger.warning("config | índice del manual todavía cargando: se usan textos de respaldo")
    else:
        logger.info(
            "config | llm=%s stt=deepgram/nova-3(es) keyterms=%d rerank=%s piso=%s indice=%s",
            os.getenv("LLM_MODEL", "google/gemma-4-31b-it"),
            len(KEYTERMS_ES),
            retriever.settings.rerank_model if retriever.settings.rerank_enabled else "off",
            retriever.settings.min_rerank_score
            if retriever.settings.rerank_enabled
            else retriever.settings.min_score,
            len(retriever.index) if retriever.index else "NO (búsqueda contra la base)",
        )

    logger.info("agente activo en la sala %s", ctx.room.name)


def _ms(valor: float | None) -> str:
    return "—" if valor is None else f"{valor * 1000:.0f}ms"


def _wire_chat_backchannel(session: AgentSession, ctx: agents.JobContext) -> None:
    """Canal de texto para manejar el agente sin audio."""

    @ctx.room.on("data_received")
    def on_data_received(data_packet: rtc.DataPacket):
        try:
            raw_text = data_packet.data.decode("utf-8")
            try:
                payload = json.loads(raw_text)
            except Exception:
                payload = raw_text
        except Exception as exc:
            logger.error("no pude parsear el paquete de chat: %s", exc)
            return

        if isinstance(payload, dict):
            query = payload.get("message") or payload.get("text") or payload.get("content")
            debug = payload.get("debug", False)
        else:
            query = str(payload)
            debug = False

        if not query or not query.strip():
            return

        logger.info("chat recibido: %s (debug=%s)", query, debug)

        async def process_chat():
            # La pestaña Test del frontend no reproduce audio, pero el agente
            # igual sintetizaba voz con Cartesia y session.run() esperaba a que
            # terminara de "sonar": ~6 s por respuesta y caracteres gastados.
            if session.output.audio_enabled:
                session.output.set_audio_enabled(False)
                logger.info("chat de texto: salida de audio desactivada para esta sesión")

            # Clear previous turn debug data
            session.userdata.tool_calls.clear()
            session.userdata.last_llm_metrics = None
            session.userdata.last_llm_tokens = None
            t_start = time.monotonic()

            try:
                await ctx.room.local_participant.publish_data(
                    payload=json.dumps({
                        "type": "chat_status",
                        "status": "thinking",
                        "message": "Asistente analizando la situación...",
                    }).encode("utf-8"),
                    topic="test-chat",
                )
            except Exception:
                pass

            entrada, _ = await session.current_agent.preparar_texto(query)

            try:
                # interrupt() devuelve un future que se completa cuando la
                # interrupción terminó: no hace falta un sleep fijo.
                await asyncio.wait_for(session.interrupt(), timeout=1.0)
            except Exception:
                pass
            try:
                await session.run(user_input=entrada)
            except (asyncio.CancelledError, Exception) as exc:
                logger.warning("run de chat interrumpido o fallido: %s", exc)

            total_ms = int((time.monotonic() - t_start) * 1000)

            messages = session.history.messages()
            assistant_msgs = [m for m in messages if m.role == "assistant"]
            reply = (
                assistant_msgs[-1].text_content
                if assistant_msgs
                else "No se pudo generar respuesta."
            )
            logger.info("respondiendo chat: %s", reply)

            if debug:
                tool_calls = list(session.userdata.tool_calls)
                llm_metrics = session.userdata.last_llm_metrics or {}
                llm_tokens = session.userdata.last_llm_tokens
                # La config sale de variables de entorno: no hace falta que el
                # índice esté cargado para mostrarla.
                cargado = nucleo.retriever_actual()
                ajustes = cargado.settings if cargado is not None else load_settings()

                # Count searches
                search_count = sum(
                    1 for tc in tool_calls if tc.get("tool") in ("buscar_protocolo", "prefetch_protocolo")
                )

                # Merge tokens into metrics
                if llm_tokens:
                    llm_metrics["prompt_tokens"] = llm_tokens.get("prompt_tokens")
                    llm_metrics["completion_tokens"] = llm_tokens.get("completion_tokens")
                    llm_metrics["total_tokens"] = llm_tokens.get("total_tokens")
                    llm_metrics["cached_tokens"] = llm_tokens.get("cached_tokens")
                    llm_metrics["tokens_per_second"] = llm_tokens.get("tokens_per_second")

                reply_payload = {
                    "type": "chat_reply_debug",
                    "message": reply,
                    "total_response_ms": total_ms,
                    "search_count": search_count,
                    "tool_calls": tool_calls,
                    "llm_metrics": llm_metrics,
                    "config": {
                        "llm_model": os.getenv("LLM_MODEL", "google/gemma-4-31b-it"),
                        "embed_model": ajustes.embed_model,
                        "rerank_enabled": ajustes.rerank_enabled,
                        "rerank_model": ajustes.rerank_model if ajustes.rerank_enabled else None,
                        "top_k": ajustes.top_k,
                        "k_vector": ajustes.k_vector,
                        "min_score": ajustes.min_score,
                        "rerank_min_score": ajustes.min_rerank_score if ajustes.rerank_enabled else None,
                        "indice_cargado": cargado is not None,
                    },
                }
            else:
                reply_payload = {"type": "chat_reply", "message": reply}

            try:
                await ctx.room.local_participant.publish_data(
                    payload=json.dumps(reply_payload).encode("utf-8"),
                    topic="test-chat",
                )
            except Exception as exc:
                logger.error("error publicando chat_reply: %s", exc)

        asyncio.create_task(process_chat())


if __name__ == "__main__":
    agents.cli.run_app(server)

