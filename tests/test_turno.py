"""Tests de la lógica determinística del turno: sin red, sin LLM.

Cubren las fallas que aparecieron en los ensayos contra el modelo real:
- el paro («no respira») no se avisaba si antes se había dicho «inconsciente»;
- se adjuntaba RCP a ciegas cuando la persona preguntaba por compresiones;
- «no veo si reacciona» terminaba en «¿está despierto?»;
- jerga y voseo neutro llegaban a la voz.
"""

from __future__ import annotations

import time

import pytest

from habla import FRASE_911, NormalizadorStream, aplicar_aviso_911, normalizar_habla
from protocolos import TEMAS, consultas_canonicas, detectar_temas, respira_positivo, tema_de_consulta
from rag import ratelimit
from rag.index import MemoryIndex, tokenizar
from rag.store import Fragment
from triage import TriageState, procesar_turno_usuario, sin_acceso_al_herido


# --- triage ----------------------------------------------------------------------

def test_paro_se_avisa_aunque_antes_hubo_inconsciencia():
    st = TriageState()
    assert procesar_turno_usuario("mi acompañante está inconsciente", st) == "inconsciente"
    assert st.respira is None
    assert procesar_turno_usuario("no, no respira", st) == "no respira"
    assert st.respira is False
    assert st.derivado


def test_misma_categoria_no_se_avisa_dos_veces():
    st = TriageState()
    assert procesar_turno_usuario("está inconsciente", st)
    assert procesar_turno_usuario("sigue inconsciente, no reacciona", st) is None


def test_atrapado_marca_estado_y_deriva():
    st = TriageState()
    procesar_turno_usuario("hay una persona atrapada en el auto", st)
    assert st.atrapado is True and st.derivado


def test_sin_senal_no_deriva():
    st = TriageState()
    assert procesar_turno_usuario("tuve un roce con otro auto", st) is None
    assert not st.derivado


@pytest.mark.parametrize("texto", ["no veo si reacciona", "No llego hasta el auto", "no puedo ver nada"])
def test_sin_acceso(texto):
    assert sin_acceso_al_herido(texto)


# --- protocolos -------------------------------------------------------------------

def test_todos_los_temas_tienen_respaldo_y_consulta_cacheada():
    canonicas = consultas_canonicas()
    for tema in TEMAS.values():
        assert len(tema.respaldo) > 80, tema.clave
        assert tema.consulta in canonicas


def test_respaldos_no_dicen_112():
    for tema in TEMAS.values():
        assert "112" not in tema.respaldo


def test_detectar_temas():
    assert detectar_temas("se cayó de la moto, ¿le saco el casco?") == ["casco"]
    assert "hemorragia" in detectar_temas("le sale mucha sangre de la pierna")
    assert "fuego" in detectar_temas("sale humo del motor")
    assert detectar_temas("hola, tuve un choque") == []


@pytest.mark.parametrize("texto,esperado", [
    ("sí, se le mueve el pecho", True),
    ("está respirando", True),
    ("no está respirando", False),
    ("no se le mueve el pecho", False),
    ("no sé si respira", False),
])
def test_respira_positivo(texto, esperado):
    assert respira_positivo(texto) is esperado


def test_tema_de_consulta():
    assert tema_de_consulta("control de hemorragias externas").clave == "hemorragia"
    assert tema_de_consulta("Accidente moto: retirar el casco, columna cervical").clave == "casco"
    assert tema_de_consulta("dolor de muelas") is None


# --- habla -----------------------------------------------------------------------

@pytest.mark.parametrize("entrada,salida", [
    ("Mantené la vía aérea abierta.", "Mantené el paso del aire abierto."),
    ("No la muevas, solo verifica si respira.", "No la muevas, solo verificá si respira."),
    ("Pon las manos en el pecho.", "Poné las manos en el pecho."),
    ("Comprimí a 100 a 120 compresiones por minuto.", "Comprimí dos veces por segundo."),
    ("Llamá al 112.", "Llamá al nueve once."),
    ("Puede tener una fractura.", "Puede tener un hueso roto."),
    ("Aplicá la maniobra frente‑mentón.", "Aplicá la maniobra frente y mentón."),
    ("Mantene la presión.", "Mantené la presión."),
])
def test_normalizar_habla(entrada, salida):
    assert normalizar_habla(entrada) == salida


@pytest.mark.parametrize("pregunta", ["¿Respira?", "¿Sigue sangrando?", "El sistema verifica todo."])
def test_normalizar_no_toca_terceras_personas(pregunta):
    assert normalizar_habla(pregunta) == pregunta


def test_aviso_911_se_agrega_una_sola_vez_al_derivar():
    st = TriageState()
    procesar_turno_usuario("el acompañante no respira", st)  # deriva
    primera = aplicar_aviso_911("Apoyá el talón de tu mano en el centro del pecho.", st)
    assert primera.startswith(FRASE_911)
    segunda = aplicar_aviso_911("Seguí comprimiendo sin parar.", st)
    assert FRASE_911 not in segunda


def test_aviso_911_no_se_duplica_si_el_modelo_lo_dijo():
    st = TriageState()
    procesar_turno_usuario("hay una persona atrapada", st)
    texto = "Ya estás geolocalizado y la ayuda va en camino."
    assert aplicar_aviso_911(texto, st) == texto
    # y si lo repite en un turno posterior, se saca
    assert aplicar_aviso_911("Ya estás geolocalizado y la ayuda va en camino. No la muevas.", st) == "No la muevas."


def test_sin_derivacion_no_hay_aviso_911():
    st = TriageState()
    procesar_turno_usuario("tuve un roce, nadie lastimado", st)
    assert aplicar_aviso_911("Encendé las balizas.", st) == "Encendé las balizas."


def test_normalizador_stream_corta_en_puntuacion():
    n = NormalizadorStream()
    salida = "".join(n.push(c) for c in ["Mantené la vía", " aérea abierta", ", y solo veri", "fica si ", "respira"])
    salida += n.flush()
    assert salida == "Mantené el paso del aire abierto, y solo verificá si respira"


# --- índice en memoria --------------------------------------------------------------

def _indice():
    frags = [
        Fragment(text="Presión directa sobre la herida para controlar la hemorragia.", score=0, section="HEMORRAGIAS EXTERNAS"),
        Fragment(text="No quitar el casco al motorista accidentado.", score=0, section="SOCORRER"),
        Fragment(text="Compresiones torácicas en el centro del pecho.", score=0, section="RCP"),
    ]
    embs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    return MemoryIndex(frags, embs)


def test_busqueda_vectorial():
    res = _indice().buscar_vector([0.1, 0.9, 0.0], 2)
    assert "casco" in res[0].text
    assert res[0].score > res[1].score


def test_busqueda_lexica_con_plural_y_acentos():
    res = _indice().buscar_lexico("control de hemorragias", 3)
    assert res and "hemorragia" in res[0].text


def test_busqueda_lexica_sin_relacion_no_devuelve_nada():
    assert _indice().buscar_lexico("precio de la verificación técnica", 3) == []


def test_tokenizar():
    assert tokenizar("Las Hemorragias") == ["hemorr"]


# --- rate limit del rerank ------------------------------------------------------------

def test_intentar_turno_no_espera():
    ratelimit._proxima = 0.0
    assert ratelimit.intentar_turno() is True
    t0 = time.monotonic()
    assert ratelimit.intentar_turno() is False
    assert time.monotonic() - t0 < 0.05
    ratelimit._proxima = 0.0
