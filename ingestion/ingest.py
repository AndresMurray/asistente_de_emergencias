"""Ingesta de chunks a pgvector.

Cambios respecto de la versión anterior:

- Embeddings batcheados: Cohere acepta hasta 96 textos por llamada, y antes se
  hacía una llamada HTTP + un INSERT + un COMMIT por chunk, secuencial. Para 174
  chunks eso son 348 round trips contra 2 llamadas y un INSERT.
- Idempotente: content_hash + ON CONFLICT en lugar de TRUNCATE, así arreglar un
  documento no obliga a re-embeber el corpus entero ni a vaciar la tabla.
- La metadata llega a la base. Antes la línea
  `[limpiar_texto(item["text"]) for item in data]` tiraba id y metadata, y por eso
  el agente prefijaba todo con el literal hardcodeado «[GENERAL]».

Uso:
    python -m ingestion.ingest --texto data/processed/corpus_reconstruido.txt --dry-run
    python -m ingestion.ingest --texto data/processed/corpus_reconstruido.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values

from ingestion.chunker import Chunk, chunkear

COHERE_URL = "https://api.cohere.ai/v1/embed"
MODELO = "embed-multilingual-v3.0"
LOTE = 96  # máximo que acepta Cohere por llamada
FUENTE_DEFAULT = "COMPORTAMIENTO-EN-CASO-DE-ACCIDENTE-PRIMEROS-AUXILIOS.pdf"


def content_hash(texto: str, fuente: str) -> str:
    normalizado = " ".join(texto.split()).lower()
    return hashlib.sha256(f"{fuente}\x00{normalizado}".encode()).hexdigest()


def embeber_lote(textos: list[str], api_key: str) -> list[list[float]]:
    respuesta = requests.post(
        COHERE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "texts": textos,
            "model": MODELO,
            # Asimétrico respecto de la consulta, que usa search_query.
            "input_type": "search_document",
            "embedding_types": ["float"],
        },
        timeout=60,
    )
    if respuesta.status_code != 200:
        raise RuntimeError(f"Cohere devolvió {respuesta.status_code}: {respuesta.text[:300]}")
    return respuesta.json()["embeddings"]["float"]


def reporte(chunks: list[Chunk]) -> None:
    largos = [len(c.texto) for c in chunks]
    secciones = {c.seccion for c in chunks}
    temas = sorted({c.tema for c in chunks if c.tema})
    print(f"[ingesta] {len(chunks)} chunks | {len(secciones)} secciones | temas {temas}")
    print(
        f"[ingesta] tamaño: min {min(largos)} · mediana {statistics.median(largos):.0f} "
        f"· p95 {sorted(largos)[int(len(largos) * 0.95)]} · max {max(largos)}"
    )
    paginas = [c.pagina_inicio for c in chunks if c.pagina_inicio]
    if paginas:
        print(f"[ingesta] páginas: {min(paginas)}–{max(paginas)}")


def insertar(chunks: list[Chunk], vectores: list[list[float]], dsn: str, tabla: str) -> int:
    filas = [
        (
            content_hash(c.texto, c.fuente),
            c.texto,
            vector,
            c.fuente,
            c.seccion,
            c.subseccion,
            c.pagina_inicio,
            c.pagina_fin,
            c.orden,
            "es-ES",
            json.dumps(c.metadata(), ensure_ascii=False),
        )
        for c, vector in zip(chunks, vectores)
    ]

    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            execute_values(
                cur,
                f"""
                INSERT INTO {tabla}
                    (content_hash, text, embedding, source, section, subsection,
                     page_start, page_end, ord, locale, metadata)
                VALUES %s
                ON CONFLICT (content_hash) DO UPDATE SET
                    section    = EXCLUDED.section,
                    subsection = EXCLUDED.subsection,
                    page_start = EXCLUDED.page_start,
                    page_end   = EXCLUDED.page_end,
                    ord        = EXCLUDED.ord,
                    metadata   = EXCLUDED.metadata
                """,
                filas,
                template="(%s,%s,%s::vector,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                page_size=100,
            )
            # cur.rowcount solo refleja el último lote de execute_values, así que
            # se cuenta la tabla en lugar de reportar un número engañoso.
            cur.execute(f"SELECT count(*) FROM {tabla};")
            total = int(cur.fetchone()[0])
        conn.commit()
        return total
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--texto", required=True, help="archivo de texto del documento")
    p.add_argument("--fuente", default=FUENTE_DEFAULT, help="nombre del documento origen")
    p.add_argument("--tabla", default="chunks")
    p.add_argument("--dry-run", action="store_true", help="chunkea y reporta, sin tocar la base")
    args = p.parse_args()

    load_dotenv(".env.local")

    with open(args.texto, encoding="utf-8") as f:
        texto = f.read()

    chunks = chunkear(texto, args.fuente)
    for c in chunks:
        c.fuente = args.fuente
    if not chunks:
        sys.exit("ERROR: el chunker no produjo nada")

    reporte(chunks)

    if args.dry_run:
        print("\n[ingesta] --dry-run: no se tocó la base. Primeros 2 chunks:")
        for c in chunks[:2]:
            print(f"\n  [{c.orden}] tema {c.tema} · pág {c.pagina_inicio} · {c.seccion}")
            print(f"      {c.texto[:200]}…")
        return

    api_key = os.getenv("COHERE_API_KEY")
    dsn = os.getenv("DATABASE_URL")
    if not api_key or not dsn:
        sys.exit("ERROR: faltan COHERE_API_KEY o DATABASE_URL (ver .env.example)")

    vectores: list[list[float]] = []
    inicio = time.monotonic()
    for i in range(0, len(chunks), LOTE):
        lote = chunks[i : i + LOTE]
        vectores.extend(embeber_lote([c.texto for c in lote], api_key))
        print(f"[ingesta] embebidos {len(vectores)}/{len(chunks)}", flush=True)

    if len(vectores) != len(chunks):
        sys.exit(f"ERROR: {len(vectores)} vectores para {len(chunks)} chunks")

    total = insertar(chunks, vectores, dsn, args.tabla)
    print(
        f"[ingesta] LISTO: la tabla '{args.tabla}' quedó con {total} filas "
        f"({len(chunks)} chunks procesados) en {time.monotonic() - inicio:.1f}s "
        f"({(len(chunks) + LOTE - 1) // LOTE} llamadas a Cohere, 1 INSERT)"
    )


if __name__ == "__main__":
    main()
