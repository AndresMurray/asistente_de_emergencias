"""Tests de las negaciones: sin red, sin LLM.

Antes la detección buscaba palabras sueltas y la respuesta natural a la propia
pregunta del agente («¿Hay fuego o humo cerca?» → «No, no hay fuego ni humo»)
disparaba la alerta de fuego y derivaba al 911. Lo mismo con «No está
inconsciente, me habla», «No sangra» o «El celular no responde».

La regla ante la duda es la contraria: perder un «no respira» real es peor que
una falsa alarma, así que también se prueba que lo afirmado se siga detectando.
"""

from __future__ import annotations

import asyncio

import pytest

import agent
from deteccion import buscar, clasificar
from protocolos import detectar_temas, tema_de_consulta
from triage import (
    SENALES_CRITICAS, SENALES_INCONSCIENCIA, TriageState, hay_herido, hay_objeto_clavado,
    procesar_turno_usuario,
)


@pytest.fixture
def sin_indice(monkeypatch):
    monkeypatch.setattr(agent, "_retriever", None)
    monkeypatch.setattr(agent, "_iniciar_carga", lambda: None)


# --- clasificación ----------------------------------------------------------------

@pytest.mark.parametrize("texto,palabra,esperado", [
    ("No hay humo.", "humo", "negado"),
    ("Ni fuego ni humo.", "humo", "negado"),
    ("Sin fuego.", "fuego", "negado"),
    ("No hay nada de humo.", "humo", "negado"),
    ("No hay fuego, humo ni nafta.", "humo", "negado"),
    ("Hay humo.", "humo", "afirmado"),
    ("No hay heridos pero sale humo.", "humo", "afirmado"),
    ("No, no hay humo, está inconsciente.", "inconsciente", "afirmado"),
    ("No, está inconsciente.", "inconsciente", "afirmado"),
    ("No sé si está inconsciente.", "inconsciente", "afirmado"),
    ("si esta tirado en el piso", "tirado", "afirmado"),
    ("¿Hay riesgo de incendio?", "incendio", "hipotetico"),
    ("Si no respira, ¿qué hago?", "no respira", "hipotetico"),
    ("¿Y si se prende fuego?", "fuego", "hipotetico"),
])
def test_clasificar(texto, palabra, esperado):
    assert clasificar(texto, texto.lower().index(palabra)) == esperado


# --- señales críticas -------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "No, no hay fuego ni humo.",
    "No hay fuego, humo ni nafta.",
    "No está inconsciente, me habla.",
    "No, no está atrapado, ya salió solo.",
    "Nadie está atrapado.",
    "No sangra mucho, es un raspón.",
    "El celular no responde.",
    "No se mueve la puerta.",
    "¿Hay riesgo de incendio?",
    "Si no respira, ¿qué hago?",
    "¿Y si se desmaya?",
])
def test_negado_o_hipotetico_no_alerta_ni_deriva(texto):
    st = TriageState()
    assert procesar_turno_usuario(texto, st) is None
    assert not st.derivado and not st.alertas
    assert st.respira is None and st.consciente is None and st.atrapado is None


@pytest.mark.parametrize("texto,senal", [
    ("No, no respira.", "no respira"),
    ("Ya no respira.", "no respira"),
    ("Creo que no respira.", "no respira"),
    ("No, no se le mueve el pecho.", "no se le mueve el pecho"),
    ("No, está inconsciente.", "inconsciente"),
    ("No sé si está inconsciente.", "inconsciente"),
    ("No, no hay humo, está inconsciente.", "inconsciente"),
    ("Quedó en el auto, no responde.", "no responde"),
    ("El conductor del auto no responde.", "no responde"),
    ("No, no puede salir.", "no puede salir"),
    ("Sí, está atrapado.", "atrapado"),
    ("No hay heridos pero sale humo.", "humo"),
    ("Hay humo, no hay fuego.", "humo"),
    ("Hay dos heridos: uno no respira y el otro sangra mucho.", "no respira"),
])
def test_afirmado_sigue_alertando(texto, senal):
    st = TriageState()
    assert procesar_turno_usuario(texto, st) == senal
    assert st.derivado


def test_negar_una_cosa_no_niega_la_siguiente():
    st = TriageState()
    assert procesar_turno_usuario("No, no hay fuego. Pero está inconsciente.", st) == "inconsciente"
    assert "fuego" not in st.alertas


def test_riesgos_registrados_negados_no_son_criticos():
    """Lo que registra el modelo con la tool tampoco: «sin fuego ni humo»."""
    st = TriageState(riesgos="sin fuego ni humo", heridos="ninguno")
    assert not st.critico()
    st = TriageState(riesgos="ninguno", heridos="inconsciente")
    assert st.critico()


def test_objetos_no_son_personas():
    assert buscar("El celular no responde.", SENALES_INCONSCIENCIA, descartar_objetos=True) is None
    assert buscar("No responde el celular.", SENALES_INCONSCIENCIA, descartar_objetos=True) is None
    assert buscar("Está tirado y no se mueve.", SENALES_INCONSCIENCIA, descartar_objetos=True)
    assert buscar("Está en el auto no responde", SENALES_INCONSCIENCIA, descartar_objetos=True)
    # Sin descartar objetos la señal se ve: el filtro es opt-in por categoría.
    assert buscar("El celular no responde.", SENALES_CRITICAS)


# --- heridos y objeto clavado ------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("No sangra, está bien.", False),
    ("No está lastimado.", False),
    ("Se cayó la moto, pero yo estoy bien.", False),
    ("El auto está golpeado.", False),
    ("No sangra pero le duele la pierna.", True),
    ("Se cayó de la moto.", True),
    ("La moto lo dejó tirado en el piso.", True),
])
def test_hay_herido_con_negaciones_y_objetos(texto, esperado):
    assert hay_herido(texto) is esperado


def test_objeto_clavado_negado():
    st = TriageState(dichos=["No tiene nada clavado, solo un raspón."])
    assert not hay_objeto_clavado(st)
    st.dichos.append("Ah no, tiene un vidrio clavado en el brazo.")
    assert hay_objeto_clavado(st)


# --- temas --------------------------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("No sangra, está bien.", []),
    ("No tiene nada clavado.", []),
    ("No, no hay fuego ni humo.", []),
    ("Dejá de tomar mate y ayudame.", []),
    ("Se quemó el motor pero nadie se lastimó.", []),
    ("Se quemó la mano con el caño de escape.", ["quemadura"]),
    ("Si sangra mucho, ¿qué hago?", ["hemorragia"]),
    ("No le saco el casco?", ["casco"]),
    ("No sangra. ¿Le saco el casco?", ["casco"]),
    ("Me pide agua, ¿le doy?", ["beber"]),
    ("No, no se le mueve el pecho.", ["rcp"]),
])
def test_temas_con_negaciones(texto, esperado):
    assert detectar_temas(texto) == esperado


def test_consulta_del_modelo_no_se_lee_como_negacion():
    """El «no» de «no mover al herido» es parte de la indicación."""
    assert tema_de_consulta("no mover al herido, columna").clave == "columna"


def test_contexto_sin_alerta_si_niega_el_fuego(sin_indice):
    st = TriageState()
    extra = asyncio.run(agent.contexto_del_turno(
        "No, no hay fuego ni humo.", st, "¿Hay fuego, humo o combustible cerca?"
    ))
    assert not st.derivado
    assert "RIESGO DE FUEGO" not in extra and "Qué indicar:" not in extra
    # Sigue el triage: lo próximo es preguntar por heridos.
    assert "lastimado" in extra
