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

from prompts import KEYTERMS_ES, SALUDO, SYSTEM_INSTRUCTIONS
from rag import Retriever
from triage import (
    AVISO_CRITICO,
    TriageState,
    derivar_a_emergencias,
    procesar_turno_usuario,
    registrar_datos_escena,
)

load_dotenv(".env.local")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("emergency-agent")

# Un retriever por proceso: adentro tiene el pool de conexiones y se comparte
# entre los jobs del proceso.
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

    async with context.with_filler("Dame un segundo.", delay=0.7, max_steps=1):
        result = await retriever.search(query)

    if result.status == "error":
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
            tools=[buscar_protocolo, registrar_datos_escena, derivar_a_emergencias],
        )

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """Camino de audio: detecta riesgo de vida sin depender del modelo."""
        senal = procesar_turno_usuario(
            new_message.text_content, self.session.userdata
        )
        if senal:
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
            model=os.getenv("LLM_MODEL", "openai/gpt-4.1-mini"),
            extra_kwargs={"temperature": 0.2, "parallel_tool_calls": True},
        ),
        tts=inference.TTS(
            model="cartesia/sonic-3",
            voice=os.getenv("CARTESIA_VOICE_ID", "b4b8e2af-6139-466e-a93a-30c20d2e1fc5"),
            extra_kwargs={"language": "es"},
        ),
        turn_handling={
            "endpointing": {"mode": "dynamic", "max_delay": 4.5},
            "interruption": {"min_duration": 0.4, "min_words": 2},
            "preemptive_generation": {"preemptive_tts": False, "max_speech_duration": 15.0},
        },
        keyterms_options={
            "keyterms": KEYTERMS_ES,
            "keyterm_detection": {"enabled": True, "turn_interval": 2},
        },
        max_tool_steps=5,
        user_away_timeout=20.0,
        aec_warmup_duration=1.0,
    )

    @session.on("conversation_item_added")
    def _on_item(ev):
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
        if ev.new_state == "away" and not session.userdata.derivado:
            session.say("Seguí, te escucho. ¿Cómo va?")

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(),
        ),
    )

    _wire_chat_backchannel(session, ctx)

    participant = await ctx.wait_for_participant()
    logger.info("participante conectado: %s", participant.identity)

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

    session.say(SALUDO, allow_interruptions=True)
    try:
        asyncio.create_task(
            ctx.room.local_participant.publish_data(
                payload=json.dumps({"type": "chat_reply", "message": SALUDO}).encode("utf-8"),
                topic="test-chat",
            )
        )
    except Exception:
        pass

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
        else:
            query = str(payload)

        if not query or not query.strip():
            return

        logger.info("chat recibido: %s", query)

        async def process_chat():
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

