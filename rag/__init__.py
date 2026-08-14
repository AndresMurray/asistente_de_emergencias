"""Retrieval de protocolos de emergencia.

Este paquete existe para que el agente y los scripts de metricas/ importen el
MISMO código. Antes las métricas importaban src.main (Ollama + sentence-
transformers de 768 dims contra la tabla protocol_chunks) mientras el agente
usaba Cohere de 1024 dims contra chunks: medían un sistema que no existía.
"""

from .config import RagSettings, load_settings
from .errors import RetrievalError
from .retriever import RetrievalResult, Retriever, Status
from .store import Fragment

__all__ = [
    "Fragment",
    "RagSettings",
    "RetrievalError",
    "RetrievalResult",
    "Retriever",
    "Status",
    "load_settings",
]
