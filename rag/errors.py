"""Errores de retrieval.

Existe para que el agente pueda distinguir "el manual no cubre esto" de "la
búsqueda se rompió". Antes los dos caminos devolvían "" y el agente le decía a
alguien con un herido que no existía el procedimiento.
"""

from __future__ import annotations


class RetrievalError(Exception):
    """La búsqueda falló por una causa técnica (embedding, base, timeout).

    No significa que no haya protocolo: significa que no pudimos consultarlo.
    """
