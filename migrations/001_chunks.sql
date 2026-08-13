-- Esquema de la tabla `chunks`.
--
-- Contexto: la tabla actual se creó a mano en la consola de Supabase y no había
-- DDL en el repo. Hoy es `chunks(id integer, text text, embedding)` sin metadata
-- y SIN ÍNDICE VECTORIAL (solo el btree del primary key).
--
-- NO CORRAS ESTE ARCHIVO ENTERO DE UNA. Son dos partes con riesgos distintos.

-- ============================================================================
-- PARTE 1 — Seguro de correr AHORA, no destructivo, no rompe nada.
-- Agrega el índice vectorial que falta sobre la tabla que ya existe.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- Honestidad sobre lo que gana esto HOY: nada medible. Con EXPLAIN ANALYZE, el
-- seq scan sobre las 288 filas tarda 2,7 ms del lado del servidor, mientras que
-- el round trip a Supabase (us-west-2) cuesta ~220 ms. O sea que la latencia de
-- la búsqueda es red, no cómputo, y el índice no la mueve.
-- Vale crearlo igual porque es gratis y porque después de la reingesta de la
-- Fase 4, con metadata y un corpus más grande, sí va a importar.
-- m=16 es el default de pgvector y está bien hasta miles de filas.
-- ef_construction=200 (sobre el default 64) tarda segundos a este tamaño y
-- compra recall que después no hay que volver a mirar.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
  ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

-- ============================================================================
-- PARTE 2 — Correr SOLO junto con la reingesta (Fase 4).
-- Después de esto la tabla `chunks` queda vacía y el agente no encuentra nada
-- hasta que corras la ingesta. No la ejecutes un rato antes de una demo.
-- ============================================================================

-- RENAME en lugar de TRUNCATE, a propósito: son 288 filas, no cuesta nada, y
-- deja re-apuntar RAG_TABLE a la tabla vieja para medir el corpus viejo con el
-- agente nuevo. Es la comparación que zanja si el rework del chunking sirvió.
ALTER TABLE IF EXISTS chunks RENAME TO chunks_legacy_v1;
ALTER INDEX IF EXISTS chunks_embedding_hnsw RENAME TO chunks_legacy_v1_hnsw;

CREATE TABLE chunks (
  id            bigserial PRIMARY KEY,
  -- sha256(texto normalizado + source): hace la reingesta idempotente vía
  -- ON CONFLICT, así arreglar un documento no re-embebe todo el corpus.
  content_hash  text         NOT NULL UNIQUE,
  text          text         NOT NULL,
  embedding     vector(1024) NOT NULL,        -- cohere embed-multilingual-v3.0
  source        text         NOT NULL,
  section       text,                          -- "2.4. EL HERIDO INCONSCIENTE QUE NO RESPIRA"
  subsection    text,
  page_start    int,
  page_end      int,
  ord           int          NOT NULL,         -- orden dentro del documento
  -- locale existe para que sumar un corpus argentino más adelante no requiera
  -- otra migración, aunque hoy la decisión sea quedarse con el corpus español.
  locale        text         NOT NULL DEFAULT 'es-ES',
  metadata      jsonb        NOT NULL DEFAULT '{}'::jsonb,
  -- Columna generada, gratis de crear. Deja probar hybrid BM25 + RRF como un
  -- experimento de 20 líneas en vez de otra migración, si el eval lo pide.
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('spanish', text)) STORED,
  created_at    timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX chunks_embedding_hnsw ON chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200);
CREATE INDEX chunks_tsv_gin   ON chunks USING gin (tsv);
CREATE INDEX chunks_source_ix ON chunks (source);
