import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Literal

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
    room_io,
)
from livekit.agents.llm import ToolFlag

from prompts import KEYTERMS_ES, SALUDO, SYSTEM_INSTRUCTIONS
from rag import Retriever
from metricas.latencia import LatencyRecorder
from triage import (
    AVISO_CRITICO,
    TriageState,
    derivar_a_emergencias,
    generar_aviso_critico,
    procesar_turno_usuario,
    registrar_datos_escena,
)

load_dotenv(".env.local")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("emergency-agent")

# Un retriever por proceso: adentro tiene el pool de conexiones y se comparte
# entre los jobs del proceso.
_retriever: Retriever | None = None
_retriever_lock = threading.Lock()

PrefetchCategory = Literal["no_respira", "hemorragia", "fuego", "atrapado"]


@dataclass
class _RagPrefetch:
    category: PrefetchCategory
    task: asyncio.Task


async def _prefetch_search(query: str):
    """Obtiene el pool fuera del event loop antes de consultar el RAG."""
    retriever = await asyncio.to_thread(_get_retriever)
    return await retriever.search(query)


def _get_retriever() -> Retriever:
    global _retriever
    with _retriever_lock:
        if _retriever is None:
            _retriever = Retriever()
            _retriever.connect()
    return _retriever


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_float(name: str, default: float | None) -> float | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value)


def _prefetch_category(text: str) -> PrefetchCategory | None:
    """Clasifica sólo urgencias inequívocas; inconsciencia sola no habilita RCP."""
    normalized = text.lower()
    if any(term in normalized for term in ("no respira", "no está respirando", "no esta respirando", "dejó de respirar", "dejo de respirar")):
        return "no_respira"
    if any(term in normalized for term in ("se desangra", "sangra mucho", "mucha sangre", "hemorragia")):
        return "hemorragia"
    if any(term in normalized for term in ("fuego", "incendio", "humo", "combustible", "nafta")):
        return "fuego"
    if any(term in normalized for term in ("atrapado", "aplastado", "prensado")):
        return "atrapado"
    return None


def _query_category(query: str) -> PrefetchCategory | None:
    """Evita usar un contexto prefetched para una maniobra de otra categoría."""
    return _prefetch_category(query)


def _session_prefetch(context: RunContext, query: str) -> tuple[asyncio.Task | None, bool, str | None]:
    state = context.userdata
    pending = getattr(state, "_rag_prefetch", None)
    category = _query_category(query)
    if not isinstance(pending, _RagPrefetch):
        return None, False, category
    if pending.category != category:
        # No conservar trabajo de otro protocolo: además de evitar una futura
        # reutilización errónea, ahorra una llamada externa descartada.
        if not pending.task.done():
            pending.task.cancel()
        setattr(state, "_rag_prefetch", None)
        return None, False, category
    # Se consume una sola vez: una búsqueda posterior siempre se evalúa contra
    # el query actual y no reutiliza contexto potencialmente stale.
    setattr(state, "_rag_prefetch", None)
    return pending.task, True, category


@function_tool(flags=ToolFlag.IGNORE_ON_ENTER, on_duplicate="replace")
async def buscar_protocolo(context: RunContext, query: str) -> str:
    """Busca en el manual de primeros auxilios los fragmentos relevantes.

    Llamala SIEMPRE antes de dar cualquier indicación de primeros auxilios.
    Reformulá lo que dijo la persona con palabras del manual: "no respira" se
    busca como "herido inconsciente que no respira reanimación cardiopulmonar";
    "se está desangrando" como "control de hemorragias externas".
    """
    prefetched_task, prefetched, category = _session_prefetch(context, query)

    async with context.with_filler("Dame un segundo.", delay=0.7, max_steps=1):
        result = (
            await prefetched_task
            if prefetched_task is not None
            else await _prefetch_search(query)
        )

    recorder = getattr(context.userdata, "_latency_recorder", None)
    if isinstance(recorder, LatencyRecorder):
        recorder.record_rag(
            speech_id=getattr(context.speech_handle, "id", None),
            status=result.status,
            timings_ms=result.timings_ms,
            prefetched=prefetched,
            query_category=category,
        )

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
        text = new_message.text_content
        senal = procesar_turno_usuario(
            text, self.session.userdata
        )
        if senal:
            aviso = generar_aviso_critico(senal, self.session.userdata)
            turn_ctx.add_message(
                role="system", content=aviso
            )

        # El prefetch no modifica el prompt ni espera dentro del callback: se
        # superpone con el primer LLM. Sólo se habilita para maniobras que no
        # pueden confundirse con "inconsciente pero respira".
        if not _env_bool("RAG_PREFETCH_CRITICAL", False):
            return
        prior = getattr(self.session.userdata, "_rag_prefetch", None)
        if isinstance(prior, _RagPrefetch) and not prior.task.done():
            prior.task.cancel()
        setattr(self.session.userdata, "_rag_prefetch", None)
        category = _prefetch_category(text)
        if category is None:
            return
        canonical_queries: dict[PrefetchCategory, str] = {
            "no_respira": "herido inconsciente que no respira reanimación cardiopulmonar",
            "hemorragia": "control de hemorragias externas",
            "fuego": "accidente vial fuego combustible riesgos inmediatos",
            "atrapado": "persona atrapada accidente vial primeros auxilios",
        }
        task = asyncio.create_task(
            _prefetch_search(canonical_queries[category]),
            name=f"rag-prefetch-{category}",
        )
        setattr(self.session.userdata, "_rag_prefetch", _RagPrefetch(category, task))


server = AgentServer()


@server.rtc_session(agent_name="asistente-emergencias")
async def entrypoint(ctx: agents.JobContext):
    # Todas las líneas de log del job quedan correlacionables por sala.
    ctx.log_context_fields = {"room": ctx.room.name, "job": ctx.job.id}
    logger.info("conectando a la sala %s", ctx.room.name)

    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    stt_model = os.getenv("STT_MODEL", "deepgram/nova-3")
    is_flux = stt_model == "deepgram/flux-general-multi"
    stt_language = os.getenv("STT_LANGUAGE", "multi" if is_flux else "es")
    stt_kwargs = {"eager_eot_threshold": 0.4} if is_flux else {}
    llm_model = os.getenv("LLM_MODEL", "openai/gpt-4.1-mini")
    # Perfil seleccionado tras las corridas locales: reduce el EOU sin cambiar
    # STT, LLM ni voz. Todas las variables siguen permitiendo rollback inmediato.
    endpoint_mode = os.getenv("ENDPOINTING_MODE", "fixed")
    endpoint_min = _env_float("ENDPOINTING_MIN_DELAY", 0.3)
    endpoint_max = _env_float("ENDPOINTING_MAX_DELAY", 2.5)
    preemptive_tts = _env_bool("PREEMPTIVE_TTS", True)
    max_preemptive_speech = _env_float("PREEMPTIVE_MAX_SPEECH_DURATION", 10.0)
    endpointing = {"mode": endpoint_mode, "max_delay": endpoint_max}
    if endpoint_min is not None:
        endpointing["min_delay"] = endpoint_min

    stt = inference.STT(model=stt_model, language=stt_language, extra_kwargs=stt_kwargs)
    llm = inference.LLM(
        model=llm_model,
        extra_kwargs={"temperature": 0.2, "parallel_tool_calls": True},
    )
    tts = inference.TTS(
        model="cartesia/sonic-3.6",
        voice=os.getenv("CARTESIA_VOICE_ID", "826111be-ee28-4c28-bc77-4ecdeae8e8b9"),
        extra_kwargs={"language": "es"},
    )
    recorder = LatencyRecorder(
        room=ctx.room.name,
        job=ctx.job.id,
        config={
            "stt_model": stt_model,
            "stt_language": stt_language,
            "llm_model": llm_model,
            "tts_model": "cartesia/sonic-3.6",
            "endpointing": endpointing,
            "preemptive_tts": preemptive_tts,
            "rag_prefetch_critical": _env_bool("RAG_PREFETCH_CRITICAL", False),
        },
    )
    userdata = TriageState()
    setattr(userdata, "_latency_recorder", recorder)

    session = AgentSession[TriageState](
        userdata=userdata,
        stt=stt,
        llm=llm,
        tts=tts,
        turn_handling={
            **({"turn_detection": "stt"} if is_flux else {}),
            "endpointing": endpointing,
            "interruption": {"min_duration": 0.4, "min_words": 2},
            "preemptive_generation": {
                "preemptive_tts": preemptive_tts,
                "max_speech_duration": max_preemptive_speech,
            },
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
        recorder.record_conversation_item(ev.item)

    # En 1.6.5, EOUMetrics sólo se publica en la sesión y es el evento que
    # entrega el speech_id que correlaciona LLM/TTS/RAG. El evento está marcado
    # deprecado para uso agregado, pero sigue siendo la única API de esta
    # versión que expone estas métricas por componente y por turno.
    @session.on("metrics_collected")
    def _on_metrics(ev):
        recorder.record_component(ev.metrics)

    @session.on("session_usage_updated")
    def _on_usage(ev):
        logger.debug("uso acumulado: %s", ev.usage)

    @session.on("user_state_changed")
    def _on_user_state(ev):
        if ev.new_state == "away" and not session.userdata.derivado:
            session.say("Seguí, te escucho. ¿Cómo va?")

    @session.on("agent_state_changed")
    def _on_agent_state(ev):
        recorder.record_agent_state(ev)

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

    # DB/schema warmup no debe bloquear el primer audio de la llamada. Durante
    # el saludo, el trabajo bloqueante vive en otro thread y el primer RAG ya
    # llega con pool y conexiones preparados.
    warm_retriever = asyncio.create_task(asyncio.to_thread(_get_retriever))
    session.say(SALUDO, allow_interruptions=True)
    recorder.record_startup(time.time())
    retriever = await warm_retriever
    logger.info(
        "config | llm=%s stt=%s(%s) keyterms=%d rerank=%s piso=%s",
        llm_model,
        stt_model,
        stt_language,
        len(KEYTERMS_ES),
        retriever.settings.rerank_model if retriever.settings.rerank_enabled else "off",
        retriever.settings.min_rerank_score
        if retriever.settings.rerank_enabled
        else retriever.settings.min_score,
    )

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

    async def _close_latency() -> None:
        pending = getattr(session.userdata, "_rag_prefetch", None)
        if isinstance(pending, _RagPrefetch) and not pending.task.done():
            pending.task.cancel()
        recorder.close()

    ctx.add_shutdown_callback(_close_latency)


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
                aviso = generar_aviso_critico(senal, session.userdata)
                entrada = f"{query}\n\n[{aviso}]"

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
