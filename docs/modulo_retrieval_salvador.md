# Módulo de Recuperación Vectorial (Salvador)

**Rama:** `feature/vector-retrieval`
**Archivos:** [`src/retrieval/vector_store.py`](../src/retrieval/vector_store.py), [`src/retrieval/search.py`](../src/retrieval/search.py)

Este documento describe la implementación real (sin mocks) del subsistema de base de
datos vectorial: conexión a PostgreSQL + `pgvector`, generación de embeddings,
inserción de los chunks de Andrés y búsqueda por similitud de coseno.

---

## 1. Stack y decisiones

| Componente | Elección | Motivo |
|---|---|---|
| Base de datos | **PostgreSQL 17** (Homebrew) | estándar del proyecto. |
| Extensión vectorial | **pgvector 0.8.2** | Soporte nativo de `VECTOR` y operadores de distancia + índice HNSW. |
| Modelo de embeddings | **`paraphrase-multilingual`** vía Ollama (~563 MB, **768 dim**) | Multilingüe (español), liviano y orientado a similitud semántica. Se descartó `bge-m3` (1024 dim, ~1.2 GB) por ser innecesariamente pesado. |
| Métrica de similitud | **Distancia de coseno (`<=>`)** | Apropiada para embeddings semánticos normalizados. |
| Índice | **HNSW** (`vector_cosine_ops`, `m=16`, `ef_construction=64`) | Búsqueda aproximada de baja latencia. |

La dimensión del vector es configurable con la variable de entorno `EMBEDDING_DIM`
(por defecto `768`). El modelo y la URL de Ollama se leen de `EMBED_MODEL` y
`OLLAMA_URL`.

---

## 2. Puesta en marcha (entorno local)

```bash
# 1. PostgreSQL + pgvector
brew install postgresql@17 pgvector
brew services start postgresql@17

# 2. Crear rol y base de datos (Homebrew crea el superusuario con tu usuario de OS)
psql -d postgres -c "CREATE ROLE postgres LOGIN SUPERUSER PASSWORD 'postgres';"
psql -d postgres -c "CREATE DATABASE emergencias_db OWNER postgres;"
psql "postgresql://postgres:postgres@localhost:5432/emergencias_db" -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 3. Modelo de embeddings (Ollama)
ollama pull paraphrase-multilingual

# 4. Dependencias Python
pip install -r requirements.txt
```

Variables de entorno relevantes (con sus valores por defecto):

```bash
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/emergencias_db"
OLLAMA_URL="http://localhost:11434"
EMBED_MODEL="paraphrase-multilingual"
EMBEDDING_DIM="768"
```

---

## 3. Esquema de base de datos

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS protocol_chunks (
    id              UUID PRIMARY KEY,
    texto_del_chunk TEXT NOT NULL,
    metadatos       JSONB NOT NULL,
    embedding       VECTOR(768)
);

CREATE INDEX IF NOT EXISTS protocol_chunks_embedding_hnsw_idx
ON protocol_chunks USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

## 4. `VectorStoreManager` (`vector_store.py`)

- **`connect()`** — Abre la conexión con `psycopg2`, crea la extensión `vector` y
  registra el adaptador de tipos (`register_vector`). Si faltan los drivers, cae a
  modo *mock* en memoria para no romper el pipeline de otros integrantes.
- **`initialize_schema()`** — Crea la tabla `protocol_chunks` con `VECTOR(EMBEDDING_DIM)`.
- **`insert_chunks(chunks)`** — Firma original intacta. Genera internamente el embedding
  de cada chunk (vía un `VectorSearcher` creado de forma diferida) y persiste en lote
  con el auxiliar `_persist` (`execute_values` + `ON CONFLICT`).
- **`insert_from_json(json_path)`** — Lee el JSON de Andrés
  (`[{"id", "text", "metadata"}, ...]`), construye los `DocumentChunk` y llama a
  `insert_chunks`. Es el punto de entrada recomendado para la ingesta.
- **`_persist(chunks, embeddings)`** / **`_get_searcher()`** — Auxiliares internos
  (ver sección 6).

## 5. `VectorSearcher` (`search.py`)

- **`get_embeddings(text)`** — Embedding real vía `POST /api/embeddings` de Ollama.
- **`search_similarity(query, limit)`** — Vectoriza la consulta y ejecuta la búsqueda
  real por distancia de coseno (`ORDER BY embedding <=> %s`). Mantiene un fallback
  heurístico por palabras clave cuando la BD está en modo mock.
- **`create_hnsw_index()`** — Crea el índice HNSW de coseno.

### Ejemplo de uso (ingesta + consulta)

```python
from src.retrieval.vector_store import VectorStoreManager
from src.retrieval.search import VectorSearcher

m = VectorStoreManager(); m.connect(); m.initialize_schema()
s = VectorSearcher(m)

m.insert_from_json("data/processed/protocolos_chunks.json")  # ingesta (genera embeddings)
s.create_hnsw_index()

for r in s.search_similarity("¿Qué hago con un herido grave que sangra?", limit=2):
    print(r.metadata.get("fase_protocolo"), "->", r.text[:60])
m.close()
```

---

## 6. Contrato preservado y auxiliares internos

La firma pública **se mantiene igual**:
`insert_chunks(self, chunks)` y `search_similarity(self, query, limit)`.

`insert_chunks` ahora **genera embeddings reales** en
vez de un vector *dummy*. 

Para lograrlo sin cambiar la firma se agregaron dos
auxiliares internos:
- **`_get_searcher()`** — Crea de forma diferida un `VectorSearcher(self)` (import local
  para evitar la dependencia circular con `search.py`). Se usa para vectorizar.
- **`_persist(chunks, embeddings)`** — Hace la inserción/upsert en lote en pgvector con
  los embeddings ya calculados.

Así, la responsabilidad de generar embeddings vive en `VectorSearcher` y la de
persistir en `VectorStoreManager`, pero la interfaz pública no cambia.

---

## 7. Cómo testearlo

### 7.1 Pre-requisitos
Verificá que los servicios estén arriba antes de probar:

```bash
# PostgreSQL corriendo
brew services list | grep postgresql        # debe figurar "started"

# Ollama corriendo y con el modelo de embeddings
ollama list | grep paraphrase-multilingual  # debe aparecer el modelo
curl -s localhost:11434/api/tags >/dev/null && echo "Ollama OK"

# La extensión vector está instalada en la BD
psql "postgresql://postgres:postgres@localhost:5432/emergencias_db" \
  -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
```

### 7.2 Comprobación rápida del modelo de embeddings (768 dim)
```bash
curl -s localhost:11434/api/embeddings \
  -d '{"model":"paraphrase-multilingual","prompt":"prueba de emergencia vial"}' \
  | python3 -c "import sys,json; print('dim =', len(json.load(sys.stdin)['embedding']))"
# Esperado: dim = 768
```

### 7.3 Test end-to-end (ingesta + búsqueda)
Necesitás un JSON de chunks en `data/processed/protocolos_chunks.json` (lo produce
Andrés; si todavía no está, podés crear uno de ejemplo con el formato
`[{"id","text","metadata"}, ...]`). Luego:

```bash
export PYTHONPATH=.
python3 - <<'PY'
from src.retrieval.vector_store import VectorStoreManager
from src.retrieval.search import VectorSearcher

m = VectorStoreManager(); m.connect(); m.initialize_schema()
m.insert_from_json("data/processed/protocolos_chunks.json")
s = VectorSearcher(m); s.create_hnsw_index()

for q in ["¿Cuánto tiempo tienen para llegar al accidente?",
          "¿Qué hago con un herido grave que sangra?"]:
    print("\nQ:", q)
    for r in s.search_similarity(q, limit=2):
        print("  ->", r.metadata.get("fase_protocolo"), "|", r.text[:50])
m.close()
PY
```

Resultado esperado: cada consulta devuelve primero el fragmento de la fase correcta
(p. ej. "ARRIBO AL LUGAR" para la pregunta de tiempos, "INTERVENCION" para la del
herido), confirmando que la similitud de coseno funciona.

### 7.4 Verificar los datos directamente en la BD
```bash
psql "postgresql://postgres:postgres@localhost:5432/emergencias_db" -c \
  "SELECT id, metadatos->>'fase_protocolo' AS fase,
          vector_dims(embedding) AS dims
   FROM protocol_chunks;"
```
Debe listar los chunks insertados con `dims = 768` en todos.

### 7.5 Modo fallback (sin BD)
Si PostgreSQL no está disponible, `connect()` activa el modo mock en memoria y
`search_similarity` usa una heurística por palabras clave. Útil para que el resto del
equipo ejecute el pipeline aunque no tengan la BD levantada:

```bash
export PYTHONPATH=.
python3 src/retrieval/search.py   # corre el __main__ de ejemplo
```

### 7.6 Validador del equipo
Antes de mergear, correr el evaluador general:
```bash
export PYTHONPATH=.
python3 tests_eval/evaluator.py
```
