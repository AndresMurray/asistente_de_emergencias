"""Utilidades de texto del orquestador: oraciones para el TTS y fin de frase."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

_FIN_DE_ORACION = re.compile(r"[.!?…]+[\"»”)]*\s*$")


def parece_completa(texto: str) -> bool:
    """La frase termina en punto, signo de pregunta o de exclamación.

    Deepgram puntúa lo que transcribe, así que sirve de pista barata de que la
    persona terminó de hablar («Sí.») o quedó a mitad de camino («Sí, pero»)."""
    return bool(_FIN_DE_ORACION.search(texto))


def contar_palabras(texto: str) -> int:
    return len(texto.split())


async def por_oraciones(tramos: AsyncIterator[str], *, minimo: int = 12) -> AsyncIterator[str]:
    """Junta los tramos del LLM en oraciones completas para el TTS.

    Una oración entera suena mejor que tres pedazos cortados en las comas. El
    mínimo evita mandar sola una oración muy corta («Sí.») cuando enseguida
    viene el resto."""
    pendiente = ""
    async for tramo in tramos:
        pendiente += tramo
        if parece_completa(pendiente) and len(pendiente.strip()) >= minimo:
            yield pendiente.strip()
            pendiente = ""
    if pendiente.strip():
        yield pendiente.strip()
