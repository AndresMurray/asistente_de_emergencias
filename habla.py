"""Correcciones determinísticas del texto antes de que se hable.

El prompt ya pide voseo y lenguaje llano, pero el modelo se desliza: en las
pruebas dijo «abrí la vía aérea» (jerga que el prompt prohíbe) y «solo verifica
si respira» (imperativo neutro en vez de «verificá»). Para una persona asustada
esas cosas importan, y no conviene depender de que el modelo obedezca.

Se aplica en Assistant.llm_node, así que corrige a la vez lo que se habla, lo
que se transcribe y lo que queda en el historial.
"""

from __future__ import annotations

import re

# Jerga -> palabras de todos los días. De lo más específico a lo más general,
# para que «la vía aérea abierta» no quede como «el paso del aire abierta».
_JERGA: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bla v[íi]a a[ée]rea (abierta|libre|permeable)\b", re.I), r"el paso del aire \1"),
    (re.compile(r"\bla v[íi]a a[ée]rea\b", re.I), "el paso del aire"),
    (re.compile(r"\bv[íi]a a[ée]rea\b", re.I), "paso del aire"),
    (re.compile(r"\bel paso del aire abierta\b", re.I), "el paso del aire abierto"),
    (re.compile(r"\bpermeable\b", re.I), "libre"),
    # El modelo a veces usa guiones Unicode (‐ ‑ –) en lugar del ASCII.
    (re.compile(r"\bfrente\s*[-‐‑–]?\s*ment[óo]n\b", re.I), "frente y mentón"),
    (re.compile(r"\buna fractura\b", re.I), "un hueso roto"),
    (re.compile(r"\bfracturas\b", re.I), "huesos rotos"),
    (re.compile(r"\bfractura\b", re.I), "hueso roto"),
    (re.compile(r"\bmasaje card[íi]aco\b", re.I), "compresiones en el pecho"),
    (re.compile(r"\bcompresiones tor[áa]cicas\b", re.I), "compresiones en el pecho"),
    (re.compile(
        r"\b(?:a )?(?:ciento|cien|100)\s*(?:a|-|y)\s*(?:ciento veinte|120)(?: compresiones)?(?: por minuto)?",
        re.I,
    ), "dos veces por segundo"),
    (re.compile(r"\b1\s*1\s*2\b|\bciento doce\b", re.I), "nueve once"),
]

# Imperativo neutro -> voseo. Solo en posición de orden (inicio de oración o
# después de «y», «solo», «ahora»...), porque «verifica» también puede ser
# tercera persona («el sistema verifica»).
_VOSEO = {
    "pon": "poné", "haz": "hacé", "ten": "tené", "sal": "salí",
    "mantén": "mantené", "manten": "mantené", "mantene": "mantené",
    "mantente": "mantenete", "mantenete": "mantenete", "comprime": "comprimí",
    "presiona": "presioná", "aprieta": "apretá", "apoya": "apoyá",
    "verifica": "verificá", "revisa": "revisá", "mira": "mirá", "fíjate": "fijate",
    "quédate": "quedate", "aléjate": "alejate", "tranquilízate": "tranquilizate",
    "escucha": "escuchá", "llama": "llamá", "coloca": "colocá", "cubre": "cubrí",
    "evita": "evitá", "espera": "esperá", "intenta": "intentá",
    "acuéstalo": "acostalo", "acuéstala": "acostala",
    "avísame": "avisame", "dime": "decime", "cuéntame": "contame",
    "arrodíllate": "arrodillate", "acércate": "acercate", "abre": "abrí",
    "quedá": "quedate",
}
# Fuera de la lista a propósito: «respira», «sigue», «continúa». Al
# inicio de una pregunta son tercera persona («¿Respira?», «¿Sigue sangrando?»)
# y convertirlas en «¿Respirá?» cambiaría el sentido de la pregunta crítica.
_VOSEO_RE = re.compile(
    r"(^\s*|[.!¡,:;]\s*|\b(?:y|solo|sólo|ahora|primero|luego|después|entonces|tranquilo|tranquila)\s+)"
    r"(" + "|".join(sorted(map(re.escape, _VOSEO), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _voseo(m: re.Match[str]) -> str:
    palabra = m.group(2)
    nueva = _VOSEO[palabra.lower()]
    if palabra[0].isupper():
        nueva = nueva[0].upper() + nueva[1:]
    return m.group(1) + nueva


def normalizar_habla(texto: str) -> str:
    for patron, reemplazo in _JERGA:
        texto = patron.sub(reemplazo, texto)
    return _VOSEO_RE.sub(_voseo, texto)


# --- aviso de despacho al 911 ---------------------------------------------------
#
# Para la demo, cuando el sistema deriva (heridos o riesgo de vida) quien llama
# tiene que escuchar que ya fue geolocalizado y que la ayuda va en camino. Antes
# lo decía el modelo "si se acordaba", y en las pruebas a veces no lo decía
# (hemorragia, paro). Ahora lo pone el sistema: una sola vez por llamada, al
# principio de la primera respuesta después de derivar.

FRASE_911 = "Ya estás geolocalizado y la ayuda va en camino."

_MENCION_911 = re.compile(r"geolocaliz|ayuda (ya )?(va|viene|est[aá]) en camino|la ayuda viene", re.I)
_QUITAR_911 = [
    re.compile(r"\b(ya )?est[aá]s geolocalizad[oa]\s*(y\s*|[,;.]\s*)?", re.I),
    re.compile(r"\b(y )?la ayuda (ya )?(va|viene|est[aá]) en camino\s*[.,;]?\s*", re.I),
    re.compile(r"\b(y )?la ayuda viene\s*[.,;]?\s*", re.I),
]


def menciona_aviso_911(texto: str) -> bool:
    return bool(_MENCION_911.search(texto))


def quitar_aviso_911(texto: str) -> str:
    """Saca «ya estás geolocalizado / la ayuda va en camino» si el modelo lo
    repite: la frase ya la dijo el sistema y repetirla en cada turno cansa."""
    limpio = texto
    for patron in _QUITAR_911:
        limpio = patron.sub("", limpio)
    if limpio == texto:
        return texto
    limpio = limpio.lstrip(" ,;.")
    if not limpio.strip():
        return ""
    # Si se cortó el principio de la oración, recuperar la mayúscula.
    if texto[:1].isupper() and limpio[:1].islower():
        limpio = limpio[0].upper() + limpio[1:]
    return (" " if texto[:1] == " " else "") + limpio


def aplicar_aviso_911(texto: str, st) -> str:
    """Aplica el aviso a un tramo de texto de la respuesta.

    `st` es el TriageState: usa `derivado` y `aviso_911_dicho`."""
    if not texto.strip():
        return texto
    if st.derivado and not st.aviso_911_dicho:
        st.aviso_911_dicho = True
        if menciona_aviso_911(texto):
            return texto
        return f"{FRASE_911} {texto.lstrip()}"
    if st.aviso_911_dicho:
        return quitar_aviso_911(texto)
    return texto


# Se corta el stream en signos de puntuación: ningún patrón de arriba cruza una
# coma o un punto, así que cada tramo se puede corregir por separado sin
# romper una frase a la mitad. A ~300 tokens/s de Groq, esperar hasta la primera
# coma agrega unas decenas de milisegundos.
_CORTE = re.compile(r"[.!?,;:\n]")


class NormalizadorStream:
    """Acumula texto del LLM y lo devuelve corregido de a tramos completos."""

    def __init__(self) -> None:
        self._buffer = ""

    def push(self, delta: str) -> str:
        self._buffer += delta
        ultimo = None
        for m in _CORTE.finditer(self._buffer):
            ultimo = m
        if ultimo is None:
            return ""
        listo, self._buffer = self._buffer[: ultimo.end()], self._buffer[ultimo.end():]
        return normalizar_habla(listo)

    def flush(self) -> str:
        listo, self._buffer = self._buffer, ""
        return normalizar_habla(listo) if listo else ""
