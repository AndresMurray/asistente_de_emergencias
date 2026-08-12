import os
import sys
import json
import re
import argparse
import requests
import psycopg2
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(".env.local")

parser = argparse.ArgumentParser(description="Script de ingesta de chunks en pgvector (Cohere API).")
parser.add_argument(
    "json_path",
    nargs="?",
    default="data/processed/protocolos_chunks.json",
    help="Ruta al archivo JSON de chunks (por defecto: data/processed/protocolos_chunks.json)"
)
parser.add_argument(
    "--reset",
    action="store_true",
    help="Vacía la tabla de chunks antes de realizar la ingesta."
)
args = parser.parse_args()

JSON_PATH  = args.json_path
RESET_DB   = args.reset

DB_URL = os.getenv("DATABASE_URL")
COHERE_KEY = os.getenv("COHERE_API_KEY")

print(f"[Ingesta] BD  -> Supabase (chunks table)")
print(f"[Ingesta] EMB -> Cohere embed-multilingual-v3.0 (1024 dims)")
print(f"[Ingesta] JSON -> {JSON_PATH}")

if not COHERE_KEY:
    print("ERROR: COHERE_API_KEY no encontrada en .env.local")
    sys.exit(1)

if not DB_URL:
    print("ERROR: DATABASE_URL no encontrada en .env.local")
    sys.exit(1)

def limpiar_texto(texto: str) -> str:
    texto = texto.replace('\ufffd', ' ')
    texto = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', texto)
    texto = re.sub(r'  +', ' ', texto)
    return texto.strip()

def get_embedding(texto: str) -> list:
    response = requests.post(
        "https://api.cohere.ai/v1/embed",
        headers={
            "Authorization": f"Bearer {COHERE_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        json={
            "texts": [texto],
            "model": "embed-multilingual-v3.0",
            "input_type": "search_document",
            "embedding_types": ["float"]
        }
    )
    if response.status_code != 200:
        raise Exception(f"Error API Cohere: {response.text}")
    return response.json()["embeddings"]["float"][0]

with open(JSON_PATH, "r", encoding="utf-8", errors="replace") as f:
    data = json.load(f)

# Extraemos solo el texto del json
chunks_to_ingest = [limpiar_texto(item["text"]) for item in data if "text" in item]

print(f"[Ingesta] {len(chunks_to_ingest)} chunks cargados. Conectando a BD...")

conn = psycopg2.connect(DB_URL)
register_vector(conn)

with conn.cursor() as cur:
    if RESET_DB:
        print("[Ingesta] Vaciando la tabla 'chunks'...")
        cur.execute("TRUNCATE TABLE chunks RESTART IDENTITY;")
        conn.commit()

ok, skipped = 0, 0

for i, text in enumerate(chunks_to_ingest):
    try:
        emb = get_embedding(text)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chunks (text, embedding)
                VALUES (%s, %s)
                """,
                (text, emb)
            )
        conn.commit()
        ok += 1
        print(f"  -> {ok}/{len(chunks_to_ingest)} insertados...", flush=True)
    except Exception as e:
        conn.rollback()
        skipped += 1
        print(f"  [SKIP] Chunk {i} saltado: {str(e)[:100]}")

conn.close()

print(f"\n[Ingesta] FINALIZADA: {ok} insertados, {skipped} saltados.")
