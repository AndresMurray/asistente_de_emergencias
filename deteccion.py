"""Buscar señales en lo que dice la persona sin caer en las negaciones.

Antes la detección buscaba palabras sueltas: «No, no hay fuego ni humo» (la
respuesta natural a «¿Hay fuego o humo cerca?», que pregunta el propio agente)
disparaba la alerta de fuego y derivaba al 911; «No está inconsciente, me
habla» activaba la alerta de inconsciencia; «El celular no responde», también.

Cada aparición de una señal se clasifica mirando lo que la rodea dentro de la
misma parte de la frase:

- negada: hay una negación cerca antes («no hay humo», «ni humo», «nadie»,
  «sin fuego»);
- hipotética: está dentro de una pregunta o de un «si…» condicional («¿y si no
  respira?», «¿hay riesgo de incendio?»): sirve para responder, no para
  cambiar el estado ni derivar;
- afirmada: todo lo demás.

Criterio ante la duda: perder un «no respira» real es mucho peor que una falsa
alarma, así que solo se descarta lo que es claramente negado o hipotético. «No
sé si está inconsciente» cuenta como afirmado (mejor que el agente pida
verificar), y el «No,» con el que se contesta una pregunta no niega lo que
sigue («No, está inconsciente»).
"""

from __future__ import annotations

import re
from typing import Literal

Clase = Literal["afirmado", "negado", "hipotetico"]

_NEGACIONES = frozenset({
    "no", "ni", "nunca", "nadie", "ningún", "ningun", "ninguno", "ninguna",
    "sin", "tampoco", "jamás", "jamas",
})

# Fin de la «parte de la frase» que puede alcanzar una negación.
_CORTE = re.compile(r"[.;:!?¿¡]|\b(?:pero|aunque|y|e|si|porque|que|ahora|igual)\b", re.IGNORECASE)
_CORTE_O_COMA = re.compile(_CORTE.pattern + "|,", re.IGNORECASE)

# Expresiones con «no» que no niegan lo que viene después.
_NO_NIEGAN = re.compile(
    r"\bno\s*,|\bno\s+sé\b|\bno\s+sabemos\b|\bno\s+entiendo\b|\bno\s+(?:lo\s+)?puedo\s+creer\b",
    re.IGNORECASE,
)

# «No sé si…», «no estoy seguro si…»: es duda, no un condicional.
_ANTES_DE_SI_DUDA = frozenset({"sé", "se", "sabe", "sabemos", "sabés", "seguro", "segura", "idea"})

# Si el sujeto es una cosa, «no responde» / «no se mueve» no hablan de una persona.
OBJETOS = frozenset({
    "celular", "teléfono", "telefono", "auto", "coche", "motor", "puerta", "puertas",
    "volante", "freno", "frenos", "radio", "moto", "vehículo", "vehiculo", "camioneta",
    "camión", "camion", "colectivo", "cinturón", "cinturon", "airbag", "ventanilla",
    "llave", "batería", "bateria", "tablero", "pantalla", "aplicación", "app", "baúl", "baul",
})

_DETERMINANTES = frozenset({
    "el", "la", "los", "las", "mi", "mis", "su", "sus", "tu", "tus",
    "este", "esta", "ese", "esa", "un", "una",
})
_PREPOSICIONES = frozenset({
    "a", "al", "de", "del", "en", "con", "dentro", "adentro", "sobre", "bajo", "debajo",
    "contra", "desde", "por", "entre", "junto", "cerca", "hacia", "atrás", "arriba", "abajo",
})
# Lo que puede ir entre el sujeto y la señal: «el auto está muy golpeado».
_PUENTE = frozenset({
    "está", "esta", "estaba", "quedó", "quedo", "sigue", "muy", "re", "todo", "toda",
    "medio", "se", "le", "ya",
})

_PALABRA = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)
_VENTANA = 4


def _dentro_de_pregunta(bajo: str, i: int) -> bool:
    abre = bajo.rfind("¿", 0, i)
    return abre != -1 and "?" not in bajo[abre:i]


def _es_si_afirmativo(bajo: str, inicio: int, fin: int) -> bool:
    """«si» sin tilde usado como «sí»: en el chat la gente escribe «si esta
    tirado en el piso». Cuenta como afirmativo si va seguido de coma, o si
    abre la frase y no hay ninguna pregunta (el condicional típico es «si no
    respira, ¿qué hago?»)."""
    if bajo[fin:fin + 1] == ",":
        return True
    return not bajo[:inicio].strip(" ¡!.,") and "?" not in bajo


def clasificar(texto: str, inicio: int) -> Clase:
    """Clasifica la aparición que empieza en `inicio`."""
    bajo = texto.lower()
    if _dentro_de_pregunta(bajo, inicio):
        return "hipotetico"
    previo = bajo[:inicio]
    cortes = list(_CORTE.finditer(previo))
    if cortes:
        ultimo = cortes[-1]
        if ultimo.group(0) == "si" and not _es_si_afirmativo(bajo, ultimo.start(), ultimo.end()):
            antes_del_si = _PALABRA.findall(previo[: ultimo.start()])
            if not antes_del_si or antes_del_si[-1] not in _ANTES_DE_SI_DUDA:
                return "hipotetico"
        previo = previo[ultimo.end():]
    previo = _NO_NIEGAN.sub(" ", previo)
    # La coma corta: en «No, no hay humo, está inconsciente» el «no» es del
    # humo. Pero si la señal viene justo después de la coma es una lista y
    # hereda la negación: «No hay fuego, humo ni nafta».
    tramos = previo.split(",")
    i = len(tramos) - 1
    while i > 0 and not _PALABRA.findall(tramos[i]):
        i -= 1
    if any(p in _NEGACIONES for p in _PALABRA.findall(tramos[i])[-_VENTANA:]):
        return "negado"
    return "afirmado"


def _ultimo_tramo(texto: str) -> str:
    cortes = list(_CORTE_O_COMA.finditer(texto))
    return texto[cortes[-1].end():] if cortes else texto


def _primer_tramo(texto: str) -> str:
    corte = _CORTE_O_COMA.search(texto)
    return texto[: corte.start()] if corte else texto


def habla_de_objeto(texto: str, inicio: int, fin: int) -> bool:
    """«El celular no responde», «no se mueve la puerta»: el sujeto es una cosa.

    Solo cuenta si la cosa es el sujeto: en «quedó en el auto no responde» o
    «el conductor del auto no responde» el auto es un lugar o un complemento,
    y la señal sigue hablando de una persona."""
    bajo = texto.lower()
    antes = _PALABRA.findall(_ultimo_tramo(bajo[:inicio]))
    j = len(antes) - 1
    while j >= 0 and antes[j] in _PUENTE and len(antes) - 1 - j < 2:
        j -= 1
    if j >= 0 and antes[j] in OBJETOS:
        k = j - 1
        if k >= 0 and antes[k] in _DETERMINANTES:
            k -= 1
        if k < 0 or antes[k] not in _PREPOSICIONES:
            return True
    despues = _PALABRA.findall(_primer_tramo(bajo[fin:]))[:2]
    if despues and despues[0] in _DETERMINANTES:
        despues = despues[1:]
    return bool(despues) and despues[0] in OBJETOS


def _apariciones(bajo: str, frase: str):
    """Posiciones donde `frase` aparece al principio de una palabra."""
    i = bajo.find(frase)
    while i != -1:
        if i == 0 or not bajo[i - 1].isalnum():
            yield i
        i = bajo.find(frase, i + 1)


def buscar(
    texto: str,
    frases: tuple[str, ...] | list[str],
    *,
    aceptar_hipotesis: bool = False,
    respetar_negacion: bool = True,
    descartar_objetos: bool = False,
) -> str | None:
    """La primera frase de `frases` que aparece afirmada en `texto`.

    aceptar_hipotesis: también vale dentro de una pregunta o un «si…» (para
    elegir qué protocolo adjuntar, no para cambiar el estado ni derivar).
    descartar_objetos: ignora apariciones cuyo sujeto es una cosa."""
    bajo = (texto or "").lower()
    for frase in frases:
        for i in _apariciones(bajo, frase):
            if _vale(texto, i, i + len(frase), aceptar_hipotesis, respetar_negacion, descartar_objetos):
                return frase
    return None


def buscar_regex(
    texto: str,
    patron: re.Pattern[str],
    *,
    aceptar_hipotesis: bool = False,
    respetar_negacion: bool = True,
    descartar_objetos: bool = False,
) -> re.Match[str] | None:
    """Como buscar(), para un patrón: la primera coincidencia afirmada."""
    for m in patron.finditer(texto or ""):
        if _vale(texto, m.start(), m.end(), aceptar_hipotesis, respetar_negacion, descartar_objetos):
            return m
    return None


def _vale(texto: str, inicio: int, fin: int, aceptar_hipotesis: bool, respetar_negacion: bool,
          descartar_objetos: bool) -> bool:
    clase = clasificar(texto, inicio)
    if clase == "negado" and respetar_negacion:
        return False
    if clase == "hipotetico" and not aceptar_hipotesis:
        return False
    if descartar_objetos and habla_de_objeto(texto, inicio, fin):
        return False
    return True
