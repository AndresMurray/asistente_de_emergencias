"""Tests del metrónomo de RCP y de cuándo puede sonar: sin red, sin sala."""

from __future__ import annotations

import asyncio
import itertools

import numpy as np
import pytest

import agent
from metronomo import SAMPLE_RATE, Metronomo, bloques, clic, pide_apagar, pide_prender
from triage import TriageState, llego_la_ayuda, procesar_turno_usuario, rcp_en_curso


def _inicios_de_clic(bpm: float, segundos: float) -> np.ndarray:
    n_bloques = int(segundos * 1000 / 20)
    audio = np.concatenate(list(itertools.islice(bloques(bpm), n_bloques)))
    # Dentro de un clic el seno pasa por cero cada medio ciclo: un clic nuevo
    # es una muestra no nula después de un silencio largo (no de un cruce).
    no_nulas = np.flatnonzero(audio)
    nuevo = np.concatenate([[True], np.diff(no_nulas) > SAMPLE_RATE // 100])
    return no_nulas[nuevo]


@pytest.mark.parametrize("bpm", [100, 110, 120])
def test_ritmo_exacto_sin_deriva(bpm):
    inicios = _inicios_de_clic(bpm, 30)
    periodo = SAMPLE_RATE * 60 / bpm
    esperados = np.round(np.arange(len(inicios)) * periodo)
    # +1 muestra: el seno arranca en 0, así que la primera no nula es la siguiente.
    assert np.all(np.abs(inicios - esperados) <= 1)
    assert len(inicios) == pytest.approx(30 * bpm / 60, abs=1)


def test_clic_es_corto_y_no_satura():
    golpe = clic()
    assert len(golpe) < 0.05 * SAMPLE_RATE
    assert np.abs(golpe).max() < 32767


def test_metronomo_sin_sala_no_falla():
    m = Metronomo()
    assert not m.iniciar()
    assert not m.activo
    assert not m.detener()
    asyncio.run(m.aclose())


# --- cuándo hay RCP en curso ------------------------------------------------------

@pytest.fixture
def sin_indice(monkeypatch):
    monkeypatch.setattr(agent, "_retriever", None)
    monkeypatch.setattr(agent, "_iniciar_carga", lambda: None)


def test_inconsciente_sin_verificar_no_es_rcp(sin_indice):
    """Aunque pregunte por compresiones, sin confirmar que no respira no suena."""
    st = TriageState()
    asyncio.run(agent.contexto_del_turno("está inconsciente, no reacciona", st))
    asyncio.run(agent.contexto_del_turno("¿le hago compresiones?", st))
    assert st.respira is None
    assert not rcp_en_curso(st)


def test_paro_confirmado_es_rcp_y_se_corta_si_respira(sin_indice):
    st = TriageState()
    asyncio.run(agent.contexto_del_turno("el acompañante no respira", st))
    assert rcp_en_curso(st)
    asyncio.run(agent.contexto_del_turno("¡volvió a respirar!", st))
    assert not rcp_en_curso(st)


def test_rcp_se_corta_cuando_llega_la_ayuda(sin_indice):
    st = TriageState()
    asyncio.run(agent.contexto_del_turno("no respira", st))
    extra = asyncio.run(agent.contexto_del_turno("llegó la ambulancia", st))
    assert st.ayuda_llego and not rcp_en_curso(st)
    assert "profesionales" in extra


def test_paro_solo_por_estado_sin_protocolo_no_es_rcp():
    """respira=False sin que se haya dado la indicación de comprimir todavía."""
    st = TriageState()
    procesar_turno_usuario("no respira", st)
    assert st.respira is False
    assert not rcp_en_curso(st)


@pytest.mark.parametrize("texto,esperado", [
    ("Llegó la ambulancia", True),
    ("ya llegaron los bomberos", True),
    ("la ambulancia ya está acá", True),
    ("ya está acá la ambulancia", True),
    ("todavía no llegó la ambulancia", False),
    ("¿cuándo llega la ambulancia?", False),
    ("llegó un auto y se fue", False),
])
def test_llego_la_ayuda(texto, esperado):
    assert llego_la_ayuda(texto) is esperado


@pytest.mark.parametrize("texto,apagar,prender", [
    ("pará el sonido", True, False),
    ("sacá ese ruido que me pone nervioso", True, False),
    ("apagá el metrónomo", True, False),
    ("poné el sonido de nuevo", False, True),
    ("volvé a poner el ritmo", False, True),
    ("sigo comprimiendo", False, False),
    ("no paro, sigo", False, False),
])
def test_pedidos_de_apagar_y_prender(texto, apagar, prender):
    assert pide_apagar(texto) is apagar
    assert pide_prender(texto) is prender


def test_pedir_sacar_el_sonido_lo_silencia_y_se_puede_volver(sin_indice):
    st = TriageState()
    asyncio.run(agent.contexto_del_turno("no respira", st))
    asyncio.run(agent.contexto_del_turno("pará el sonido, me pone nervioso", st))
    assert st.metronomo_silenciado and rcp_en_curso(st)
    asyncio.run(agent.contexto_del_turno("poné el sonido de nuevo", st))
    assert not st.metronomo_silenciado


def test_si_respira_corta_la_rcp(sin_indice):
    st = TriageState()
    asyncio.run(agent.contexto_del_turno("no respira", st))
    asyncio.run(agent.contexto_del_turno("Sí, respira.", st))
    assert st.respira is True and not rcp_en_curso(st)


def test_tope_de_tiempo_por_env(monkeypatch):
    monkeypatch.setenv("METRONOMO_MAX_MIN", "2")
    assert Metronomo().max_s == 120
