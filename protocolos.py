"""Temas de primeros auxilios que el agente tiene que resolver sin fallar.

Cada tema tiene:
- palabras con que lo dice una persona común (para detectarlo en lo que dijo),
- la consulta canónica al manual (precalculada en rag/cache_consultas.json, así
  que en vivo sale en 0 ms y sin depender de Google ni Cohere),
- un texto de respaldo, redactado a partir de los fragmentos del manual, para el
  caso extremo en que el retrieval falle igual (base caída, índice sin cargar).

Con esto la maniobra que salva la vida nunca depende de tres servicios externos
funcionando a la vez. Antes, un 429 de Google hacía que el agente contestara
«perdí el acceso al manual» a alguien con una persona que no respira.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag.retriever import normalizar_consulta


@dataclass(frozen=True)
class Tema:
    clave: str
    consulta: str
    palabras: tuple[str, ...]
    respaldo: str


TEMAS: dict[str, Tema] = {}


def _tema(clave: str, consulta: str, palabras: tuple[str, ...], respaldo: str) -> None:
    TEMAS[clave] = Tema(clave, consulta, palabras, respaldo)


# El orden importa: es el orden de prioridad cuando en un mismo turno aparecen
# varios temas (se inyectan como máximo dos).
_tema(
    "rcp",
    "herido inconsciente que no respira reanimación cardiopulmonar",
    ("no respira", "no está respirando", "no esta respirando", "dejó de respirar",
     "dejo de respirar", "no tiene pulso", "reanimación", "reanimacion", "rcp",
     "compresiones", "comprimiendo", "comprimir"),
    (
        'Herido inconsciente que no respira: arrodillarse al lado de la víctima a la altura del pecho. Colocar el talón de una mano en el centro del pecho y la otra mano encima, con los dedos entrelazados, sin apoyar sobre las costillas ni sobre la parte alta de la panza. Con los brazos rectos, comprimir hundiendo el pecho unos cuatro o cinco centímetros y soltar sin despegar las manos, a un ritmo de casi dos compresiones por segundo. No parar hasta que llegue la ayuda o la persona empiece a respirar.'
    ),
)
_tema(
    "inconsciente_respira",
    "herido inconsciente que respira posición lateral de seguridad",
    (),  # se activa por estado (inconsciente y respira), no por palabras
    (
        'Herido inconsciente que respira: por ser un accidente de tránsito, tratarlo como si tuviera una lesión en la columna, sin moverlo y manteniendo alineados cabeza, cuello y tronco. Mantener abierto el paso del aire con la maniobra frente-mentón mientras siga inconsciente, comprobar cada tanto que sigue respirando y no dejarlo solo. Solo ponerlo de costado (posición lateral de seguridad) si empieza a vomitar o a sangrar por la boca, o si hay que dejarlo solo para pedir ayuda.'
    ),
)
_tema(
    "hemorragia",
    "control de hemorragias externas",
    ("sangra", "sangre", "sangrando", "desangra", "hemorragia", "herida abierta",
     "corte profundo", "tajo"),
    (
        'Hemorragia externa: la medida más efectiva es apretar fuerte y directo con la mano sobre el punto que sangra, poniendo en el medio una gasa o una prenda limpia, sin soltar. Atender primero la sangre que sale rápido o a chorro. No tapar la sangre que sale por oídos, nariz o boca después de un golpe: puede venir de una lesión grave en la cabeza.'
    ),
)
_tema(
    "fuego",
    "incendio del vehículo humo combustible derramado",
    ("fuego", "incendio", "humo", "llamas", "se prendió", "se prendio",
     "combustible", "nafta", "gasoil", "olor a quemado"),
    (
        'Riesgo de incendio: es extremadamente peligroso quedarse en la calzada o acercarse a un vehículo en llamas o con combustible derramado; alejarse. El incendio o el riesgo elevado de incendio es uno de los pocos casos en que se justifica mover a un herido, siempre manteniendo alineados cabeza, cuello y tronco y solo si se puede sin ponerse en peligro. Si se prende la ropa de una persona, taparla con una manta o algo similar para apagar el fuego.'
    ),
)
_tema(
    "atrapado",
    "movilización de heridos accidente vehículo",
    ("atrapad", "aplastad", "prensad", "aprisionad", "encerrad", "trabad",
     "no puede salir", "no pueden salir", "no logra salir",
     "lo saco", "la saco", "sacarlo", "sacarla", "lo muevo", "la muevo",
     "moverlo", "moverla"),
    (
        'Heridos dentro del vehículo: como norma general no se debe mover a los heridos ni sacarlos del vehículo. Solo se justifica si hay incendio o riesgo elevado de incendio, riesgo de un nuevo accidente o necesidad de reanimación. Sacarlos sin las condiciones adecuadas puede provocar o agravar lesiones de la columna. Si no hay más remedio que moverlo, mantener alineados cabeza, cuello y tronco.'
    ),
)
_tema(
    "columna",
    "lesión de columna vertebral cuello no mover al herido inmovilizar",
    ("cuello", "columna", "espalda", "nuca", "no siente las piernas",
     "no siente los brazos", "no puede mover las piernas", "no puede moverse",
     "no siente el cuerpo"),
    (
        "Posible lesión de columna (dolor de cuello o espalda, no siente o no puede mover alguna "
        "parte del cuerpo, golpe por encima de los hombros): no moverlo ni dejar que se mueva, y "
        "mantener quietos y alineados cabeza, cuello y tronco hasta que llegue la ayuda. No "
        "trasladarlo en un auto particular."
    ),
)
_tema(
    "casco",
    "accidente moto retirar el casco columna cervical",
    ("casco",),
    (
        'Motociclista: como norma general no se le debe quitar el casco ni permitir que alguien se lo quite, para no agravar una lesión en el cuello. Solo se retira si hace falta para atender la respiración y con ayuda especializada. Mantener quieta la zona del cuello.'
    ),
)
_tema(
    "quemadura",
    "quemaduras primeros auxilios",
    ("quemad", "quemó", "quemo", "quema"),
    (
        'Quemaduras: si la ropa sigue prendida, taparla con una manta para apagar el fuego, sin echar agua ni extintor directo sobre el cuerpo. Enfriar la zona quemada con agua fría. No tocar la zona, no sacar la ropa pegada a la piel ni reventar ampollas. Cubrir con una tela limpia humedecida. Si la quemadura es en la cara, vigilar que respire bien.'
    ),
)
_tema(
    "fractura",
    "fracturas inmovilización del miembro",
    ("hueso roto", "fractur", "quebr", "se le dobló", "se le doblo", "hueso afuera"),
    (
        'Posible hueso roto: no intentar acomodarlo. Si hay herida, taparla y frenar el sangrado. Inmovilizar la zona sujetándola por encima y por debajo de la lesión; en el brazo, con un cabestrillo hecho con una tela o un pañuelo.'
    ),
)
_tema(
    "seguridad_escena",
    "proteger la zona del accidente señalizar chaleco triángulos",
    ("mover el auto", "muevo el auto", "correr el auto", "corro el auto",
     "triángulo", "triangulo", "balizas", "señaliz", "chaleco"),
    (
        'Proteger el lugar: señalizar cuanto antes con los triángulos, encender las balizas y las luces, dejar el auto propio en un lugar seguro, usar chaleco reflectante y no quedarse en la calzada. Fijarse si hay riesgo de incendio o manchas de combustible. No sacar a los heridos de los vehículos salvo que esté claramente indicado.'
    ),
)

# Convulsiones NO es un tema: el manual no lo trata y el retrieval devolvía el
# fragmento de RCP con relevancia 0.27. Inyectarlo sería peligroso.

# Consultas que el prompt le enseña al modelo a usar. Van al caché aunque no
# sean de un tema, así la tool buscar_protocolo también sale en 0 ms.
CONSULTAS_EXTRA = (
    "herido inconsciente que no respira reanimación cardiopulmonar",
    "control de hemorragias externas",
    "accidente moto retirar el casco columna cervical",
    "movilización de heridos accidente vehículo",
    "posición lateral de seguridad",
    "shock",
)


def consultas_canonicas() -> list[str]:
    return list(dict.fromkeys([t.consulta for t in TEMAS.values()] + list(CONSULTAS_EXTRA)))


# --- detección ---------------------------------------------------------------

_RESPIRA_SI = re.compile(
    # «sí respira» solo con tilde: sin tilde, «no sé si respira» daría positivo.
    r"(?<!no )\b(est[aá] respirando|sí respira|respira bien|respira normal|"
    r"se le mueve el pecho|sigue respirando|empezó a respirar|empezo a respirar|"
    r"volvió a respirar|volvio a respirar|respira de nuevo)"
)


def respira_positivo(texto: str) -> bool:
    """«Sí, se le mueve el pecho», «está respirando». Evita «no está respirando»."""
    bajo = texto.lower()
    return bool(_RESPIRA_SI.search(bajo)) and not re.search(
        r"\bno (est[aá] respirando|se le mueve el pecho|respira)", bajo
    )


def detectar_temas(texto: str) -> list[str]:
    """Temas mencionados en lo que dijo la persona, en orden de prioridad."""
    bajo = texto.lower()
    return [
        t.clave for t in TEMAS.values() if t.palabras and any(p in bajo for p in t.palabras)
    ]


def tema_de_consulta(consulta: str) -> Tema | None:
    """Si la consulta del modelo es claramente de un tema, el tema.

    Se usa en buscar_protocolo para responder con el resultado canónico (0 ms)
    en lugar de embeber una consulta nueva."""
    clave = normalizar_consulta(consulta)
    for t in TEMAS.values():
        if clave == normalizar_consulta(t.consulta):
            return t
    temas = detectar_temas(consulta)
    return TEMAS[temas[0]] if len(temas) == 1 else None
