"""Tests de agent.py que no necesitan red: qué pasa si el índice no cargó."""

from __future__ import annotations

import asyncio

import pytest

import agent
from livekit.agents import llm
from triage import TriageState


@pytest.fixture
def sin_indice(monkeypatch):
    """Simula que el índice del manual todavía se está cargando."""
    monkeypatch.setattr(agent, "_retriever", None)
    monkeypatch.setattr(agent, "_iniciar_carga", lambda: None)


def test_get_retriever_no_bloquea_si_no_cargo(sin_indice):
    with pytest.raises(agent.RetrieverNoListo):
        agent._get_retriever()


def test_protocolo_critico_sale_igual_sin_indice(sin_indice):
    st = TriageState()
    extra = asyncio.run(agent.contexto_del_turno("el acompañante no respira", st))
    assert extra and "Qué indicar:" in extra and "centro del pecho" in extra
    assert st.derivado


def test_ultima_respuesta_sale_del_historial():
    ctx = llm.ChatContext.empty()
    ctx.add_message(role="assistant", content="¿Estás en un lugar seguro, fuera de la calzada?")
    ctx.add_message(role="user", content="Sí")
    assert agent.ultima_respuesta_de(ctx) == "¿Estás en un lugar seguro, fuera de la calzada?"


def test_si_al_saludo_no_deriva(sin_indice):
    """El bug de producción por voz: «Sí» a «¿Estás en un lugar seguro?» se
    tomaba como confirmación de heridos."""
    st = TriageState()
    asyncio.run(agent.contexto_del_turno("Sí.", st, "¿Estás en un lugar seguro, fuera de la calzada?"))
    assert not st.derivado


def test_si_a_pregunta_de_heridos_deriva(sin_indice):
    st = TriageState()
    asyncio.run(agent.contexto_del_turno("Sí, una persona.", st, "¿Hay alguien herido?"))
    assert st.derivado
