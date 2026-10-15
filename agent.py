import asyncio
import json
import logging
import os
import random
import re
import threading
import time
from collections.abc import Callable

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

from livekit import agents, rtc  # type: ignore
from livekit.agents import (  # type: ignore
    Agent,
    AgentServer,
    AgentSession,
    JobProcess,
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

from habla import NormalizadorStream, aplicar_aviso_911
from metronomo import Metronomo, pide_apagar, pide_prender
from prompts import KEYTERMS_ES, SALUDO, SYSTEM_INSTRUCTIONS
from protocolos import TEMAS, detectar_temas, respira_positivo, tema_de_consulta
from rag import RetrievalResult, Retriever, load_settings
from triage import (
    TriageState,
    confirma_heridos,
    derivar_automatico,
    generar_aviso_critico,
    hay_herido,
    llego_la_ayuda,
    niega_heridos,
    procesar_turno_usuario,
    rcp_en_curso,
    registrar_datos_escena,
    sin_acceso_al_herido,
)

load_dotenv(".env.local")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("emergency-agent")

# Un retriever por proceso: adentro tiene el pool de conexiones, el índice en
# memoria y el caché de consultas, y se comparte entre los jobs del proceso.
#
# Se carga en un hilo y NUNCA dentro de un turno: si Supabase está lento (se
# vio una carga del índice colgada más de 25 s), el proceso igual arranca y
# atiende con los textos de respaldo de protocolos.py hasta que el índice esté.
_retriever: Retriever | None = None
_carga: threading.Thread | None = None
_carga_lock = threading.Lock()
_PREWARM_ESPERA_S = 15.0


class RetrieverNoListo(RuntimeError):
    """El índice todavía se está cargando (o la base no respondió)."""


def _cargar_retriever() -> None:
    global _retriever
    try:
        r = Retriever()
        r.connect()
        _retriever = r  # se publica recién cuando está listo
    except Exception:
        logger.exception("no pude cargar el retriever; sigo con los textos de respaldo")


def _iniciar_carga() -> threading.Thread:
    global _carga
    with _carga_lock:
        if _carga is None or not _carga.is_alive():
            _carga = threading.Thread(target=_cargar_retriever, name="carga-retriever", daemon=True)
            _carga.start()
        return _carga


def _get_retriever() -> Retriever:
    """El retriever si ya está cargado. Si no, dispara la carga en segundo plano
    y levanta RetrieverNoListo: quien llama usa el texto de respaldo en lugar
    de dejar a la persona esperando."""
    if _retriever is not None:
        return _retriever
    _iniciar_carga()
    raise RetrieverNoListo("el índice del manual todavía se está cargando")


def prewarm(proc: JobProcess | None) -> None:
    """Carga base, índice y caché ANTES de que entre una llamada, con un tope de
    espera para no trabar el arranque del proceso (LiveKit lo corta a los 30 s)."""
    _iniciar_carga().join(timeout=_PREWARM_ESPERA_S)
    if _retriever is None:
        logger.warning("prewarm: el índice sigue cargando; mientras tanto, textos de respaldo")


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


# Frases de espera profesionales, serias y empáticas para emergencias viales.
# Transmiten control, acompañan y evitan sonar informales o repetitivas.
FRASES_ESPERA_EMERGENCIA = [
    "Dame un segundo, estoy con vos.",
    "Un momento, ya te confirmo el paso exacto.",
    "Un instante, estoy verificando el protocolo.",
    "Dame un segundo, ya te indico cómo seguir.",
    "Un momento, quedate conmigo.",
]


def _elegir_frase_espera(userdata: TriageState | None = None) -> str:
    """Elige una frase de espera profesional evitando repetir la última usada."""
    last_idx = getattr(userdata, "_last_filler_idx", -1) if userdata else -1
    candidatos = [i for i in range(len(FRASES_ESPERA_EMERGENCIA)) if i != last_idx]
    idx = random.choice(candidatos)
    if userdata:
        setattr(userdata, "_last_filler_idx", idx)
    return FRASES_ESPERA_EMERGENCIA[idx]


@function_tool(flags=ToolFlag.IGNORE_ON_ENTER, on_duplicate="replace")
async def buscar_protocolo(context: RunContext, query: str) -> str:
    """Busca en el manual de primeros auxilios los fragmentos relevantes.

    Llamala cuando necesites una maniobra que NO esté ya en el contexto (si ya
    tenés el protocolo adjunto en el mensaje de la persona, no la llames).
    Reformulá lo que dijo la persona con palabras del manual: "no respira" se
    busca como "herido inconsciente que no respira reanimación cardiopulmonar";
    "se está desangrando" como "control de hemorragias externas".
    NUNCA la llames más de una vez en el mismo turno ni repitas la misma consulta.
    """
    st: TriageState = context.userdata
    q_norm = query.strip().lower()
    if st.ultima_consulta == q_norm:
        logger.warning("buscar_protocolo: consulta duplicada en el mismo turno: '%s'", query)
        return (
            f"Ya consultaste el manual para «{query}» en este turno y los fragmentos están arriba. "
            "Formulá tu respuesta ahora."
        )
    st.ultima_consulta = q_norm

    # Si la consulta es claramente de un tema crítico, se usa la consulta
    # canónica: su resultado está precalculado y sale en 0 ms.
    tema = tema_de_consulta(query)
    consulta = tema.consulta if tema else query

    t0 = time.monotonic()
    async with context.with_filler(_elegir_frase_espera(st), delay=0.6, max_steps=1):
        try:
            result = await _get_retriever().search(consulta)
        except RetrieverNoListo as exc:
            result = RetrievalResult(status="error", error=str(exc))
    elapsed = int((time.monotonic() - t0) * 1000)

    usa_respaldo = result.status != "ok" and tema is not None
    st.tool_calls.append({
        "tool": "buscar_protocolo",
        "args": {"query": query, "consulta_usada": consulta},
        "origen": "respaldo" if usa_respaldo else result.modo,
        "total_latency_ms": elapsed,
        "chunks_found": len(result.fragments),
        "context_for_llm": (
            result.para_llm() if result.status == "ok" else tema.respaldo if usa_respaldo else None
        ),
        **result.to_debug_dict(),
    })

    if result.status == "ok":
        return result.para_llm()

    # Para los temas críticos nunca se contesta "no está en el manual" ni
    # "perdí el acceso": hay texto de respaldo redactado del mismo manual.
    if usa_respaldo:
        logger.warning("buscar_protocolo: %s (%s), uso respaldo de «%s»", result.status, result.error, tema.clave)
        return tema.respaldo

    if result.status == "error":
        raise ToolError(
            "La búsqueda en el manual falló por un problema técnico. "
            f"Motivo: {result.error}"
        )
    return (
        "El manual no tiene nada relevante para esa consulta. "
        "No inventes un procedimiento: decí que no está en tu manual y seguí acompañando."
    )


# --- contexto determinístico de cada turno -----------------------------------

_MAX_TEMAS_POR_TURNO = 2

# «¿le saco el casco?», «tengo que mover el auto». Deepgram puntúa, pero por
# las dudas también se miran las formas típicas de pedir una indicación.
_PREGUNTA = re.compile(
    r"\?|\b(tengo que|debo|hago|le saco|lo saco|la saco|lo muevo|la muevo|"
    r"qué hago|que hago|cómo|como hago|está bien|esta bien)\b",
    re.IGNORECASE,
)


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


async def contexto_del_turno(
    texto: str, st: TriageState, ultima_respuesta: str | None = None
) -> str | None:
    """Lo que el sistema le agrega al turno ANTES de llamar al LLM.

    Es el mismo para voz, chat y los scripts de prueba. Hace tres cosas sin
    depender de que el modelo llame una tool:
    1. detecta riesgo de vida y deriva al 911 (triage.procesar_turno_usuario);
    2. adjunta el protocolo del manual de los temas mencionados (precalculado:
       0 ms), así el modelo responde en UNA pasada en vez de llamar a
       buscar_protocolo y esperar otra vuelta;
    3. marca situaciones que el modelo manejaba mal (no ve al herido, pide RCP
       sin saber si respira).
    """
    st.ultima_consulta = None
    if ultima_respuesta is not None:
        st.ultima_respuesta = ultima_respuesta
    st.pregunta_pendiente = bool(_PREGUNTA.search(texto))
    partes: list[str] = []

    senal = procesar_turno_usuario(texto, st)
    herido_nuevo = False
    if not senal and not st.derivado and hay_herido(texto):
        # Herido sin riesgo de vida explícito: igual se deriva (y el sistema le
        # dice a la persona que la ayuda va en camino).
        if st.heridos is None:
            st.heridos = texto
        derivar_automatico(st, motivo="herido")
        herido_nuevo = True
    elif not senal and not st.derivado and confirma_heridos(texto, st.ultima_respuesta):
        # «sí, una persona» a «¿Hay alguien herido?»: no dice «herido», pero lo
        # confirma. Antes dependía de que el modelo llamara a la tool, y en
        # producción no la llamó: no derivaba y preguntaba «¿cuántos heridos?».
        st.heridos = texto
        derivar_automatico(st, motivo="heridos confirmados")
        herido_nuevo = True
    elif st.heridos is None and niega_heridos(texto):
        st.heridos = texto
    if herido_nuevo:
        partes.append(
            f"Ya está confirmado que hay un herido («{texto}»): no vuelvas a preguntar si hay "
            "heridos ni cuántos. Lo próximo es saber si el herido está despierto y responde "
            "(salvo que la persona te haya preguntado algo: eso primero)."
        )
    if senal:
        partes.append(generar_aviso_critico(senal, st))
        # Lo esencial (no respira, inconsciente, atrapado) ya quedó registrado y
        # el 911 ya fue avisado: registrar_datos_escena acá solo agrega otra
        # vuelta al LLM (~1 s) en el turno donde más importa la velocidad.
        partes.append("Esto ya quedó registrado: respondé directo, SIN llamar herramientas en este turno.")

    if not st.ayuda_llego and llego_la_ayuda(texto):
        st.ayuda_llego = True
        # En los ensayos, con un «hagan cargo» a secas, el modelo decía
        # «detené las compresiones» apenas llegaba la ambulancia: no se frena
        # hasta que alguien toma el lugar.
        aviso_ayuda = "LLEGÓ LA AYUDA: que deje que los profesionales se hagan cargo y les cuente lo que pasó."
        if st.respira is False:
            aviso_ayuda += (
                " NO le digas que deje de comprimir: que siga hasta que un profesional le pida el lugar."
            )
        partes.append(aviso_ayuda)

    if pide_apagar(texto) and not st.metronomo_silenciado:
        st.metronomo_silenciado = True
        partes.append(
            "La persona pidió sacar el sonido del ritmo: ya se apagó. Confirmáselo en pocas "
            "palabras y, si está comprimiendo, que siga al mismo ritmo."
        )
    elif pide_prender(texto) and st.metronomo_silenciado:
        st.metronomo_silenciado = False
        partes.append("La persona pidió volver a escuchar el ritmo: ya vuelve a sonar. Decile que lo siga.")

    inconsciente = st.consciente is False or "inconsciencia" in st.alertas
    en_rcp = rcp_en_curso(st)
    if respira_positivo(texto) and (st.respira is False or (inconsciente and st.respira is None)):
        # También cubre «¡volvió a respirar!» en plena RCP: se dejan las
        # compresiones y pasa al protocolo del inconsciente que respira.
        if st.respira is False:
            partes.append("VOLVIÓ A RESPIRAR: que deje de comprimir y vigile que siga respirando.")
        st.respira = True
        en_rcp = False
    elif en_rcp:
        # En las pruebas, ante «ya hice las compresiones, ¿ahora qué?», el
        # modelo pedía revisar si respiraba: eso frena la RCP.
        # El ejemplo de cierre rota: con uno fijo, el modelo terminaba cada
        # turno de RCP con la misma frase.
        cierre_rcp = _CIERRES_RCP[st.seguimientos_usados.get("rcp", 0) % len(_CIERRES_RCP)]
        st.seguimientos_usados["rcp"] = st.seguimientos_usados.get("rcp", 0) + 1
        aviso_rcp = (
            "Está haciendo RCP: que siga comprimiendo sin parar, dos veces por segundo, hasta que "
            "llegue la ayuda o la persona empiece a respirar. No le pidas que frene ni que revise nada. "
            f"No le hagas preguntas: cerrá invitándola a avisarte, por ejemplo «{cierre_rcp}»."
        )
        if st.metronomo_activo:
            aviso_rcp += " Ya suena un sonido que marca el ritmo: decile que siga ese sonido."
        partes.append(aviso_rcp)

    temas = detectar_temas(texto)
    repetidos = [t for t in temas if t in st.temas_inyectados]
    if repetidos:
        # «le scao el casco» (con error de tipeo, sin signo de pregunta) después
        # de haber hablado del casco: es una pregunta aunque no lo parezca, y el
        # agente respondía repitiendo su pregunta anterior.
        st.pregunta_pendiente = True
        partes.append(
            f"La persona vuelve a preguntar por {', '.join(repetidos)}: respondé eso directo, "
            "con el protocolo que ya tenés, antes que cualquier otra cosa."
        )
    if st.respira is False:
        temas.insert(0, "rcp")
    elif "rcp" in temas:
        # Pregunta por RCP sin paro confirmado: nunca adjuntar el protocolo de
        # compresiones a ciegas (si respira, comprimir le hace daño).
        temas.remove("rcp")
        partes.append(
            "Todavía no está confirmado que el herido NO respire: antes de cualquier "
            "compresión, pedí que se fije si se le mueve el pecho."
        )
    if inconsciente and st.respira is True:
        temas.insert(0, "inconsciente_respira")
    if "hemorragia" in temas and ("objeto_clavado" in temas or "objeto_clavado" in st.temas_inyectados):
        # El protocolo de hemorragia dice «apretar directo sobre el punto que
        # sangra»: con un objeto clavado eso lo empuja. El de objeto clavado ya
        # dice cómo tapar el sangrado.
        temas.remove("hemorragia")

    if st.pregunta_pendiente:
        # En las pruebas el modelo ignoraba «¿le saco el casco?» para seguir con
        # sus preguntas de triage, aun con el protocolo adjunto.
        partes.append(
            "La persona te hizo una pregunta: respondela en ESTE turno, con el protocolo "
            "si lo hay, antes de preguntar cualquier otra cosa."
        )

    if sin_acceso_al_herido(texto):
        partes.append(
            "La persona NO puede ver ni llegar al herido: no le pidas que revise nada del "
            "herido. Que se quede a resguardo, fuera de la calzada, y te avise si ve algún cambio."
        )

    nuevos = [t for t in dict.fromkeys(temas) if t not in st.temas_inyectados]
    st.indicacion_pendiente = bool(nuevos)
    if nuevos:
        st.tema_activo = nuevos[0]
    for clave in nuevos[:_MAX_TEMAS_POR_TURNO]:
        tema = TEMAS[clave]
        # Primero el resumen verificado (redactado del manual para este caso) y
        # después los fragmentos como respaldo. Solo con los fragmentos, el
        # modelo tomaba el primero al pie de la letra: ante un inconsciente
        # que respira indicaba la posición lateral, cuando el manual dice que en
        # un accidente de tránsito no hay que moverlo salvo que vomite.
        fragmentos = ""
        res = None
        t0 = time.monotonic()
        try:
            res = await _get_retriever().search(tema.consulta)
            if res.status == "ok":
                fragmentos = res.para_llm()
        except RetrieverNoListo:
            logger.warning("prefetch de «%s»: índice cargando, uso solo el resumen", clave)
        except Exception:
            logger.exception("prefetch de «%s» falló, uso solo el resumen", clave)
        elapsed = int((time.monotonic() - t0) * 1000)
        st.temas_inyectados.add(clave)
        bloque = (
            f"PROTOCOLO DEL MANUAL ({clave}), ya consultado, no llames buscar_protocolo para esto.\n"
            f"Qué indicar: {tema.respaldo}"
        )
        if fragmentos:
            bloque += f"\nFragmentos del manual:\n{fragmentos}"
        partes.append(bloque)

        # Mismo formato que buscar_protocolo, para que el panel de debug del
        # frontend muestre fragmentos, scores y el contexto que recibió el LLM.
        debug = res.to_debug_dict() if res else {"status": "error", "error": "retriever no disponible", "fragments": []}
        st.tool_calls.append({
            "tool": "prefetch_protocolo",
            "args": {"tema": clave, "query": tema.consulta},
            "origen": debug.get("modo") if fragmentos else "respaldo",
            "total_latency_ms": elapsed,
            "chunks_found": len(debug["fragments"]),
            "context_for_llm": bloque,
            **debug,
        })

    if not partes and st.heridos is None and not st.derivado:
        # Al principio de la llamada el modelo juntaba dos preguntas («¿Qué pasó
        # y cuántas personas resultaron heridas?»). Lo que importa primero es
        # si hay heridos: una sola pregunta.
        partes.append(
            "Todavía no se sabe si hay heridos: preguntá solo eso, con una sola pregunta "
            "corta («¿Hay alguien lastimado?»)."
        )
    cierre = _guia_de_cierre(texto, temas, nuevos, st, en_rcp)
    if not partes and not cierre:
        return None
    if partes:
        # Con el protocolo completo a mano el modelo tendía a recitarlo entero
        # (50+ palabras): por teléfono eso no se retiene.
        partes.append(
            "Respondé con UNA indicación corta (máximo dieciocho palabras) y la pregunta de "
            "cierre si corresponde; lo demás, en los turnos siguientes."
        )
    return "[Contexto del sistema, no lo leas en voz alta]\n" + "\n\n".join(partes + cierre)


_CIERRES_RCP = (
    "Avisame si se mueve o empieza a respirar.",
    "Si ves que respira, decímelo enseguida.",
    "Vas bien, avisame si notás algún cambio.",
)

_ULTIMA_PREGUNTA = re.compile(r"¿[^¿?]+\?")


def _ultima_pregunta(texto: str) -> str | None:
    preguntas = _ULTIMA_PREGUNTA.findall(texto or "")
    return preguntas[-1] if preguntas else None


def _pregunta_de_seguimiento(temas: list[str], nuevos: list[str], st: TriageState) -> str | None:
    """La próxima pregunta de seguimiento sin usar del tema más relevante.

    Primero los temas recién adjuntados, después los mencionados en el turno y
    por último el último tema tratado (la persona dice «listo, ya aprieto» sin
    nombrar el tema). Cada pregunta se sugiere una sola vez por llamada: después
    el modelo cierra con sus palabras en lugar de repetir siempre la misma."""
    for clave in dict.fromkeys([*nuevos, *temas, st.tema_activo]):
        if clave is None:
            continue
        preguntas = TEMAS[clave].seguimiento
        usadas = st.seguimientos_usados.get(clave, 0)
        if usadas < len(preguntas):
            st.seguimientos_usados[clave] = usadas + 1
            return preguntas[usadas]
    return None


def _guia_de_cierre(
    texto: str, temas: list[str], nuevos: list[str], st: TriageState, en_rcp: bool
) -> list[str]:
    """Cómo cerrar el turno para que la conversación siga.

    Librado al prompt, el modelo cerraba casi todo con «¿Lo pudiste hacer?»,
    que no le sirve para decidir el paso siguiente. Acá se le sugiere la
    observación que importa para el tema en curso («¿Sigue saliendo sangre?»)
    y se le recuerda su última pregunta para que no la repita igual."""
    if st.respira is False and not st.ayuda_llego:
        if en_rcp:
            return []  # el aviso de RCP ya dice cómo cerrar sin preguntar
        return [
            "No cierres con una pregunta: que empiece a comprimir ya y te avise si se mueve "
            "o empieza a respirar."
        ]

    cierre: list[str] = []
    if not sin_acceso_al_herido(texto):
        if sugerida := _pregunta_de_seguimiento(temas, nuevos, st):
            cierre.append(
                f"Cerrá con UNA pregunta que te diga si la indicación funcionó, por ejemplo "
                f"«{sugerida}». No uses «¿Pudiste?» si hay algo más útil para observar."
            )
    if previa := _ultima_pregunta(st.ultima_respuesta):
        cierre.append(f"Tu última pregunta fue «{previa}»: no la repitas igual.")
    return cierre


class Assistant(Agent):
    def __init__(self, al_actualizar_estado: Callable[[], None] | None = None) -> None:
        super().__init__(
            instructions=SYSTEM_INSTRUCTIONS,
            tools=[buscar_protocolo, registrar_datos_escena],
        )
        # Se llama apenas el turno actualizó el estado de triage, antes del LLM
        # (entrypoint lo usa para apagar el metrónomo si volvió a respirar).
        self._al_actualizar_estado = al_actualizar_estado

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """Camino de audio: mismo contexto determinístico que el chat.

        Se agrega al mensaje del usuario (no a turn_ctx): lo que se agrega a
        turn_ctx vale solo para este turno, y el aviso de riesgo o el protocolo
        desaparecían en el turno siguiente."""
        extra = await contexto_del_turno(
            new_message.text_content or "", self.session.userdata, ultima_respuesta_de(turn_ctx)
        )
        if extra:
            new_message.content.append(extra)
        if self._al_actualizar_estado is not None:
            self._al_actualizar_estado()

    async def llm_node(self, chat_ctx, tools, model_settings: ModelSettings):
        """Corrige el texto antes de hablarlo (ver habla.py): jerga, voseo y el
        aviso «Ya estás geolocalizado y la ayuda va en camino.», que lo pone el
        sistema una sola vez cuando se derivó al 911."""
        st: TriageState = self.session.userdata
        norm = NormalizadorStream()

        def salida(texto: str) -> str:
            return aplicar_aviso_911(texto, st) if texto else texto

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

FRASE_FALLA_LLM = "Perdón, se me cortó un momento. Seguí con lo que estabas haciendo y repetime lo último."

FRASE_INICIO_METRONOMO = "Comprimí al ritmo de este sonido, sin parar."
FRASE_FIN_METRONOMO = (
    "Voy a sacar el sonido. Si seguís comprimiendo, mantené el mismo ritmo. "
    "Si querés que vuelva, pedime que ponga el sonido."
)

FRASES_ALIENTO_RCP = [
    "Vas muy bien, seguí al ritmo del sonido.",
    "No pares, la ayuda ya viene en camino.",
    "Fuerte y parejo, seguí el sonido.",
]


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

    retriever = _retriever
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

            extra = await contexto_del_turno(query, session.userdata, ultima_respuesta_de(session.history))
            entrada = f"{query}\n\n{extra}" if extra else query

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
                ajustes = _retriever.settings if _retriever is not None else load_settings()

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
                        "indice_cargado": _retriever is not None,
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

