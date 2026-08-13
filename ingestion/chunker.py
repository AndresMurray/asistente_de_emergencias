"""Chunker consciente de la estructura del documento.

Reemplaza a _RecursiveCharacterSplitter de chunking.py en lugar de parcharlo,
porque el bug de ese era de arquitectura: _split_recursive hacía part.strip() y
descartaba el separador, y _merge_with_overlap volvía a unir con un espacio
simple, así que la clase no podía preservar límites de oración por más que se le
movieran los parámetros. El resultado medido sobre la tabla en producción: 95%
de los chunks arrancaban en mitad de una oración, 66% no terminaban en
puntuación, y 23% traían basura de encabezado.

Cómo funciona:

1. El texto se parte por los encabezados de página «TEMA n Pág. m», que además
   son la fuente de la metadata: de ahí salen el capítulo y el número de página
   de cada chunk. Eso se hace ANTES de limpiarlos, claro.
2. Se descartan los bloques de índice (los que tienen corridas de puntos).
3. Dentro del texto ya limpio se detectan los títulos numerados. La detección es
   inline y no ancorada a línea: el texto reconstruido desde la base perdió casi
   todos los newlines, y un regex con ^...$ y re.M encuentra CERO títulos ahí.
4. Cada sección se empaqueta en chunks de oraciones COMPLETAS, con solape de
   oraciones enteras. Nunca se corta una oración al medio.

Parámetros para prosa de protocolo en español: objetivo 900 caracteres, máximo
1500, mínimo 250. embed-multilingual-v3.0 trunca a 512 tokens (~1800 caracteres),
así que 1500 entra cómodo. Los 453 de promedio que tenía la tabla eran demasiado
poco: una secuencia como el ABC quedaba desparramada en cuatro chunks, que es por
qué el modelo tenía que adivinar cómo seguían.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- objetivos de tamaño ------------------------------------------------------

OBJETIVO = 900
MAXIMO = 1500
MINIMO = 250
SOLAPE_ORACIONES = 1

# --- patrones -----------------------------------------------------------------

# Encabezado de página. Trae el capítulo y la página, así que se captura antes de
# borrarlo. En el corpus actual hay 52, de «TEMA 3 Pág. 29» a «TEMA 6 Pág. 80».
ENCABEZADO_PAGINA = re.compile(r"TEMA\s*(\d+)\s*P[áa]g\.\s*(\d+)\s*")

# Corridas de puntos del índice: «1. Introducción: la hora de oro. . . . . . 30»
PUNTOS_INDICE = re.compile(r"(?:\.\s){4,}\.?\s*\d*")

# Prefijo numerado de un título: «3.» «3.1» «2.5.1.-» «2º-». Inline y no ancorado
# a línea, porque el texto reconstruido desde la base perdió casi todos los
# newlines y un regex con ^...$ y re.M encuentra CERO títulos.
PREFIJO_TITULO = re.compile(r"(?<![\w.,)])(\d{1,2}(?:\.\d{1,2}){0,2})[º°]?\s*[.\-)]*\s+")

# Palabra en mayúsculas sostenidas (el cuerpo de un título).
PALABRA_MAYUS = re.compile(r"[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ0-9,:ºª/().\-]*$")

# Conectores en minúscula que SÍ pueden ir dentro de un título:
# «2º- AVISAR o ALERTAR», «APOYO EMOCIONAL A LAS VÍCTIMAS». Se limita a esta
# lista corta: permitir minúsculas libres hacía que el título se comiera la prosa
# que venía después.
CONECTORES = {
    "o", "y", "e", "u", "de", "del", "la", "las", "el", "los", "en", "a",
    "al", "con", "por", "para", "su", "sus", "un", "una", "ante", "sobre",
}

TITULO_MIN_LARGO = 5
TITULO_MAX_LARGO = 80
TITULO_MAX_PALABRAS = 12

# Referencias cruzadas que no sirven dicha en voz alta. Ojo: NO se toca
# «(ver-oír-sentir)», que es un mnemónico clínico y no una referencia.
REFERENCIAS = re.compile(
    r"\s*\((?:ver|véase|vease|v\.)\s+(?:el\s+|la\s+)?"
    r"(?:tema|cap[íi]tulo|apartado|punto|figura|tabla|p[áa]g\.?)"
    # Cola holgada: hay referencias largas como
    # «(ver tema de Nociones Fisiológicas Básicas de este Manual)».
    r"[^)]{0,80}\)",
    re.IGNORECASE,
)
REFERENCIA_TABLA = re.compile(r"\s*\((?:ver|véase)\s+tabla\)", re.IGNORECASE)

# El corpus es un manual español y menciona el 112 trece veces. Quien llama es
# argentino. Se neutraliza en la ingesta para que el número casi nunca llegue al
# modelo; la regla del prompt que prohíbe leer números del contexto es la segunda
# línea de defensa.
NUMERO_ESPANA = re.compile(r"\b112\b")
REEMPLAZO_NUMERO = "el número de emergencias"

# Abreviaturas que NO terminan una oración, para el corte por oraciones.
ABREVIATURAS = {
    "pág", "págs", "art", "arts", "fig", "figs", "tab", "núm", "nº", "no",
    "dr", "dra", "sr", "sra", "etc", "ej", "p.ej", "vol", "cap", "aprox",
    "máx", "mín", "seg", "min", "kg", "cm", "mm", "ml", "km", "a.m", "p.m",
}

VINETAS = str.maketrans({"■": "-", "●": "-", "•": "-", "": "-"})


@dataclass
class Chunk:
    texto: str
    fuente: str = ""
    tema: int | None = None
    pagina_inicio: int | None = None
    pagina_fin: int | None = None
    seccion: str | None = None
    subseccion: str | None = None
    orden: int = 0

    def metadata(self) -> dict:
        return {
            "tema": self.tema,
            "seccion": self.seccion,
            "subseccion": self.subseccion,
            "pagina_inicio": self.pagina_inicio,
            "pagina_fin": self.pagina_fin,
        }


@dataclass
class _Trozo:
    """Fragmento de texto de una página, ya sin el encabezado."""

    texto: str
    tema: int | None
    pagina: int | None


def buscar_titulos(stream: str) -> list[tuple[int, int, str, str]]:
    """Encuentra títulos numerados. Devuelve (inicio, fin, numero, titulo).

    Se escanea token por token en lugar de usar un solo regex, porque con regex
    aparecían dos bugs difíciles de evitar: el título se cortaba ante un conector
    en minúscula («2º- AVISAR o ALERTAR» quedaba como «AVISAR», y «o ALERTAR» se
    volvía un chunk de 9 caracteres), y el lookahead retrocedía cuando lo que
    seguía era el número de la sección siguiente («…EN LAS DIFERENTES» partido de
    «SITUACIONES 2.1.-»).
    """
    encontrados: list[tuple[int, int, str, str]] = []

    for prefijo in PREFIJO_TITULO.finditer(stream):
        numero = prefijo.group(1)
        pos = prefijo.end()

        palabras: list[str] = []
        fin = pos
        cursor = pos
        hay_mayuscula = False

        while len(palabras) < TITULO_MAX_PALABRAS:
            espacio = re.compile(r"\s*").match(stream, cursor)
            inicio_palabra = espacio.end() if espacio else cursor
            token = re.compile(r"[^\s]+").match(stream, inicio_palabra)
            if not token:
                break
            palabra = token.group(0)

            if PALABRA_MAYUS.match(palabra) and len(palabra) >= 2:
                palabras.append(palabra)
                hay_mayuscula = True
                fin = token.end()
                cursor = token.end()
                continue

            # Un conector en minúscula solo cuenta si después vuelve a haber
            # mayúsculas: así «AVISAR o ALERTAR» entra entero, pero
            # «PROTEGER el lugar de los hechos» no se toma como título.
            if palabra.lower().strip(",:.") in CONECTORES and hay_mayuscula:
                siguiente = re.compile(r"\s*([^\s]+)").match(stream, token.end())
                if siguiente and PALABRA_MAYUS.match(siguiente.group(1)) and len(siguiente.group(1)) >= 2:
                    palabras.append(palabra)
                    cursor = token.end()
                    continue
            break

        if not hay_mayuscula or len(palabras) < 1:
            continue

        titulo = re.sub(r"\s+", " ", stream[pos:fin]).strip(" .,-:")
        if not (TITULO_MIN_LARGO <= len(titulo) <= TITULO_MAX_LARGO):
            continue
        # Un título de una sola palabra corta es casi siempre un falso positivo.
        if len(palabras) == 1 and len(titulo) < 8:
            continue
        encontrados.append((prefijo.start(), fin, numero, titulo))

    return encontrados


@dataclass
class _Seccion:
    titulo: str | None
    numero: str | None
    texto: str
    tema: int | None = None
    pagina_inicio: int | None = None
    pagina_fin: int | None = None
    partes: list[_Trozo] = field(default_factory=list)


# --- paso 1: separar por página y quedarse con la metadata --------------------


def separar_paginas(texto: str) -> list[_Trozo]:
    """Parte por «TEMA n Pág. m» y etiqueta cada trozo con capítulo y página."""
    trozos: list[_Trozo] = []
    marcas = list(ENCABEZADO_PAGINA.finditer(texto))

    if not marcas:
        return [_Trozo(texto=texto, tema=None, pagina=None)]

    # Texto anterior al primer encabezado, si hay algo sustancial.
    if marcas[0].start() > 0:
        previo = texto[: marcas[0].start()].strip()
        if previo:
            trozos.append(_Trozo(texto=previo, tema=None, pagina=None))

    for i, marca in enumerate(marcas):
        tema = int(marca.group(1))
        pagina = int(marca.group(2))
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        cuerpo = texto[marca.end() : fin]
        if cuerpo.strip():
            trozos.append(_Trozo(texto=cuerpo, tema=tema, pagina=pagina))
    return trozos


def es_indice(texto: str) -> bool:
    """Un trozo es índice si está dominado por corridas de puntos."""
    if not PUNTOS_INDICE.search(texto):
        return False
    sin_puntos = PUNTOS_INDICE.sub(" ", texto)
    # Si al sacar las corridas de puntos se va la mayor parte, era índice.
    return len(sin_puntos.strip()) < len(texto.strip()) * 0.65


# --- paso 2: limpieza ---------------------------------------------------------


def limpiar(texto: str) -> str:
    texto = texto.translate(VINETAS)
    texto = PUNTOS_INDICE.sub(" ", texto)
    texto = REFERENCIA_TABLA.sub("", texto)
    texto = REFERENCIAS.sub("", texto)
    texto = NUMERO_ESPANA.sub(REEMPLAZO_NUMERO, texto)
    # Restos de encabezado que hubieran quedado sin el «TEMA n» adelante.
    texto = re.sub(r"\s*P[áa]g\.\s*\d+\s*", " ", texto)
    texto = texto.replace("�", " ")
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\s*\n\s*", "\n", texto)
    return texto.strip()


# --- paso 3: cortar por oraciones --------------------------------------------


def partir_oraciones(texto: str) -> list[str]:
    """Corta en oraciones, respetando abreviaturas y numeraciones tipo «2º»."""
    oraciones: list[str] = []
    actual: list[str] = []

    # Se corta ante . ! ? : seguidos de espacio y mayúscula, o ante salto de línea.
    for pieza in re.split(r"(?<=[.!?:])\s+|\n+", texto):
        pieza = pieza.strip()
        if not pieza:
            continue
        actual.append(pieza)
        candidato = " ".join(actual)

        ultima = pieza.rstrip(".!?:").split()[-1].lower() if pieza.split() else ""
        termina_en_abreviatura = ultima.strip(".,;()") in ABREVIATURAS
        # «2º», «1.» y «A.» sueltos son numeraciones de lista, no fin de oración.
        es_numeracion = bool(re.fullmatch(r"[\dA-Za-zºª]{1,3}[.\-º)]?", pieza))

        if termina_en_abreviatura or es_numeracion:
            continue
        if pieza[-1] in ".!?:":
            oraciones.append(candidato)
            actual = []

    if actual:
        oraciones.append(" ".join(actual))
    return oraciones


# --- paso 4: armar secciones y empaquetar ------------------------------------


def detectar_secciones(trozos: list[_Trozo]) -> list[_Seccion]:
    """Une los trozos en un stream y lo corta por títulos, sin perder páginas."""
    # Stream con un mapa de posición -> (tema, página), para poder reconstruir la
    # metadata después de cortar por títulos.
    piezas: list[str] = []
    mapa: list[tuple[int, int | None, int | None]] = []
    largo = 0
    for t in trozos:
        limpio = limpiar(t.texto)
        if not limpio:
            continue
        if piezas:
            piezas.append(" ")
            largo += 1
        mapa.append((largo, t.tema, t.pagina))
        piezas.append(limpio)
        largo += len(limpio)
    stream = "".join(piezas)

    def ubicar(pos: int) -> tuple[int | None, int | None]:
        tema = pagina = None
        for inicio, tm, pg in mapa:
            if inicio <= pos:
                tema, pagina = tm, pg
            else:
                break
        return tema, pagina

    marcas = buscar_titulos(stream)
    secciones: list[_Seccion] = []

    if not marcas:
        tema, pagina = ubicar(0)
        return [
            _Seccion(
                titulo=None, numero=None, texto=stream, tema=tema,
                pagina_inicio=pagina, pagina_fin=ubicar(len(stream))[1],
            )
        ]

    if marcas[0][0] > 0:
        cabeza = stream[: marcas[0][0]].strip()
        if len(cabeza) >= MINIMO:
            tema, pagina = ubicar(0)
            secciones.append(
                _Seccion(titulo=None, numero=None, texto=cabeza, tema=tema,
                         pagina_inicio=pagina, pagina_fin=pagina)
            )

    for i, (inicio, fin_titulo, numero, titulo) in enumerate(marcas):
        fin = marcas[i + 1][0] if i + 1 < len(marcas) else len(stream)
        cuerpo = stream[fin_titulo:fin].strip()
        if not cuerpo:
            continue
        tema, pagina_inicio = ubicar(inicio)
        _, pagina_fin = ubicar(fin)
        secciones.append(
            _Seccion(
                titulo=titulo, numero=numero, texto=cuerpo, tema=tema,
                pagina_inicio=pagina_inicio, pagina_fin=pagina_fin,
            )
        )
    return secciones


def empaquetar(oraciones: list[str]) -> list[str]:
    """Agrupa oraciones completas hasta el objetivo, con solape de oraciones."""
    if not oraciones:
        return []

    grupos: list[list[str]] = []
    actual: list[str] = []
    largo = 0

    for oracion in oraciones:
        # Una oración sola más larga que el máximo va sola: partirla rompería la
        # premisa de no cortar oraciones, y son casos raros.
        if len(oracion) > MAXIMO:
            if actual:
                grupos.append(actual)
                actual, largo = [], 0
            grupos.append([oracion])
            continue

        if largo and largo + 1 + len(oracion) > OBJETIVO:
            grupos.append(actual)
            solape = actual[-SOLAPE_ORACIONES:] if SOLAPE_ORACIONES else []
            # El solape no puede comerse el presupuesto del chunk siguiente.
            if sum(len(s) for s in solape) > OBJETIVO // 2:
                solape = []
            actual = list(solape)
            largo = sum(len(s) + 1 for s in actual)

        actual.append(oracion)
        largo += len(oracion) + 1

    if actual:
        grupos.append(actual)

    textos = [" ".join(g).strip() for g in grupos]

    # Cola corta: se fusiona con el chunk anterior en lugar de emitir un chunk
    # que no dice nada por sí solo.
    if len(textos) >= 2 and len(textos[-1]) < MINIMO:
        fusionado = textos[-2] + " " + textos[-1]
        if len(fusionado) <= MAXIMO:
            textos[-2:] = [fusionado]

    return textos


def chunkear(texto: str, fuente: str) -> list[Chunk]:
    """Punto de entrada: texto crudo del documento -> chunks con metadata."""
    trozos = [t for t in separar_paginas(texto) if not es_indice(t.texto)]
    secciones = detectar_secciones(trozos)

    chunks: list[Chunk] = []
    orden = 0
    for seccion in secciones:
        oraciones = partir_oraciones(seccion.texto)
        for cuerpo in empaquetar(oraciones):
            if len(cuerpo) < MINIMO and chunks:
                # Absorber restos mínimos en el chunk anterior de la misma sección.
                previo = chunks[-1]
                if previo.seccion == seccion.titulo and len(previo.texto) + len(cuerpo) <= MAXIMO:
                    previo.texto = previo.texto + " " + cuerpo
                    continue
            etiqueta = _etiqueta(seccion)
            chunks.append(
                Chunk(
                    texto=cuerpo,
                    fuente=fuente,
                    tema=seccion.tema,
                    pagina_inicio=seccion.pagina_inicio,
                    pagina_fin=seccion.pagina_fin,
                    seccion=etiqueta,
                    subseccion=None,
                    orden=orden,
                )
            )
            orden += 1
    return chunks


def _etiqueta(seccion: _Seccion) -> str | None:
    """Título legible, con el número de sección adelante si lo hay."""
    if not seccion.titulo:
        return None
    if seccion.numero:
        return f"{seccion.numero}. {seccion.titulo}"
    return seccion.titulo
