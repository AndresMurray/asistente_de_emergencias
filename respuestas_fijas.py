"""Respuestas fijas para los momentos críticos.

En estos momentos la respuesta no la escribe el modelo: sale de acá, igual
siempre y al instante (no espera al LLM). Son las respuestas que no pueden
fallar, y el modelo, aun con el protocolo adjunto, a veces se salía: a «le scao
el casco» una vez contestó «apoyá una toalla bajo el cuello».

Los textos están redactados a partir de los resúmenes del manual que ya usa el
agente (protocolos.py). Son los primeros que habría que validar con
profesionales.

Solo se usan cuando el turno es claro: un único momento crítico, quien llama
puede llegar al herido y no hay otra urgencia ni otro tema en el mismo turno.
Si no, responde el modelo con el protocolo adjunto, como siempre. El aviso «Ya
estás geolocalizado y la ayuda va en camino.» lo sigue agregando habla.py.
"""

from __future__ import annotations

import re

from triage import TriageState

RCP = (
    "Apoyá el talón de una mano en el centro del pecho, poné la otra encima y comprimí "
    "fuerte y rápido, sin parar. Avisame si se mueve o empieza a respirar."
)
FIJATE_SI_RESPIRA = "Fijate si se le mueve el pecho. ¿Respira?"
CASCO = (
    "No, no le saques el casco ni dejes que nadie se lo saque: puede tener lastimado el cuello. "
    "Mantenele la cabeza y el cuello quietos."
)
# Si vuelve a preguntar: la misma respuesta con otras palabras.
CASCO_OTRA_VEZ = (
    "No, el casco no se saca: lo sacan los médicos cuando llegan. Mantenele la cabeza quieta.",
    "No. Aunque parezca que le molesta, el casco se deja puesto hasta que lleguen los médicos.",
)
OBJETO_CLAVADO = (
    "No le saques el objeto ni lo muevas: dejalo donde está. Si sangra, tapá alrededor "
    "con una tela limpia, sin apretar sobre el objeto."
)

# «¿Le saco el casco?», «¿puedo sacárselo?», «le scao el casco». En pasado
# («ya le saqué el casco») es otra situación: responde el modelo.
_SACAR = re.compile(
    r"\b(saco|sacar|sacarle|sacarlo|sacárselo|sacarselo|sacamos|saca|sacás|sacas|scao|"
    r"quito|quitar|quitarle|quitarlo|quitárselo|quitarselo|quitamos)\b",
    re.IGNORECASE,
)
# Con tilde: «saco» es presente y «sacó», pasado. Sin tilde, solo con «ya».
_YA_SACADO = re.compile(
    r"\b(saqué|sacaron|sacó|quité|quitaron|quitó)\b|"
    r"\bya (le |se lo |se la |lo |la )?(saque|quite|sacamos|quitamos)\b",
    re.IGNORECASE,
)
_PREGUNTA = re.compile(r"¿[^¿?]+\?")


def pide_sacar_casco(texto: str) -> bool:
    return "casco" in texto.lower() and bool(_SACAR.search(texto)) and not _YA_SACADO.search(texto)


def _sin_repetir(opciones: list[str], ultima_respuesta: str) -> str:
    """La primera opción que no repite la última pregunta del agente."""
    previas = set(_PREGUNTA.findall(ultima_respuesta or ""))
    return next((o for o in opciones if not previas & set(_PREGUNTA.findall(o))), opciones[-1])


def _cierre_casco(st: TriageState) -> str:
    if st.consciente is False and st.respira is None:
        opciones = [FIJATE_SI_RESPIRA, "Mirá si el pecho sube y baja: ¿respira?"]
    elif st.respira is True:
        opciones = ["Vigilá que siga respirando y avisame si cambia algo."]
    elif st.consciente:
        opciones = ["¿Se queja de dolor en el cuello?", "Avisame si se queja del cuello o no siente algo."]
    else:
        opciones = ["¿Te responde cuando le hablás?", "¿Está despierto?"]
    return _sin_repetir(opciones, st.ultima_respuesta)


def _cierre_objeto(st: TriageState, sangra: bool) -> str:
    if not sangra:
        opciones = ["¿Le sale mucha sangre alrededor del objeto?"]
    elif st.consciente is None:
        opciones = ["¿Está despierto y te responde?"]
    else:
        opciones = ["Avisame si sale más sangre."]
    return _sin_repetir(opciones, st.ultima_respuesta)


def respuesta_fija(
    texto: str,
    categorias_nuevas: list[str],
    mencionados: list[str],
    nuevos: list[str],
    st: TriageState,
) -> tuple[str, str] | None:
    """(momento, frase) si este turno lleva una respuesta fija.

    categorias_nuevas: categorías de riesgo detectadas por primera vez en este
    turno (triage). mencionados: temas que nombró la persona (protocolos).
    nuevos: temas cuyo protocolo se adjunta por primera vez en este turno.
    `st` ya tiene aplicado el turno."""
    if st.sin_acceso or st.ayuda_llego:
        return None
    nuevas = set(categorias_nuevas)
    temas = set(mencionados)

    if "paro" in nuevas:
        # Atrapado en el auto no se puede comprimir: lo decide el modelo.
        if nuevas - {"paro", "inconsciencia"} or temas - {"rcp"} or st.atrapado:
            return None
        return "rcp", RCP

    if "inconsciencia" in nuevas:
        if nuevas != {"inconsciencia"} or temas - {"rcp"} or st.respira is not None:
            return None
        return "fijate_si_respira", FIJATE_SI_RESPIRA

    if st.respira is False:
        return None  # en plena RCP manda el aviso de RCP

    if "objeto_clavado" in nuevos and nuevas <= {"hemorragia"} and temas <= {"objeto_clavado", "hemorragia"}:
        sangra = "hemorragia" in st.alertas or "hemorragia" in temas
        return "objeto_clavado", f"{OBJETO_CLAVADO} {_cierre_objeto(st, sangra)}"

    if not nuevas and pide_sacar_casco(texto) and temas <= {"casco", "columna"}:
        veces = st.fijas_dadas.get("casco", 0)
        frase = CASCO_OTRA_VEZ[(veces - 1) % len(CASCO_OTRA_VEZ)] if veces else CASCO
        return "casco", f"{frase} {_cierre_casco(st)}"

    return None
