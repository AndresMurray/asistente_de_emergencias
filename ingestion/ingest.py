"""Ingesta de chunks a pgvector.

Soporta Google text-embedding-004 (768d) y Cohere embed-multilingual-v3.0 (1024d).

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

GEMINI_BATCH_URL = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents"
COHERE_URL = "https://api.cohere.ai/v1/embed"
LOTE = 90  # máximo seguro para Google y Cohere
FUENTE_DEFAULT = "COMPORTAMIENTO-EN-CASO-DE-ACCIDENTE-PRIMEROS-AUXILIOS.pdf"


def content_hash(texto: str, fuente: str) -> str:
    normalizado = " ".join(texto.split()).lower()
    return hashlib.sha256(f"{fuente}\x00{normalizado}".encode()).hexdigest()


def asegurar_esquema(conn, tabla: str, dim: int = 768) -> None:
    """Asegura que la tabla tenga las columnas y restricciones necesarias con la dimensión vectorial exacta."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s;
            """,
            (tabla,),
        )
        cols = {r[0] for r in cur.fetchall()}
        if not cols:
            # La tabla no existe, la creamos completa con vector(dim)
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {tabla} (
                    id BIGSERIAL PRIMARY KEY,
                    content_hash TEXT NOT NULL UNIQUE,
                    text TEXT NOT NULL,
                    embedding VECTOR({dim}) NOT NULL,
                    source TEXT,
                    section TEXT,
                    subsection TEXT,
                    page_start INT,
                    page_end INT,
                    ord INT NOT NULL DEFAULT 0,
                    locale TEXT NOT NULL DEFAULT 'es-ES',
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE INDEX IF NOT EXISTS {tabla}_embedding_hnsw 
                ON {tabla} USING hnsw (embedding vector_cosine_ops);
                """
            )
            return

        if "content_hash" not in cols:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS content_hash TEXT;")
            cur.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {tabla}_content_hash_key;")
            cur.execute(f"ALTER TABLE {tabla} ADD CONSTRAINT {tabla}_content_hash_key UNIQUE (content_hash);")
        if "ord" not in cols:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS ord INT NOT NULL DEFAULT 0;")
        if "locale" not in cols:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS locale TEXT NOT NULL DEFAULT 'es-ES';")
        if "metadata" not in cols:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb;")
        
        # Asegurar tipo de dimensión de columna embedding
        cur.execute(
            f"ALTER TABLE {tabla} ALTER COLUMN embedding TYPE VECTOR({dim});"
        )
    conn.commit()


def embeber_lote_gemini(textos: list[str], api_key: str) -> list[list[float]]:
    # Modelos activos en la cuenta
    modelos_prioritarios = [
        "gemini-embedding-001",
        "gemini-embedding-2",
        "gemini-embedding-2-preview",
        "text-embedding-004",
    ]

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }

    modelo_elegido = None
    for mod in modelos_prioritarios:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:embedContent?key={api_key}"
        payload = {
            "model": f"models/{mod}",
            "content": {"parts": [{"text": "test"}]},
        }
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            modelo_elegido = mod
            break

    if not modelo_elegido:
        raise RuntimeError("No se pudo conectar con ningún modelo de embeddings disponible en Google AI.")

    vectores = []
    for t in textos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo_elegido}:embedContent?key={api_key}"
        payload = {
            "model": f"models/{modelo_elegido}",
            "content": {"parts": [{"text": t}]},
            "taskType": "RETRIEVAL_DOCUMENT",
            "outputDimensionality": 768,
        }
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        if res.status_code != 200:
            raise RuntimeError(f"Google AI ({modelo_elegido}) devolvió {res.status_code}: {res.text[:300]}")
        vectores.append(res.json()["embedding"]["values"])

    return vectores





def embeber_lote_cohere(textos: list[str], api_key: str) -> list[list[float]]:
    respuesta = requests.post(
        COHERE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "texts": textos,
            "model": "embed-multilingual-v3.0",
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

    dim = len(vectores[0]) if vectores else 768
    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        asegurar_esquema(conn, tabla, dim=dim)
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
            cur.execute(
                f"DELETE FROM {tabla} WHERE source = ANY(%s) AND content_hash <> ALL(%s);",
                (sorted({c.fuente for c in chunks}), [f[0] for f in filas]),
            )
            obsoletos = cur.rowcount
            if obsoletos:
                print(f"[ingesta] {obsoletos} chunk(s) obsoleto(s) borrado(s)")
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
    load_dotenv(".env.local")

    default_table = os.getenv("RAG_TABLE", "chunks_gemini")

    posibles_rutas = [
        "data/processed/clean/COMPORTAMIENTO-EN-CASO-DE-ACCIDENTE-PRIMEROS-AUXILIOS_clean.txt",
        "data/processed/corpus_reconstruido.txt",
        "data/processed/corpus_limpio.txt",
    ]
    ruta_default = next((r for r in posibles_rutas if os.path.exists(r)), posibles_rutas[0])

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--texto", default=ruta_default, help=f"archivo de texto del documento (default: {ruta_default})")
    p.add_argument("--fuente", default=FUENTE_DEFAULT, help="nombre del documento origen")
    p.add_argument("--tabla", default=default_table, help=f"tabla destino (default: {default_table})")
    p.add_argument("--dry-run", action="store_true", help="chunkea y reporta, sin tocar la base")
    args = p.parse_args()

    if not os.path.exists(args.texto):
        sys.exit(f"ERROR: no se encontró el archivo de texto: {args.texto}")

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

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    cohere_key = os.getenv("COHERE_API_KEY")
    dsn = os.getenv("DATABASE_URL")

    if not dsn:
        sys.exit("ERROR: falta DATABASE_URL en .env.local")

    if not gemini_key and not cohere_key:
        sys.exit("ERROR: falta GEMINI_API_KEY (o COHERE_API_KEY) en .env.local")

    usar_gemini = bool(gemini_key)
    proveedor = "Google text-embedding-004 (768d)" if usar_gemini else "Cohere embed-multilingual-v3.0 (1024d)"
    print(f"[ingesta] usando proveedor de embeddings: {proveedor} hacia tabla '{args.tabla}'")

    vectores: list[list[float]] = []
    inicio = time.monotonic()
    for i in range(0, len(chunks), LOTE):
        lote = chunks[i : i + LOTE]
        textos_lote = [c.texto for c in lote]
        if usar_gemini:
            vectores.extend(embeber_lote_gemini(textos_lote, gemini_key))
        else:
            vectores.extend(embeber_lote_cohere(textos_lote, cohere_key))
        print(f"[ingesta] embebidos {len(vectores)}/{len(chunks)}", flush=True)

    if len(vectores) != len(chunks):
        sys.exit(f"ERROR: {len(vectores)} vectores para {len(chunks)} chunks")

    total = insertar(chunks, vectores, dsn, args.tabla)
    print(
        f"[ingesta] LISTO: la tabla '{args.tabla}' quedó con {total} filas "
        f"({len(chunks)} chunks procesados) en {time.monotonic() - inicio:.1f}s"
    )


if __name__ == "__main__":
    main()

