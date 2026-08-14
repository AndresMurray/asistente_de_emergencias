import asyncio
import json
import logging
import os

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

from livekit import agents, rtc  # type: ignore
from livekit.agents import (  # type: ignore
    Agent,
    AgentServer,
    AgentSession,
    RunContext,
    ToolError,
    function_tool,
    inference,
    metrics,
    room_io,
)
from livekit.agents.llm import ToolFlag

import telephony
from prompts import KEYTERMS_ES, SALUDO, SYSTEM_INSTRUCTIONS
from rag import Retriever
from triage import (
    AVISO_CRITICO,
    TriageState,
    procesar_turno_usuario,
    registrar_datos_escena,
)

load_dotenv(".env.local")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("emergency-agent")

# Un retriever por proceso: adentro tiene el pool de conexiones y se comparte
# entre los jobs del proceso. Antes acá había una única conexión psycopg2 global
# compartida entre todos los jobs concurrentes, que era una condición de carrera
# esperando a pasar.
_retriever: Retriever | None = None


def _get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
        _retriever.connect()
    return _retriever


@function_tool(flags=ToolFlag.IGNORE_ON_ENTER, on_duplicate="replace")
async def buscar_protocolo(context: RunContext, query: str) -> str:
    """Busca en el manual de primeros auxilios los fragmentos relevantes.

    Llamala SIEMPRE antes de dar cualquier indicación de primeros auxilios.
    Reformulá lo que dijo la persona con palabras del manual: "no respira" se
    busca como "herido inconsciente que no respira reanimación cardiopulmonar";
    "se está desangrando" como "control de hemorragias externas".
    """
    retriever = _get_retriever()

    # El filler solo habla si de verdad hay hueco. Medido, el caso típico es
    # ~490 ms (Cohere ~250 + pgvector ~230), así que con delay 0.7 casi nunca
    # dispara; cuando Cohere arranca en frío y se va a 2 s, sí.
    async with context.with_filler("Dame un segundo.", delay=0.7, max_steps=1):
        result = await retriever.search(query)

    if result.status == "error":
        # Distinto de "no hay protocolo": esto es una falla técnica. Se levanta
        # ToolError para que el modelo tome el camino de "perdí el acceso al
        # manual" y derive, en lugar de decirle a alguien con un herido que el
        # procedimiento no existe. Antes los dos caminos devolvían "".
        raise ToolError(
            "La búsqueda en el manual falló por un problema técnico. "
            f"Motivo: {result.error}"
        )

    if result.status == "no_match":
        return (
            "El manual no tiene nada relevante para esa consulta. "
            "No inventes un procedimiento: decí que no está en tu manual y derivá."
        )

    return result.para_llm()


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=SYSTEM_INSTRUCTIONS,
            tools=[buscar_protocolo, registrar_datos_escena],
        )

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """Camino de audio: detecta riesgo de vida sin depender del modelo.

        Medido con session.run(): ante "no se mueve y no respira" el modelo hace
        lo correcto —va directo a las compresiones— pero NO llama a
        registrar_datos_escena, así que TriageState quedaba vacío, critico() daba
        False y el briefing al 911 habría salido todo NO CONFIRMADO. Para una
        señal de seguridad eso no alcanza: no puede depender de que el modelo se
        acuerde de llamar una tool.

        La lógica vive en triage.procesar_turno_usuario porque el mismo chequeo
        tiene que correr en el camino de texto, que no pasa por este hook.
        """
        senal = procesar_turno_usuario(
            new_message.text_content, self.session.userdata
        )
        if senal:
            # Se le inyecta como contexto del turno para que priorice sin que
            # haya que esperar a que llame una tool.
            turn_ctx.add_message(
                role="system", content=AVISO_CRITICO.format(senal=senal)
            )


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: agents.JobContext):
    # Todas las líneas de log del job quedan correlacionables por sala.
    ctx.log_context_fields = {"room": ctx.room.name, "job": ctx.job.id}
    logger.info("conectando a la sala %s", ctx.room.name)

    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    session = AgentSession[TriageState](
        userdata=TriageState(),
        stt=inference.STT(model="deepgram/nova-3", language="es"),
        llm=inference.LLM(
            # gpt-4o-mini era de lo más viejo del catálogo del gateway, y el
            # prompt nuevo le pide más: grounding estricto, matices del
            # rioplatense y argumentos de tool bien armados.
            model=os.getenv("LLM_MODEL", "openai/gpt-4.1-mini"),
            # parallel_tool_calls en True a propósito: con un solo tool call por
            # paso, el modelo priorizaba buscar_protocolo y nunca registraba los
            # datos de la escena. Necesita poder guardar y buscar en el mismo
            # turno, o el briefing al 911 sale vacío.
            extra_kwargs={"temperature": 0.2, "parallel_tool_calls": True},
        ),
        tts=inference.TTS(
            model="cartesia/sonic-3",
            voice="595f1cfa-bd48-432c-a519-abe83e210398",
        ),
        # La derivación al 911 va como toolset de sesión, no del Agent, para que
        # corra en background: así el agente le sigue hablando a la persona
        # mientras el teléfono del 911 suena.
        tools=[telephony.toolset()],
        turn_handling={
            # El default con turn detector streaming es min 0.3 / max 2.5. Se
            # sube el máximo porque alguien llorando hace pausas largas en medio
            # de una frase, y que lo corten al medio es la falla más dañina.
            # 'dynamic' adapta el corte al ritmo de cada persona.
            "endpointing": {"mode": "dynamic", "max_delay": 4.5},
            # Sirenas, sollozos y una puerta que se cierra interrumpían al agente
            # en medio de una indicación. Con dos palabras mínimas, un
            # "¡no respira!" real igual entra al instante.
            "interruption": {"min_duration": 0.4, "min_words": 2},
            # preemptive_generation ya viene activado por default; lo que se
            # ajusta es el TTS preventivo, que acá conviene APAGADO: casi todos
            # los turnos arrancan con una tool call, así que el audio preventivo
            # se descarta y se escucha como falso arranque.
            "preemptive_generation": {"preemptive_tts": False, "max_speech_duration": 15.0},
        },
        # OJO, esto puede fallar en silencio. El SDK reporta
        # capabilities.keyterms=True para deepgram/nova-3 y le reenvía la lista
        # como `keyterm` sin importar el idioma, así que NO hay warning si
        # Deepgram no la aplica en español (históricamente el keyterm prompting
        # de nova-3 estuvo limitado a inglés). No se puede verificar leyendo
        # código: hay que correr `python agent.py console`, leer en voz alta
        # «torniquete», «preseñalización» y «frente-mentón», y ver si aparecen
        # bien en la transcripción. Si no, las alternativas son
        # extra_kwargs={"keywords": [(termino, peso)]} de nova-2, o dejar solo la
        # detección por LLM, que es agnóstica del proveedor.
        keyterms_options={
            "keyterms": KEYTERMS_ES,
            "keyterm_detection": {"enabled": True, "turn_interval": 2},
        },
        # Triage + búsqueda + derivación pueden encadenarse en un mismo turno.
        max_tool_steps=5,
        # Quien llama va a quedarse callado un rato largo mientras hace
        # compresiones. Se lo detecta para no dejar la línea muda.
        user_away_timeout=20.0,
        # 3 s de habla no interrumpible (el default) es demasiado cuando la
        # escena puede cambiar de un segundo a otro.
        aec_warmup_duration=1.0,
    )

    @session.on("conversation_item_added")
    def _on_item(ev):
        """Latencia percibida, turno por turno.

        No se usa el evento metrics_collected (deprecado en 1.6.5, avisa que hay
        que usar session_usage_updated para uso y ChatMessage.metrics para
        latencia por turno) ni UsageCollector (también deprecado), ni se arma
        persistencia de transcripciones ni OTel: session.start(record=...) ya
        sube audio, transcripciones, traces y logs a LiveKit Cloud por default.

        e2e_latency es EL número de esta fase: cuánto pasa desde que la persona
        deja de hablar hasta que el agente arranca a responder.
        """
        item = ev.item
        if getattr(item, "role", None) != "assistant":
            return
        m = getattr(item, "metrics", None) or {}
        if not m:
            return
        logger.info(
            "latencia | e2e=%s ttft=%s tts_ttfb=%s fin_turno=%s",
            _ms(m.get("e2e_latency")),
            _ms(m.get("llm_node_ttft")),
            _ms(m.get("tts_node_ttfb")),
            _ms(m.get("end_of_turn_delay")),
        )

    @session.on("session_usage_updated")
    def _on_usage(ev):
        logger.debug("uso acumulado: %s", ev.usage)

    @session.on("user_state_changed")
    def _on_user_state(ev):
        # Si se queda en silencio y todavía no derivamos, no dejar la línea muda.
        if ev.new_state == "away" and not session.userdata.derivado:
            session.say("Seguí, te escucho. ¿Cómo va?")

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                # La cancelación de ruido del lado del servidor va en el trunk
                # SIP (krisp_enabled), que es config y no cuesta código. Acá
                # haría falta livekit-plugins-noise-cancellation, que no está
                # instalado; medir si suma sobre lo del trunk antes de agregar
                # la dependencia.
            ),
        ),
    )

    _wire_chat_backchannel(session, ctx)

    # Esperar a que la persona esté realmente conectada antes de saludar. En una
    # llamada SIP el saludo salía antes de que el camino de audio estuviera
    # armado, o sea que se perdía la primera frase.
    participant = await ctx.wait_for_participant()
    session.userdata.caller_identity = participant.identity
    _log_sip_attributes(participant)

    # Deja rastro de la config que no se puede verificar leyendo código, para
    # poder confrontarla contra lo que se escucha en una corrida de consola.
    retriever = _get_retriever()
    logger.info(
        "config | llm=%s stt=deepgram/nova-3(es) keyterms=%d rerank=%s piso=%s",
        os.getenv("LLM_MODEL", "openai/gpt-4.1-mini"),
        len(KEYTERMS_ES),
        retriever.settings.rerank_model if retriever.settings.rerank_enabled else "off",
        retriever.settings.min_rerank_score
        if retriever.settings.rerank_enabled
        else retriever.settings.min_score,
    )

    # session.say en lugar de generate_reply: el saludo es una cadena fija y
    # antes se pagaba un round trip completo de LLM para producirla, justo en el
    # primer segundo de la llamada, que es el que más se nota. No se hace await
    # del handle, para no serializar el saludo contra las primeras palabras de
    # la persona.
    session.say(SALUDO, allow_interruptions=True)

    logger.info("agente activo en la sala %s", ctx.room.name)


def _ms(valor: float | None) -> str:
    return "—" if valor is None else f"{valor * 1000:.0f}ms"


def _log_sip_attributes(participant: rtc.RemoteParticipant) -> None:
    """Deja rastro de quién llamó, para poder reconstruir una llamada.

    En una llamada SIP, LiveKit publica sip.phoneNumber / sip.trunkPhoneNumber /
    sip.callID como atributos del participante. En WebRTC no están y no pasa nada.
    """
    attrs = participant.attributes or {}
    sip = {k: v for k, v in attrs.items() if k.startswith("sip.")}
    if sip:
        logger.info(
            "llamada entrante | desde=%s hacia=%s call_id=%s",
            sip.get("sip.phoneNumber", "?"),
            sip.get("sip.trunkPhoneNumber", "?"),
            sip.get("sip.callID", "?"),
        )
    else:
        logger.info("participante no-SIP: %s", participant.identity)


def _wire_chat_backchannel(session: AgentSession, ctx: agents.JobContext) -> None:
    """Canal de texto para manejar el agente sin audio.

    Lo usa metricas/coverage/ para manejar el agente desplegado por texto. Se
    conserva la semántica original: se interrumpe el habla en curso para evitar
    runs anidados, se corre el turno con el texto recibido y se publica la
    respuesta por el mismo canal de datos.
    """

    @ctx.room.on("data_received")
    def on_data_received(data_packet: rtc.DataPacket):
        try:
            payload = json.loads(data_packet.data.decode("utf-8"))
        except Exception as exc:
            logger.error("no pude parsear el paquete de chat: %s", exc)
            return

        if payload.get("type") != "chat":
            return

        query = payload.get("message")
        logger.info("chat recibido: %s", query)

        async def process_chat():
            # El mismo chequeo determinístico que en el camino de audio:
            # session.run() no pasa por Agent.on_user_turn_completed, así que sin
            # esto la evaluación por texto nunca ejercitaría la señal de riesgo
            # de vida.
            senal = procesar_turno_usuario(query, session.userdata)
            entrada = query
            if senal:
                entrada = f"{query}\n\n[{AVISO_CRITICO.format(senal=senal)}]"

            try:
                session.interrupt()
                await asyncio.sleep(0.2)
                await session.run(user_input=entrada)
            except (asyncio.CancelledError, Exception) as exc:
                logger.warning("run de chat interrumpido o fallido: %s", exc)

            messages = session.history.messages()
            assistant_msgs = [m for m in messages if m.role == "assistant"]
            reply = (
                assistant_msgs[-1].text_content
                if assistant_msgs
                else "No se pudo generar respuesta."
            )
            logger.info("respondiendo chat: %s", reply)
            try:
                await ctx.room.local_participant.publish_data(
                    payload=json.dumps(
                        {"type": "chat_reply", "message": reply}
                    ).encode("utf-8"),
                    topic="test-chat",
                )
            except Exception as exc:
                logger.error("error publicando chat_reply: %s", exc)

        asyncio.create_task(process_chat())


if __name__ == "__main__":
    agents.cli.run_app(server)
