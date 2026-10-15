"""Tests de cómo llega el contexto del turno al LLM: sin red, sin LLM.

Dos problemas que resuelve:
- Todo el contexto quedaba pegado al mensaje en el historial y los avisos de
  turnos viejos seguían ahí aunque ya no valieran. Ahora en el historial
  quedan solo los protocolos; el estado y los avisos van solo a la respuesta.
- Por voz, LiveKit genera la respuesta por adelantado (preemptive) sin pasar
  por on_user_turn_completed y la usaba sin el contexto del turno.
"""

from __future__ import annotations

import asyncio
import time

import pytest

import agent
from livekit.agents import llm
from triage import TriageState


@pytest.fixture(autouse=True)
def sin_indice(monkeypatch):
    monkeypatch.setattr(agent, "_retriever", None)
    monkeypatch.setattr(agent, "_iniciar_carga", lambda: None)


def _conversacion(*mensajes: tuple[str, str]) -> llm.ChatContext:
    ctx = llm.ChatContext.empty()
    for rol, texto in mensajes:
        ctx.add_message(role=rol, content=texto)
    return ctx


def _correr(coro):
    return asyncio.run(coro)


# --- qué queda en el historial ----------------------------------------------------

def test_en_el_historial_quedan_solo_los_protocolos():
    st = TriageState()
    turno = _correr(agent.preparar_turno("le sale mucha sangre de la pierna", st))
    historial = turno.con_protocolos("le sale mucha sangre de la pierna")
    assert "PROTOCOLO DEL MANUAL (hemorragia)" in historial
    assert "Estado de la llamada" not in historial
    assert "Respondé con UNA indicación" not in historial
    # Lo que va a esta respuesta sí lo tiene todo.
    assert "Estado de la llamada" in turno.texto_directivas()


def test_sin_protocolo_el_historial_queda_igual():
    st = TriageState()
    turno = _correr(agent.preparar_turno("Sí, estoy a salvo.", st))
    assert turno.con_protocolos("Sí, estoy a salvo.") == "Sí, estoy a salvo."
    assert "¿Hay alguien lastimado?" in turno.texto_directivas()


# --- estado actual ------------------------------------------------------------------

def test_estado_con_paro_y_rcp():
    st = TriageState()
    _correr(agent.preparar_turno("el acompañante no respira", st))
    estado = agent.estado_actual(st)
    assert "911: ya avisado" in estado
    assert "Respira: no" in estado
    assert "RCP en curso" in estado
    assert "rcp" in estado


def test_estado_inconsciente_sin_saber_si_respira_prohibe_compresiones():
    st = TriageState()
    _correr(agent.preparar_turno("está inconsciente", st))
    assert "PROHIBIDO indicar compresiones" in agent.estado_actual(st)
    _correr(agent.preparar_turno("Sí, respira.", st))
    assert "PROHIBIDO" not in agent.estado_actual(st)


def test_despierto_no_pregunta_si_respira():
    st = TriageState(heridos="un herido", consciente=True)
    assert "Herido despierto: sí (entonces respira)" in agent.estado_actual(st)
    # Sin saber si está despierto, la respiración no se menciona todavía.
    assert "Respira" not in agent.estado_actual(TriageState(heridos="un herido"))


def test_sin_acceso_sigue_valiendo_en_los_turnos_siguientes():
    """Antes el aviso sobrevivía porque quedaba en el historial; ahora es estado."""
    st = TriageState()
    _correr(agent.preparar_turno("está atrapado en el auto y no lo veo", st))
    segundo = _correr(agent.preparar_turno("sigue igual", st, "Quedate a resguardo."))
    assert "NO puede ver ni llegar al herido" in segundo.texto_directivas()
    assert "Cerrá con UNA pregunta" not in segundo.texto_directivas()
    tercero = _correr(agent.preparar_turno("ya llegué, ahora lo veo", st))
    assert "NO puede ver ni llegar" not in tercero.texto_directivas()


# --- con_contexto -------------------------------------------------------------------

def test_con_contexto_no_toca_el_historial():
    ctx = _conversacion(("assistant", "¿Hay alguien lastimado?"), ("user", "sí, sangra mucho"))
    turno = agent.Turno(protocolos=["PROTOCOLO X"], directivas=["Estado Y"])
    nuevo = agent.con_contexto(ctx, turno)
    assert ctx.items[-1].text_content == "sí, sangra mucho"
    assert "PROTOCOLO X" in nuevo.items[-1].text_content
    assert "Estado Y" in nuevo.items[-1].text_content


def test_con_contexto_no_duplica_protocolos_ya_guardados():
    turno = agent.Turno(protocolos=["PROTOCOLO X"], directivas=["Estado Y"])
    ctx = _conversacion(("user", turno.con_protocolos("sí, sangra mucho")))
    nuevo = agent.con_contexto(ctx, turno)
    assert nuevo.items[-1].text_content.count("PROTOCOLO X") == 1


# --- qué turno le toca a cada respuesta --------------------------------------------

def test_voz_turno_confirmado():
    st = TriageState()
    turnos = agent.TurnosConfirmados()
    ctx = _conversacion(("assistant", "¿Hay alguien lastimado?"), ("user", "no respira"))

    async def caso():
        confirmado = await turnos.confirmar("no respira", st, "¿Hay alguien lastimado?", ctx.items[-1].id)
        turno, estado = await turnos.para_respuesta(ctx, st)
        return confirmado, turno, estado

    confirmado, turno, estado = _correr(caso())
    assert turno is confirmado and estado is st
    assert len(st.dichos) == 1  # no se procesó dos veces


def test_respuesta_anticipada_trae_el_contexto_sin_tocar_el_estado():
    """El bug de producción: la respuesta anticipada salía sin aviso crítico."""
    st = TriageState()
    turnos = agent.TurnosConfirmados()
    ctx = _conversacion(("assistant", "Fijate si se le mueve el pecho. ¿Respira?"), ("user", "No, no respira."))

    async def caso():
        anticipado, estado = await turnos.para_respuesta(ctx, st)
        assert not st.derivado and not st.dichos  # el estado real no cambió todavía
        assert estado.derivado  # la copia sí: el aviso del 911 sale en esa respuesta
        confirmado = await turnos.confirmar("No, no respira.", st, ctx.items[0].text_content, "otro-id")
        # Si la respuesta anticipada llama una tool, vuelve a pasar por llm_node.
        despues, estado_despues = await turnos.para_respuesta(ctx, st)
        return anticipado, confirmado, despues, estado_despues

    anticipado, confirmado, despues, estado_despues = _correr(caso())
    assert "NO RESPIRA" in anticipado.texto_directivas()
    assert anticipado.completo() == confirmado.completo()  # determinístico
    assert despues is confirmado and estado_despues is st
    assert st.derivado and len(st.dichos) == 1


def test_respuesta_anticipada_que_llega_tarde_usa_el_turno_confirmado():
    """Si la confirmación empezó antes que el LLM de la respuesta anticipada,
    no se vuelve a procesar el turno sobre el estado ya actualizado."""
    st = TriageState()
    turnos = agent.TurnosConfirmados()
    ctx = _conversacion(("assistant", "¿Hay alguien lastimado?"))
    mensaje = ctx.add_message(role="user", content="está inconsciente", created_at=time.time() - 1)

    async def caso():
        confirmado = await turnos.confirmar("está inconsciente", st, "¿Hay alguien lastimado?", "final-id")
        turno, estado = await turnos.para_respuesta(ctx, st)
        return confirmado, turno, estado

    confirmado, turno, estado = _correr(caso())
    assert turno is confirmado and estado is st
    assert mensaje.id in turnos._por_mensaje
    assert len(st.dichos) == 1
    assert "INCONSCIENTE" in turno.texto_directivas()


def test_chat_turno_para_el_proximo_mensaje():
    st = TriageState()
    turnos = agent.TurnosConfirmados()
    ctx = _conversacion(("assistant", "¿Hay alguien lastimado?"))

    async def caso():
        confirmado = await turnos.confirmar("hay un herido", st, "¿Hay alguien lastimado?")
        ctx.add_message(role="user", content=confirmado.con_protocolos("hay un herido"))
        primero, _ = await turnos.para_respuesta(ctx, st)
        segundo, _ = await turnos.para_respuesta(ctx, st)  # paso de tool
        return confirmado, primero, segundo

    confirmado, primero, segundo = _correr(caso())
    assert primero is confirmado and segundo is confirmado
    assert len(st.dichos) == 1


def test_directivas_viejas_no_llegan_al_turno_siguiente():
    """Lo que se le dijo al modelo en un turno no aparece en el siguiente."""
    st = TriageState()
    turnos = agent.TurnosConfirmados()
    ctx = _conversacion(("assistant", "¿Estás en un lugar seguro?"))

    async def turno_de_chat(texto: str, respuesta: str) -> str:
        turno = await turnos.confirmar(texto, st, agent.ultima_respuesta_de(ctx))
        ctx.add_message(role="user", content=turno.con_protocolos(texto))
        t, _ = await turnos.para_respuesta(ctx, st)
        enviado = agent.con_contexto(ctx, t)
        ctx.add_message(role="assistant", content=respuesta)
        return "\n".join(m.text_content or "" for m in enviado.messages())

    async def caso():
        await turno_de_chat("Sí.", "¿Hay alguien lastimado?")
        return await turno_de_chat("Sí, está inconsciente.", "Fijate si se le mueve el pecho. ¿Respira?")

    enviado = _correr(caso())
    # «Todavía no se sabe si hay heridos» era del primer turno: ya no vale.
    assert "Todavía no se sabe si hay heridos" not in enviado
    assert enviado.count("Estado de la llamada") == 1
