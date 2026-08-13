"""Warm transfer al 911 — Opción A: el 911 entra a la MISMA sala.

Decisión de diseño, tomada a conciencia contra la alternativa del SDK:

`livekit.agents.beta.workflows.WarmTransferTask` implementa el warm transfer
clásico: pone a quien llama en HOLD (`on_enter` arranca hold_audio), marca al
humano en una sala aparte (`<sala>-human-agent`) con una segunda AgentSession,
lo briefea en privado, y recién ahí une las patas con `move_participant`. Eso da
briefing privado, que es lindo, pero deja a la persona sola escuchando música
mientras la escena cambia. En una emergencia ese es el peor momento posible para
que nadie la esté escuchando: si dice "¡ya respira!" o "¡se prendió fuego!",
nadie la oye.

Acá se hace al revés: se marca al 911 como SEGUNDO participante SIP de la misma
sala. Quien llama nunca queda solo, el agente le sigue hablando durante todo el
ring, y el briefing se dice en voz alta. Que la persona lo escuche no molesta, y
de hecho le confirma que la entendiste bien.

La pieza que hace posible "marcar sin dejar de hablar" es `AsyncToolset`: la tool
corre en background y `ctx.update()` va metiendo el progreso en la conversación
mientras el teléfono suena. Sin eso, `wait_until_answered=True` bloquea el
request HTTP durante todo el ring (ver api/sip_service.py:806, que estira el
timeout del cliente hasta ringing_timeout + 2s) y el agente se queda congelado
exactamente cuando más se lo necesita.

Topología de audio, verificada en el SDK (voice/room_io/room_io.py:378, donde
`_on_participant_connected` hace `if self._participant_available_fut.done():
return`): una vez que quien llama queda vinculado, el segundo participante SIP
es ignorado por el input del agente. O sea que el STT sigue escuchando SOLO a
quien llama, y lo que diga el operador del 911 no se transcribe ni llega al LLM.
El TTS en cambio se publica a la sala, así que los dos escuchan al agente. Es
aceptable para esto: el agente acompaña a la persona y le pasa el resumen al
operador, no conversa con el operador.
"""

from __future__ import annotations

import asyncio
import logging
import os

from livekit import api
from livekit.agents import RunContext, ToolError, function_tool, get_job_context
from livekit.agents.llm import ToolFlag
from livekit.agents.llm.async_toolset import AsyncToolset

from triage import TriageState

logger = logging.getLogger("telephony")

IDENTIDAD_OPERADOR = "operador-911"

# Cuánto suena antes de darlo por no atendido.
RINGING_TIMEOUT_S = 30
# Cota de seguridad para que una llamada colgada mal no quede abierta y facturando.
MAX_CALL_DURATION_S = 15 * 60


def _config() -> tuple[str | None, str | None]:
    """Trunk saliente y número destino, si están configurados."""
    return os.getenv("SIP_OUTBOUND_TRUNK_ID"), os.getenv("NUMERO_EMERGENCIAS")


def modo_simulado() -> bool:
    """Si no hay trunk configurado, la derivación se simula en lugar de fallar.

    Esto existe para poder ensayar el flujo completo en local (`agent.py console`)
    sin gastar un peso en telefonía: el agente igual anuncia la derivación, dice
    el resumen en voz alta y marca el estado como derivado. Lo único que no pasa
    es la llamada real.

    Se puede forzar con SIMULAR_DERIVACION=1 incluso teniendo el trunk, para
    ensayar sin hacer sonar un teléfono de verdad.
    """
    if os.getenv("SIMULAR_DERIVACION") == "1":
        return True
    trunk, numero = _config()
    return not (trunk and numero)


@function_tool(flags=ToolFlag.CANCELLABLE | ToolFlag.IGNORE_ON_ENTER, on_duplicate="reject")
async def derivar_a_emergencias(context: RunContext[TriageState]) -> str:
    """Llama al 911 y lo suma a esta misma llamada, sin cortar con la persona.

    Usala cuando ya tengas la ubicación y el estado de los heridos, o antes si
    hay riesgo de vida (no respira, sangra sin parar, atrapado, fuego).
    Mientras el teléfono suena seguí hablándole a la persona: no la dejes en
    silencio. Cuando el operador entre, resumile la situación en voz alta.
    """
    st = context.userdata

    if st.derivado:
        return "Ya derivaste al 911 en esta llamada. Seguí acompañando a la persona."

    # Puerta blanda, que refleja lo que pide el prompt: ubicación Y estado de los
    # heridos antes de derivar. Con riesgo de vida no hay puerta y se deriva ya.
    #
    # Hace falta pedir las dos cosas: con solo exigir ubicación, el agente
    # derivaba al 911 en el primer turno por un roce de chapa, antes de saber si
    # había alguien lastimado.
    if not st.critico():
        if st.ubicacion is None:
            raise ToolError(
                "Todavía no tengo la ubicación. Preguntala antes de derivar: "
                "si se corta la llamada, es el único dato con el que se puede "
                "mandar ayuda."
            )
        if st.heridos is None:
            raise ToolError(
                "Todavía no sé si hay gente lastimada. Preguntá eso antes de "
                "derivar, así el operador sabe qué mandar."
            )

    trunk_id, numero = _config()

    await context.update(
        "Estoy marcando al 911. Decile a la persona que no corte y que seguís "
        "con ella mientras suena."
    )

    if modo_simulado():
        # Ensayo local: se recorre todo el flujo menos la llamada.
        await asyncio.sleep(2.0)  # imita el ring, para probar que el agente sigue hablando
        st.derivado = True
        st.operador_presente = True
        logger.warning(
            "DERIVACIÓN SIMULADA (sin trunk SIP configurado) | estado=%s", st.brief()
        )
        return _instruccion_briefing(st)

    jc = get_job_context()

    pedido = api.CreateSIPParticipantRequest(
        sip_trunk_id=trunk_id,
        sip_call_to=numero,
        # La misma sala: es lo que hace que la persona nunca quede sola.
        room_name=jc.room.name,
        participant_identity=IDENTIDAD_OPERADOR,
        participant_name="Operador 911",
        # Se espera la atención para poder avisar si nadie contesta. Es seguro
        # porque esta tool corre en background dentro de un AsyncToolset.
        wait_until_answered=True,
        # Sin tono de marcado: la persona ya está escuchando al agente y el tono
        # se le superpondría.
        play_dialtone=False,
        krisp_enabled=True,
    )
    # ringing_timeout y max_call_duration son Duration de protobuf: se setean
    # por campo, no se pasan al constructor.
    pedido.ringing_timeout.seconds = RINGING_TIMEOUT_S
    pedido.max_call_duration.seconds = MAX_CALL_DURATION_S

    logger.info(
        "derivando al 911 | sala=%s destino=%s critico=%s estado=%s",
        jc.room.name, numero, st.critico(), st.brief(),
    )

    try:
        info = await jc.api.sip.create_sip_participant(pedido)
    except api.SipCallError as exc:
        # No atendió, ocupado, número mal formado. La persona sigue en línea con
        # el agente, así que esto es recuperable: se le dice y se sigue.
        logger.warning("el 911 no entró a la llamada: %s", exc)
        return (
            "El 911 no atendió. Decile a la persona que seguís con ella y que "
            "lo vas a intentar de nuevo. No cortes."
        )
    except Exception as exc:
        logger.error("falló la derivación al 911: %s", exc)
        raise ToolError(
            "No pude conectar con el 911. Decile a la persona que siga en línea."
        ) from exc

    st.derivado = True
    st.operador_presente = True
    logger.info("911 en la sala | participante=%s call_id=%s",
                info.participant_identity, info.sip_call_id)

    return _instruccion_briefing(st)


def _instruccion_briefing(st: TriageState) -> str:
    """Lo que se le devuelve al modelo para que resuma al operador.

    El resumen se arma desde TriageState, no desde el transcript: el
    INSTRUCTIONS_TEMPLATE del WarmTransferTask del SDK le pide al LLM que resuma
    la conversación, y con el transcript de alguien en pánico eso termina
    inventando nombres de calles.
    """
    # El orden explícito no es redacción, es un arreglo de un fallo medido.
    # Cuando la persona dice todo junto en un turno ("choqué en la ruta 2, hay un
    # señor que no respira"), las tres tools corren en paralelo y la ÚLTIMA salida
    # que lee el modelo es esta. Sin esta línea el modelo obedecía el "no
    # arranques procedimientos nuevos" del final: resumía al operador y se comía
    # las compresiones que acababa de recuperar del manual. O sea, encontraba la
    # maniobra que salva la vida y no la decía. Es la peor falla posible acá.
    primero = ""
    if st.critico():
        primero = (
            "PRIMERO: si todavía no le diste la maniobra que salva la vida, "
            "dásela ahora en una frase corta. Va ANTES del resumen al operador. "
        )
    return (
        primero + "El operador del 911 ya está en la llamada y te escucha. "
        "Resumile la situación en voz alta, usando SOLO estos datos "
        f"confirmados, sin agregar ni deducir nada: {st.brief()} "
        "Si algún dato dice NO CONFIRMADO, decí que no lo tenés. "
        "Después del resumen no arranques procedimientos nuevos: acompañá a la "
        "persona y seguí atento a si la escena cambia."
    )


def toolset() -> AsyncToolset:
    """Toolset de derivación.

    Va a nivel de sesión (no de Agent) para que sea session-scoped: si más
    adelante se agrega un handoff entre agentes, un marcado en curso sobrevive
    la transición en lugar de cancelarse.
    """
    return AsyncToolset(id="derivacion", tools=[derivar_a_emergencias])
