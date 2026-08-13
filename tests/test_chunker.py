"""Tests que congelan la calidad del chunking.

Existen porque el chunker anterior degradó el corpus sin que nadie se enterara:
la tabla en producción tenía 95% de chunks arrancando en mitad de una oración,
66% sin puntuación final y 23% con basura de encabezado, y no había forma de
notarlo salvo mirando filas a mano. Estas aserciones convierten esos números en
rojo/verde.

Correr con:  python -m pytest tests/ -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ingestion.chunker import (
    MAXIMO,
    MINIMO,
    buscar_titulos,
    chunkear,
    empaquetar,
    es_indice,
    limpiar,
    partir_oraciones,
    separar_paginas,
)

CORPUS = Path("data/processed/corpus_reconstruido.txt")

# Umbrales. No son 0% porque el PDF tiene texto de figuras y listas partidas que
# no se pueden reparar sin el original; son techos para detectar regresiones.
MAX_MINUSCULA = 0.12
MAX_SIN_PUNTUACION = 0.05


@pytest.fixture(scope="module")
def chunks():
    if not CORPUS.exists():
        pytest.skip(
            f"falta {CORPUS}. Generalo con: python -m ingestion.reconstruir -o {CORPUS}"
        )
    return chunkear(CORPUS.read_text(encoding="utf-8"), "corpus.pdf")


# --- las garantías que importan -----------------------------------------------


def test_ningun_chunk_arranca_en_mitad_de_oracion(chunks):
    malos = [c for c in chunks if re.match(r"^[a-záéíóúñü]", c.texto.strip())]
    ratio = len(malos) / len(chunks)
    assert ratio <= MAX_MINUSCULA, (
        f"{len(malos)}/{len(chunks)} ({ratio:.0%}) arrancan en minúscula, "
        f"techo {MAX_MINUSCULA:.0%}. Ejemplo: {malos[0].texto[:90]!r}"
    )


def test_los_chunks_terminan_en_puntuacion(chunks):
    malos = [c for c in chunks if not re.search(r"[.!?:]\s*$", c.texto.strip())]
    ratio = len(malos) / len(chunks)
    assert ratio <= MAX_SIN_PUNTUACION, (
        f"{len(malos)}/{len(chunks)} ({ratio:.0%}) no terminan en puntuación, "
        f"techo {MAX_SIN_PUNTUACION:.0%}. Ejemplo: …{malos[0].texto[-90:]!r}"
    )


def test_sin_basura_de_encabezado(chunks):
    malos = [c for c in chunks if re.search(r"TEMA\s*\d+\s*P[áa]g|P[áa]g\.\s*\d+", c.texto)]
    assert not malos, f"{len(malos)} chunks con encabezado: {malos[0].texto[:90]!r}"


def test_sin_indice_con_puntos_suspensivos(chunks):
    malos = [c for c in chunks if re.search(r"(?:\.\s){4,}", c.texto)]
    assert not malos, f"{len(malos)} chunks con índice: {malos[0].texto[:90]!r}"


def test_sin_referencias_cruzadas_inutiles(chunks):
    """«(ver tema 4)» no sirve dicho en voz alta a quien llama."""
    malos = [
        c for c in chunks
        if re.search(r"\((?:ver|véase)\s+(?:el\s+)?(?:tema|cap[íi]tulo|tabla|apartado)", c.texto, re.I)
    ]
    assert not malos, f"{len(malos)} chunks con referencia cruzada: {malos[0].texto[:90]!r}"


def test_no_menciona_el_numero_de_emergencias_espanol(chunks):
    """El corpus es español y dice 112; quien llama es argentino.

    Es la primera de dos líneas de defensa: acá se neutraliza en la ingesta, y en
    el prompt hay una regla que prohíbe leer cualquier número que venga del
    contexto recuperado.
    """
    malos = [c for c in chunks if re.search(r"\b112\b", c.texto)]
    assert not malos, f"{len(malos)} chunks mencionan el 112: {malos[0].texto[:90]!r}"


def test_tamanos_dentro_de_rango(chunks):
    chicos = [c for c in chunks if len(c.texto) < MINIMO]
    grandes = [c for c in chunks if len(c.texto) > MAXIMO]
    assert not chicos, f"{len(chicos)} chunks bajo {MINIMO}: {chicos[0].texto!r}"
    assert not grandes, f"{len(grandes)} chunks sobre {MAXIMO}: {len(grandes[0].texto)} ch"


def test_todos_tienen_metadata(chunks):
    """Sección y página son lo que reemplaza al literal hardcodeado «[GENERAL]»."""
    sin_seccion = [c for c in chunks if not c.seccion]
    sin_pagina = [c for c in chunks if not c.pagina_inicio]
    sin_tema = [c for c in chunks if not c.tema]
    assert not sin_seccion, f"{len(sin_seccion)} chunks sin sección"
    assert not sin_pagina, f"{len(sin_pagina)} chunks sin página"
    assert not sin_tema, f"{len(sin_tema)} chunks sin tema"


def test_el_orden_es_denso_y_creciente(chunks):
    assert [c.orden for c in chunks] == list(range(len(chunks)))


# --- unidades -----------------------------------------------------------------


def test_separar_paginas_saca_tema_y_pagina():
    trozos = separar_paginas("TEMA 3 Pág. 29 hola mundo TEMA 4 Pág. 42 chau")
    assert [(t.tema, t.pagina) for t in trozos] == [(3, 29), (4, 42)]
    assert trozos[0].texto.strip() == "hola mundo"


def test_es_indice_reconoce_las_corridas_de_puntos():
    assert es_indice("1. Introducción: la hora de oro. . . . . . . . . . . 30")
    assert not es_indice("La mortalidad de los accidentes se distribuye en 3 fases.")


def test_limpiar_neutraliza_el_numero_espanol():
    assert "112" not in limpiar("se solicitará ayuda a través del número 112, de tal forma")


def test_limpiar_saca_referencias_pero_deja_el_mnemonico():
    """«(ver-oír-sentir)» es un mnemónico clínico, no una referencia cruzada."""
    assert "(ver tema 4)" not in limpiar("está inconsciente (ver tema 4) y no respira")
    assert "ver-oír-sentir" in limpiar("comprobar la respiración (ver-oír-sentir) 10 segundos")


def test_titulo_con_conector_en_minuscula_no_se_corta():
    """Regresión: «2º- AVISAR o ALERTAR» quedaba como «AVISAR» + un chunk de 9 ch."""
    titulos = buscar_titulos("2º- AVISAR o ALERTAR a los servicios de emergencia y luego")
    assert titulos, "no detectó el título"
    assert "ALERTAR" in titulos[0][3]


def test_titulo_no_se_corta_ante_el_numero_siguiente():
    """Regresión: el lookahead retrocedía y partía el título en dos."""
    texto = "2. ATENCIÓN Y CONDUCTA EN LAS DIFERENTES SITUACIONES 2.1.- LESIONES CRÁNEO"
    titulos = buscar_titulos(texto)
    assert titulos, "no detectó el título"
    assert "SITUACIONES" in titulos[0][3], titulos[0][3]


def test_la_prosa_con_mayusculas_no_se_toma_como_titulo():
    """«…hay que PROTEGER el lugar de los hechos…» es prosa, no un título."""
    texto = "de lo ocurrido, hay que PROTEGER el lugar de los hechos y luego avisar"
    assert not buscar_titulos(texto)


def test_partir_oraciones_respeta_abreviaturas():
    oraciones = partir_oraciones("Ver la fig. 3 con cuidado. Después seguir.")
    assert len(oraciones) == 2, oraciones


def test_empaquetar_nunca_corta_una_oracion():
    oraciones = [f"Oración número {i} con relleno suficiente para sumar largo." for i in range(40)]
    for texto in empaquetar(oraciones):
        assert texto.endswith("."), texto[-50:]
        assert len(texto) <= MAXIMO


def test_empaquetar_no_emite_colas_minusculas():
    oraciones = ["A" * 880 + ".", "Cola."]
    for texto in empaquetar(oraciones):
        assert len(texto) >= MINIMO or len(texto) == len("Cola.")
