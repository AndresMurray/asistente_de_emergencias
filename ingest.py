"""
Script de ingesta de chunks en pgvector.

Uso: python ingest.py [ruta_al_json]
Por defecto usa: data/processed/protocolos_chunks.json

Puede correrse múltiples veces de forma segura — usa upsert (ON CONFLICT DO UPDATE).
"""
import os
import sys
import json
import re
import requests
import argparse

# ── Configuración ────────────────────────────────────────────────────────────
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5433/emergencias_vdb"
os.environ["OLLAMA_URL"]   = "http://localhost:11434"
os.environ["EMBED_MODEL"]  = "paraphrase-multilingual:latest"

parser = argparse.ArgumentParser(description="Script de ingesta de chunks en pgvector.")
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
BATCH_SIZE = 20  # chunks por commit a pgvector

print(f"[Ingesta] BD  -> {os.environ['DATABASE_URL']}")
print(f"[Ingesta] EMB -> {os.environ['EMBED_MODEL']}")
print(f"[Ingesta] JSON -> {JSON_PATH}")
if RESET_DB:
    print("[Ingesta] RESET activado: se vaciará la base de datos antes de ingestar.")

# ── Imports del proyecto (después de setear env vars) ─────────────────────
from src.retrieval.vector_store import VectorStoreManager
from src.ingestion.chunking import DocumentChunk


# ── Limpieza de texto ────────────────────────────────────────────────────────
def limpiar_texto(texto: str) -> str:
    """
    Limpieza mínima y segura: solo elimina caracteres de control y el
    caracter de reemplazo Unicode. NO re-encodea — eso corrompe UTF-8 válido.
    """
    texto = texto.replace('\ufffd', ' ')
    texto = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', texto)
    texto = re.sub(r'  +', ' ', texto)
    return texto.strip()


# ── Cliente de embeddings (usa /api/embed, el endpoint actual de Ollama) ─────
OLLAMA_URL  = os.environ["OLLAMA_URL"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
EMBED_URL   = f"{OLLAMA_URL}/api/embed"   # endpoint actual (reemplaza /api/embeddings)

def get_embedding(texto: str) -> list:
    """
    Llama al endpoint /api/embed de Ollama (introducido en Ollama 0.1.26).
    Más robusto que /api/embeddings para ciertos tokens del modelo.
    """
    resp = requests.post(
        EMBED_URL,
        json={"model": EMBED_MODEL, "input": texto},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # /api/embed devuelve {"embeddings": [[...]]} (lista de listas)
    embeddings = data.get("embeddings")
    if not embeddings or not embeddings[0]:
        raise ValueError(f"Ollama no devolvio embedding para: '{texto[:50]}...'")
    return embeddings[0]


# ── Carga del JSON ───────────────────────────────────────────────────────────
with open(JSON_PATH, "r", encoding="utf-8", errors="replace") as f:
    data = json.load(f)

chunks = [
    DocumentChunk(
        id=item.get("id"),
        text=limpiar_texto(item["text"]),
        metadata=item.get("metadata", {}),
    )
    for item in data
]
print(f"[Ingesta] {len(chunks)} chunks cargados. Conectando a BD...")


# ── Conexión y esquema ────────────────────────────────────────────────────────
m = VectorStoreManager()
m.connect()
m.initialize_schema()

if RESET_DB:
    m.clear_table()


# ── Inserción en batches con manejo de errores ───────────────────────────────
ok, skipped = 0, 0
batch, batch_embeddings = [], []

for i, chunk in enumerate(chunks):
    try:
        emb = get_embedding(chunk.text)
        batch.append(chunk)
        batch_embeddings.append(emb)

        if len(batch) >= BATCH_SIZE:
            m._persist(batch, batch_embeddings)
            ok += len(batch)
            print(f"  -> {ok}/{len(chunks)} insertados...", flush=True)
            batch, batch_embeddings = [], []

    except Exception as e:
        skipped += 1
        print(f"  [SKIP] Chunk {i} saltado: {str(e)[:100]}")

# Último batch residual
if batch:
    m._persist(batch, batch_embeddings)
    ok += len(batch)

m.close()

print(f"\n[Ingesta] FINALIZADA: {ok} insertados, {skipped} saltados de {len(chunks)} totales.")
if skipped > 0:
    print(f"[Ingesta] {skipped} chunks no pudieron generar embeddings y fueron omitidos.")
print()
print("Para verificar:")
print('  docker exec asistente_de_emergencias-vdb-1 psql -U postgres -d emergencias_vdb -c "SELECT COUNT(*) FROM protocol_chunks;"')
