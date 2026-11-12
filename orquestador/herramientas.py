"""Las tools que puede llamar el LLM, en el formato de la API de OpenAI.

La descripción que lee el modelo y lo que hace cada tool son los mismos que en
el agente de LiveKit: viven en nucleo.py y triage.py. Acá está solo el esquema
de parámetros y el despacho.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from nucleo import DESCRIPCION_BUSCAR_PROTOCOLO, ManualNoDisponible, _elegir_frase_espera, consultar_manual
from triage import DESCRIPCION_REGISTRAR_DATOS, TriageState, registrar_datos

logger = logging.getLogger("orquestador.herramientas")

_TEXTO = ("que_paso", "heridos", "riesgos")
_SI_NO = ("consciente", "respira", "caller_seguro", "atrapado")


def _opcional(tipo: str) -> dict[str, Any]:
    return {"anyOf": [{"type": tipo}, {"type": "null"}], "default": None}


ESQUEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "buscar_protocolo",
            "description": DESCRIPCION_BUSCAR_PROTOCOLO,
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_datos_escena",
            "description": DESCRIPCION_REGISTRAR_DATOS,
            "parameters": {
                "type": "object",
                "properties": {
                    **{campo: _opcional("string") for campo in _TEXTO},
                    **{campo: _opcional("boolean") for campo in _SI_NO},
                },
            },
        },
    },
]

# Si la búsqueda en el manual tarda más que esto, el agente dice una frase de
# espera para que no quede un silencio.
ESPERA_ANTES_DE_AVISAR_S = 0.6


def _si_no(valor: Any) -> bool | None:
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, str):
        bajo = valor.strip().lower()
        if bajo in {"true", "si", "sí", "1"}:
            return True
        if bajo in {"false", "no", "0"}:
            return False
    return None


async def ejecutar(
    nombre: str,
    argumentos: dict[str, Any],
    st: TriageState,
    *,
    al_demorar: Callable[[str], None] | None = None,
) -> str:
    """Corre una tool y devuelve el texto para el LLM. Nunca levanta: un error
    se le informa al modelo, que sigue asistiendo con lo que tiene."""
    try:
        if nombre == "buscar_protocolo":
            consulta = argumentos.get("query")
            if not isinstance(consulta, str) or not consulta.strip():
                return "Falta el texto de la consulta (query)."
            return await _buscar(consulta, st, al_demorar)
        if nombre == "registrar_datos_escena":
            campos: dict[str, Any] = {
                campo: str(argumentos[campo]) for campo in _TEXTO if argumentos.get(campo) is not None
            }
            campos.update({campo: _si_no(argumentos.get(campo)) for campo in _SI_NO})
            return registrar_datos(st, **campos)
    except ManualNoDisponible as exc:
        return str(exc)
    except Exception:
        logger.exception("la tool %s falló", nombre)
        return "La herramienta falló por un problema técnico. Seguí asistiendo con lo que ya sabés."
    return f"La herramienta «{nombre}» no existe."


async def _buscar(consulta: str, st: TriageState, al_demorar: Callable[[str], None] | None) -> str:
    busqueda = asyncio.ensure_future(consultar_manual(consulta, st))
    try:
        listas, _ = await asyncio.wait({busqueda}, timeout=ESPERA_ANTES_DE_AVISAR_S)
        if not listas and al_demorar is not None:
            al_demorar(_elegir_frase_espera(st))
        return await busqueda
    finally:
        if not busqueda.done():
            busqueda.cancel()
