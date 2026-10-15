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

from habla import FRASE_911, EstadoAviso, NormalizadorStream, aplicar_aviso_911, aviso_ya_dicho, normalizar_habla
from protocolos import TEMAS, consultas_canonicas, detectar_temas, respira_positivo, tema_de_consulta
from rag import ratelimit
from rag.index import MemoryIndex, tokenizar
from rag.store import Fragment
from triage import (
    TriageState, confirma_despierto, confirma_heridos, generar_aviso_critico, hay_herido, procesar_turno_usuario,
    sin_acceso_al_herido,
)


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


@pytest.mark.parametrize("texto,esperado", [
    ("si esta tirado en el piso con el casco", True),
    ("hay un herido en la ruta", True),
    ("nadie está lastimado", False),
    ("no hay heridos, solo el auto roto", False),
    ("tuve un roce con otro auto", False),
    ("hubo un accidente una persona tiene un fierro clavado", True),
    ("tiene un vidrio incrustado en el brazo", True),
    # Visto en la web: no derivaba.
    ("hay un accidentado en moto", True),
    ("el auto accidentado quedó en la banquina", False),
])
def test_hay_herido(texto, esperado):
    assert hay_herido(texto) is esperado


@pytest.mark.parametrize("texto,pregunta,esperado", [
    ("si, una persona", "¿Hay alguien herido y hay fuego cerca?", True),
    ("una", "¿Cuántas personas están heridas?", True),
    ("el acompañante", "¿Hay alguien lastimado?", True),
    ("no, nadie", "¿Hay alguien herido?", False),
    ("sí", "¿Hay fuego, humo o combustible cerca?", False),
    ("si, una persona", "", False),
    # Visto en la web: empezaba con «y» y no se tomaba como un sí.
    ("y si, el de la moto", "¿Hay alguien lastimado?", True),
    ("obvio, el motociclista", "¿Hay alguien lastimado?", True),
    ("la del auto blanco", "¿Hay alguien lastimado?", True),
    ("el auto nomás", "¿Hay alguien lastimado?", False),
    ("y no, nadie", "¿Hay alguien lastimado?", False),
    ("mmm no sé, creo que sí, el otro conductor", "¿Hay alguien lastimado?", True),
    ("no sé si hay alguien", "¿Hay alguien lastimado?", False),
    ("el otro auto está destrozado", "¿Hay alguien lastimado?", False),
])
def test_confirma_heridos(texto, pregunta, esperado):
    assert confirma_heridos(texto, pregunta) is esperado


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
    assert detectar_temas("una persona tiene un fierro clavado") == ["objeto_clavado"]
    assert "objeto_clavado" not in detectar_temas("se golpeó la clavícula")


def test_objeto_clavado_cambia_el_aviso_de_sangrado():
    st = TriageState()
    procesar_turno_usuario("tiene un fierro clavado en la pierna", st)
    senal = procesar_turno_usuario("y sangra mucho", st)
    aviso = generar_aviso_critico(senal, st)
    assert "NO saque" in aviso and "alrededor" in aviso


@pytest.mark.parametrize("texto,esperado", [
    ("sí, se le mueve el pecho", True),
    ("está respirando", True),
    # Respuestas cortas a «¿Respira?» o en plena RCP: antes no se detectaban
    # y el metrónomo seguía sonando después de «Sí, respira».
    ("Sí, respira.", True),
    ("Respira.", True),
    ("ya respira", True),
    ("empezó a toser", True),
    ("abrió los ojos", True),
    ("no está respirando", False),
    ("no se le mueve el pecho", False),
    ("no sé si respira", False),
    ("si respira, ¿qué hago?", False),
    # Respiración anormal: se sigue tratando como paro.
    ("respira raro, como que boquea", False),
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
    # Erratas vistas en las pruebas de la Expo.
    ("Mantené la cabeza alineada y no lo movas.", "Mantené la cabeza alineada y no lo muevas."),
    ("Alejáos del auto y de la calzada.", "Aléjense del auto y de la calzada."),
    ("Mantené la calma y mantené la calma.", "Mantené la calma."),
    ("Asegurate de que no obstruya y enciende las balizas.", "Asegurate de que no obstruya y encendé las balizas."),
    ("Apaga el motor.", "Apagá el motor."),
])
def test_normalizar_habla(entrada, salida):
    assert normalizar_habla(entrada) == salida


@pytest.mark.parametrize("pregunta", ["¿Respira?", "¿Sigue sangrando?", "El sistema verifica todo."])
def test_normalizar_no_toca_terceras_personas(pregunta):
    assert normalizar_habla(pregunta) == pregunta


def test_aviso_911_se_agrega_una_sola_vez_al_derivar():
    st = EstadoAviso(derivado=True)
    primera = aplicar_aviso_911("Apoyá el talón de tu mano en el centro del pecho.", st)
    assert primera.startswith(FRASE_911)
    segunda = aplicar_aviso_911("Seguí comprimiendo sin parar.", st)
    assert FRASE_911 not in segunda


def test_aviso_911_no_se_duplica_si_el_modelo_lo_dijo():
    st = EstadoAviso(derivado=True)
    texto = "Ya estás geolocalizado y la ayuda va en camino."
    assert aplicar_aviso_911(texto, st) == texto
    # y si lo repite en un turno posterior, se saca
    assert aplicar_aviso_911("Ya estás geolocalizado y la ayuda va en camino. No la muevas.", st) == "No la muevas."


def test_sin_derivacion_no_hay_aviso_911():
    st = EstadoAviso(derivado=False)
    assert aplicar_aviso_911("Encendé las balizas.", st) == "Encendé las balizas."


def test_sin_derivacion_no_promete_ayuda():
    st = EstadoAviso(derivado=False)
    texto = "Alejate del tráfico y esperá a que llegue la ayuda."
    assert aplicar_aviso_911(texto, st) == "Alejate del tráfico."
    # Antes el reemplazo era «mantené la calma» y duplicaba la frase.
    assert aplicar_aviso_911("Mantené la calma y esperá a que llegue la ayuda.", st) == "Mantené la calma."
    assert aplicar_aviso_911("No muevas el auto hasta que lleguen los servicios.", st) == "No muevas el auto."
    assert aplicar_aviso_911("Mantené la cabeza inmóvil hasta que llegue ayuda.", st) == "Mantené la cabeza inmóvil."
    # Versión corta, vista en la prueba por voz del choque sin heridos.
    assert aplicar_aviso_911("Quedate donde estás y esperá ayuda.", st) == "Quedate donde estás."
    assert aplicar_aviso_911("Mantené el freno, no te muevas y esperá ayuda.", st) == "Mantené el freno, no te muevas."


def test_con_derivacion_puede_decir_espera_ayuda():
    st = EstadoAviso(derivado=True)
    aplicar_aviso_911("Fijate si respira.", st)  # primera respuesta: lleva el aviso
    assert aplicar_aviso_911("Quedate con él y esperá la ayuda.", st) == "Quedate con él y esperá la ayuda."


def test_aviso_ya_dicho_sale_del_historial():
    assert aviso_ya_dicho(["Emergencias viales, te escucho.", f"{FRASE_911} Fijate si respira."])
    assert not aviso_ya_dicho(["Emergencias viales, te escucho.", "¿Hay alguien lastimado?"])


def test_con_derivacion_se_mantiene_hasta_que_llegue_la_ayuda():
    st = EstadoAviso(derivado=True)
    aplicar_aviso_911("Comprimí fuerte.", st)  # primera respuesta: lleva el aviso
    assert aplicar_aviso_911("Seguí hasta que llegue la ayuda.", st) == "Seguí hasta que llegue la ayuda."


@pytest.mark.parametrize("entrada,salida", [
    ("Quedáte donde estás.", "Quedate donde estás."),
    ("Alejáte del tráfico.", "Alejate del tráfico."),
    ("Dejálo quieto.", "Dejalo quieto."),
    ("La guía está acá.", "La guía está acá."),
])
def test_tilde_en_imperativo_con_pronombre(entrada, salida):
    assert normalizar_habla(entrada) == salida


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


def test_preguntas_de_seguimiento():
    """Todo tema tiene con qué cerrar, salvo RCP: comprimiendo no se pregunta."""
    for tema in TEMAS.values():
        if tema.clave == "rcp":
            assert tema.seguimiento == ()
            continue
        assert tema.seguimiento, tema.clave
        for pregunta in tema.seguimiento:
            assert pregunta.startswith("¿") and pregunta.endswith("?"), pregunta
            assert "112" not in pregunta and "pudiste" not in pregunta.lower()


@pytest.mark.parametrize("texto,pregunta,esperado", [
    ("y si", "Quedate a distancia. ¿Está despierto y habla?", True),
    ("sí, me habla", "¿Te responde cuando le hablás?", True),
    ("no, no me responde", "¿Te responde cuando le hablás?", False),
    ("sí", "¿Respira?", False),
    ("sí", "¿Hay alguien lastimado?", False),
])
def test_confirma_despierto(texto, pregunta, esperado):
    assert confirma_despierto(texto, pregunta) is esperado
