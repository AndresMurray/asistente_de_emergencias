"""Precalcula rag/cache_consultas.json: embedding + ranking rerankeado de las
consultas canónicas (protocolos.consultas_canonicas()).

Por qué offline: en vivo el embedding de Google falla con 429 en ~70% de las
llamadas del plan gratuito y el reranker de Cohere (Trial) admite 10 llamadas
por minuto. Acá se puede reintentar y esperar todo lo necesario; en la llamada,
las consultas críticas salen del archivo en 0 ms.

Correrlo de nuevo después de cada reingesta (si el corpus cambió, el agente
detecta que los rankings no coinciden y los ignora, pero pierde el 0 ms):

    python -m ingestion.cache_consultas            # genera y guarda
    python -m ingestion.cache_consultas --mostrar  # además imprime los fragmentos
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import logging
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(".env.local")

from protocolos import consultas_canonicas  # noqa: E402
from rag import load_settings  # noqa: E402
from rag.embeddings import embed_query  # noqa: E402
from rag.retriever import CACHE_PATH, Retriever, normalizar_consulta  # noqa: E402
from rag.session import close_fallback  # noqa: E402


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mostrar", action="store_true", help="imprimir los fragmentos de cada consulta")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)

    settings = dataclasses.replace(load_settings(), timeout_s=120.0, rerank_timeout_s=15.0)
    retriever = Retriever(settings, esperar_rerank=True, cache_path=None)
    retriever.connect()

    consultas = consultas_canonicas()
    faltan = []
    try:
        for consulta in consultas:
            try:
                vector = await embed_query(consulta, settings, intentos=20, pausa_s=2.0)
            except Exception as exc:
                print(f"✗ sin embedding: {consulta} ({exc})")
                faltan.append(consulta)
                continue
            retriever._guardar_embedding(normalizar_consulta(consulta), vector)
            res = await retriever.search(consulta)
            marca = "✓" if res.status == "ok" and res.reranked else "~"
            print(f"{marca} {consulta}  [{res.status}, rerank={res.reranked}, top={res.top_score}]")
            if args.mostrar:
                for f in res.fragments:
                    print(f"    · {f.cita()}\n      {f.text[:700]}\n")
    finally:
        await close_fallback()

    salida = retriever.exportar_cache(consultas)
    CACHE_PATH.write_text(json.dumps(salida, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(salida['consultas'])}/{len(consultas)} consultas guardadas en {CACHE_PATH}")
    return 1 if faltan else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
