"""Tests de las respuestas fijas de los momentos críticos: sin red, sin LLM.

En esos momentos la respuesta sale de respuestas_fijas.py y no del modelo.
Se prueba cuándo se usan y, tan importante como eso, cuándo NO: si hay otra
urgencia o algo más que responder en el mismo turno, responde el modelo.
"""

from __future__ import annotations

import asyncio

import pytest

import agent
import respuestas_fijas as rf
from triage import TriageState, esta_despierto, procesar_turno_usuario


@pytest.fixture(autouse=True)
def sin_indice(monkeypatch):
    monkeypatch.setattr(agent, "_retriever", None)
    monkeypatch.setattr(agent, "_iniciar_carga", lambda: None)


def _fija(*turnos: tuple[str, str]) -> str | None:
    """La respuesta fija del último turno de la conversación."""
    st = TriageState()

    async def correr():
        turno = None
        for texto, ultima in turnos:
            turno = await agent.preparar_turno(texto, st, ultima)
        return turno.respuesta_fija

    return asyncio.run(correr())


# --- cuándo se usan ------------------------------------------------------------------

def test_inconsciente_pide_fijarse_si_respira():
    assert _fija(("Mi acompañante está inconsciente.", "¿Hay alguien lastimado?")) == rf.FIJATE_SI_RESPIRA


def test_inconsciente_que_pregunta_por_rcp_primero_se_fija_si_respira():
    assert _fija(("Está inconsciente, ¿le hago RCP?", "")) == rf.FIJATE_SI_RESPIRA


@pytest.mark.parametrize("turnos", [
    [("Choqué, hay un hombre tirado que no respira", "")],
    [("Está inconsciente y no respira", "")],
    [("Está inconsciente.", ""), ("No, no se le mueve el pecho.", rf.FIJATE_SI_RESPIRA)],
])
def test_paro_indica_rcp(turnos):
    assert _fija(*turnos) == rf.RCP


def test_casco_primera_vez_y_repetido():
    primera = _fija(
        ("Choqué con una moto, está tirado en el piso.", "¿Hay alguien lastimado?"),
        ("¿Le saco el casco?", "¿Está despierto y responde?"),
    )
    assert primera.startswith(rf.CASCO)
    otra_vez = _fija(
        ("Choqué con una moto, está tirado en el piso.", "¿Hay alguien lastimado?"),
        ("¿Le saco el casco?", "¿Está despierto y responde?"),
        ("le scao el casco", primera),
    )
    assert otra_vez.startswith(rf.CASCO_OTRA_VEZ[0])


def test_casco_cierra_segun_el_estado_del_herido():
    despierto = _fija(
        ("Hay un motociclista herido, está despierto y me habla.", ""),
        ("¿Le saco el casco?", "¿Le duele algo?"),
    )
    assert despierto.endswith("¿Se queja de dolor en el cuello?")
    inconsciente = _fija(
        ("El motociclista está inconsciente.", ""),
        ("¿Le saco el casco?", "¿Está despierto?"),
    )
    assert inconsciente.endswith(rf.FIJATE_SI_RESPIRA)
    # Si eso fue lo último que preguntó, lo vuelve a pedir con otras palabras.
    otra_vez = _fija(
        ("El motociclista está inconsciente.", ""),
        ("¿Le saco el casco?", rf.FIJATE_SI_RESPIRA),
    )
    assert otra_vez.endswith("Mirá si el pecho sube y baja: ¿respira?")


def test_casco_tercera_vez_cambia_las_palabras():
    turnos = [("Choqué con una moto, está tirado en el piso.", "")]
    respuestas = []
    for _ in range(3):
        turnos.append(("¿Le saco el casco?", respuestas[-1] if respuestas else ""))
        respuestas.append(_fija(*turnos))
    assert respuestas[0].startswith(rf.CASCO)
    assert respuestas[1].startswith(rf.CASCO_OTRA_VEZ[0])
    assert respuestas[2].startswith(rf.CASCO_OTRA_VEZ[1])


@pytest.mark.parametrize("texto", ["Ahora no me contesta, se desmayó.", "Perdió el conocimiento."])
def test_desmayo_es_inconsciencia(texto):
    st = TriageState(consciente=True)
    procesar_turno_usuario(texto, st)
    assert st.consciente is False and "inconsciencia" in st.alertas


def test_casco_no_repite_la_ultima_pregunta():
    fija = _fija(
        ("Choqué con una moto, está tirado en el piso.", ""),
        ("¿Le saco el casco?", "Quedate a salvo. ¿Te responde cuando le hablás?"),
    )
    assert not fija.endswith("¿Te responde cuando le hablás?")


@pytest.mark.parametrize("texto,cierre", [
    ("Tiene un fierro clavado en la pierna.", "¿Le sale mucha sangre alrededor del objeto?"),
    ("Tiene un fierro clavado y sangra mucho.", "¿Está despierto y te responde?"),
])
def test_objeto_clavado(texto, cierre):
    fija = _fija((texto, ""))
    assert fija.startswith(rf.OBJETO_CLAVADO) and fija.endswith(cierre)


# --- cuándo NO: responde el modelo -------------------------------------------------------

@pytest.mark.parametrize("turnos", [
    # Otra urgencia en el mismo turno.
    [("No respira y sale mucho humo del motor", "")],
    # Atrapado en el auto: no se puede comprimir ahí.
    [("Está atrapado en el auto y no respira", "")],
    # No llega al herido.
    [("Creo que no respira, no lo veo bien", "")],
    # Otro tema además del momento crítico.
    [("Está inconsciente con el casco puesto", "")],
    [("Tiene un vidrio clavado, ¿le saco el casco?", "")],
    # Ya se lo sacó: es otra situación.
    [("Ya le saqué el casco, ¿está bien?", "")],
    # Casco sin pregunta: lo dice el modelo con el protocolo.
    [("Choqué con una moto, está tirado en el piso con el casco.", "")],
    # En plena RCP manda el aviso de RCP.
    [("No respira", ""), ("Ya empecé, ¿y ahora?", rf.RCP)],
    [("No respira", ""), ("¿Le saco el casco?", rf.RCP)],
    # Llegó la ayuda.
    [("Llegó la ambulancia, está inconsciente", "")],
])
def test_no_usa_respuesta_fija(turnos):
    assert _fija(*turnos) is None


@pytest.mark.parametrize("texto,esperado", [
    ("¿Le saco el casco?", True),
    ("le scao el casco", True),
    ("¿Puedo sacarle el casco?", True),
    ("Ya le saqué el casco", False),
    ("Ya le saque el casco", False),
    ("Se lo sacó un señor que pasaba", False),
    ("Tiene el casco puesto", False),
])
def test_pide_sacar_casco(texto, esperado):
    assert rf.pide_sacar_casco(texto) is esperado


# --- detección que usan las respuestas fijas --------------------------------------------

def test_dos_urgencias_nuevas_en_el_mismo_turno():
    """Antes, si la primera categoría ya estaba avisada, la segunda no se veía."""
    st = TriageState()
    procesar_turno_usuario("Está inconsciente.", st)
    assert procesar_turno_usuario("Sigue inconsciente y ahora sale humo del motor.", st) == "humo"
    assert "fuego" in st.alertas
    st = TriageState()
    assert procesar_turno_usuario("No respira y sale mucho humo.", st) == "no respira"
    assert st.senales_del_turno == ["no respira", "humo"]


def test_con_paro_no_se_avisa_tambien_la_inconsciencia():
    st = TriageState()
    extra = asyncio.run(agent.contexto_del_turno("Está inconsciente y no respira", st))
    assert "NO RESPIRA" in extra and "Todavía NO se sabe si respira" not in extra


@pytest.mark.parametrize("texto,esperado", [
    ("Está despierto y me habla.", True),
    ("Hay un señor herido pero está despierto.", True),
    ("Se queja del cuello.", True),
    ("No me responde.", False),
    ("No está consciente.", False),
    ("Sigue inconsciente, no me habla.", False),
])
def test_esta_despierto(texto, esperado):
    assert esta_despierto(texto) is esperado
