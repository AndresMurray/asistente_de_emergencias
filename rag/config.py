"""Configuración de retrieval, en un solo lugar.

Antes estaba repartida en os.getenv() por todo agent.py e ingest.py, y los
scripts de metricas/ pisaban DATABASE_URL a mano. Tener un único objeto de
settings es lo que permite que el agente y las métricas midan lo mismo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class RagSettings:
    database_url: str
    cohere_api_key: str

    table: str = "chunks"

    # Fragmentos que terminan en el prompt del LLM.
    top_k: int = 3
    # Candidatos que trae pgvector antes de rerankear. Más alto sube recall y
    # con el índice HNSW cuesta ~2 ms, así que es casi gratis.
    k_vector: int = 20

    # Presupuesto total de la tool de búsqueda. Pasado esto el agente prefiere
    # decir que perdió el manual antes que dejar a la persona esperando.
    # Medido: el caso típico es ~490 ms (Cohere ~250 + pgvector ~230), pero el
    # primer embedding tras un rato inactivo se pasó de 2 s. Con with_filler
    # cubriendo el hueco, 4 s es preferible a fallar una búsqueda real.
    timeout_s: float = 4.0
    # Timeout de la llamada a Cohere. Antes no había ninguno, así que un Cohere
    # lento colgaba el turno indefinidamente.
    embed_timeout_s: float = 2.5

    # Piso de similitud coseno por debajo del cual un fragmento se descarta.
    #
    # Calibrado con medición, y el valor NO es el que parecía a primera vista.
    # Con las 25 queries de metricas/dataset_evaluacion.json (bien escritas) la
    # separación contra 8 consultas fuera de dominio daba limpia, sin solapamiento,
    # y 0.55 parecía obvio. Pero un ciudadano en pánico no habla así: habla corto
    # y sin sintaxis. Midiendo con 13 frases telegráficas reales las
    # distribuciones SÍ se solapan (legítimas desde 0.472, basura hasta 0.518):
    #
    #   piso   rechaza legítimas   pasa basura
    #   0.40        0/13              6/8
    #   0.45        0/13              2/8      <- elegido
    #   0.48        3/13              1/8
    #   0.55        8/13              0/8
    #
    # Con 0.55 el agente le contesta "eso no está en mi manual" a alguien que
    # dice "se desangra" (0.538), "está atrapado" (0.478) o "está convulsionando"
    # (0.488). Inaceptable.
    #
    # El trade-off es asimétrico y por eso el piso va bajo: un falso negativo
    # (rechazar una emergencia real) puede costar una vida; un falso positivo
    # solo trae contexto irrelevante, y de eso ya se encarga la regla de
    # grounding del prompt, que obliga al modelo a rechazar cuando el contexto
    # no responde la pregunta.
    #
    # Esto es exactamente lo que el reranker de Cohere (Fase 4) resuelve bien:
    # sus scores separan mucho mejor que el coseno crudo en frases cortas.
    # Recalibrar después de reingestar: los scores sobre chunks enteros no son
    # comparables con los de chunks cortados a la mitad.
    min_score: float = 0.45

    embed_model: str = "embed-multilingual-v3.0"
    cohere_embed_url: str = "https://api.cohere.ai/v1/embed"


def load_settings() -> RagSettings:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL no está configurada (ver .env.example)")

    cohere_api_key = os.environ.get("COHERE_API_KEY")
    if not cohere_api_key:
        raise ValueError("COHERE_API_KEY no está configurada (ver .env.example)")

    # Los defaults salen de los campos del dataclass, no repetidos acá. Repetirlos
    # ya causó un bug: min_score quedaba en 0.0 y el piso de relevancia no se
    # aplicaba nunca, así que consultas fuera de dominio pasaban como válidas.
    defaults = {f.name: f.default for f in fields(RagSettings)}

    def _env(name: str, field: str, cast):
        raw = os.getenv(name)
        return cast(raw) if raw else defaults[field]

    return RagSettings(
        database_url=database_url,
        cohere_api_key=cohere_api_key,
        table=_env("RAG_TABLE", "table", str),
        top_k=_env("TOP_K", "top_k", int),
        k_vector=_env("RAG_K_VECTOR", "k_vector", int),
        timeout_s=_env("RAG_TIMEOUT_S", "timeout_s", float),
        embed_timeout_s=_env("RAG_EMBED_TIMEOUT_S", "embed_timeout_s", float),
        min_score=_env("RAG_MIN_SCORE", "min_score", float),
    )
