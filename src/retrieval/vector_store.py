import os
import json
from typing import List, Dict, Any, Optional
from src.ingestion.chunking import DocumentChunk

# Controladores reales de PostgreSQL + pgvector.
try:
    import psycopg2
    from psycopg2.extras import execute_values
    from pgvector.psycopg2 import register_vector
    HAS_DB_DRIVERS = True
except ImportError:
    HAS_DB_DRIVERS = False

# Dimensión de los embeddings. El modelo 'paraphrase-multilingual' produce vectores de 768.
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))


class VectorStoreManager:
    """Clase encargada de la conexión, creación de esquema e inserción en pgvector."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        """
        Inicializa el gestor de base de datos vectorial.

        Args:
            dsn (str, opcional): URI de conexión de PostgreSQL.
                                 Si no se provee, lee de variables de entorno o usa default.
        """
        self.dsn = dsn or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/emergencias_db",
        )
        self.conn = None
        self.cursor = None
        # En modo mock no se toca PostgreSQL; sólo se activa si faltan los drivers.
        self.use_mock = not HAS_DB_DRIVERS

        # Almacenamiento simulado en memoria si no hay base de datos disponible
        self._mock_db: Dict[str, DocumentChunk] = {}

    def connect(self) -> None:
        """Establece la conexión con PostgreSQL o activa el modo mock si falla."""
        if self.use_mock:
            print("[VectorStore - Mock] Controladores de BD no instalados. Usando simulador en memoria.")
            return

        try:
            self.conn = psycopg2.connect(self.dsn, connect_timeout=5)
            self.conn.autocommit = False
            self.cursor = self.conn.cursor()
            # La extensión pgvector debe existir antes de registrar el adaptador de tipos.
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self.conn.commit()
            register_vector(self.conn)
            print("[VectorStore] Conexión establecida exitosamente con PostgreSQL.")
        except Exception as e:
            print(f"[VectorStore - Fallback] No se pudo conectar a la base de datos real ({e}). Activando simulador en memoria.")
            self.use_mock = True

    def initialize_schema(self) -> None:
        """Crea la extensión pgvector y la tabla de fragmentos con columna VECTOR si es necesario."""
        if self.use_mock:
            print("[VectorStore - Mock] Esquema inicializado en memoria simulada.")
            return

        try:
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Tabla de chunks. La dimensión del vector corresponde al modelo de embeddings (bge-m3 = 1024).
            self.cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS protocol_chunks (
                    id UUID PRIMARY KEY,
                    texto_del_chunk TEXT NOT NULL,
                    metadatos JSONB NOT NULL,
                    embedding VECTOR({EMBEDDING_DIM})
                );
                """
            )
            self.conn.commit()
            print(f"[VectorStore] Esquema inicializado (extensión pgvector y tabla protocol_chunks VECTOR({EMBEDDING_DIM})).")
        except Exception as e:
            print(f"[VectorStore - Error] Error al inicializar esquema: {e}")
            self.conn.rollback()
            self.use_mock = True

    def clear_table(self) -> None:
        """Elimina todos los registros de la tabla protocol_chunks."""
        if self.use_mock:
            self._mock_db.clear()
            print("[VectorStore - Mock] Base de datos simulada vaciada.")
            return

        try:
            self.cursor.execute("TRUNCATE TABLE protocol_chunks;")
            self.conn.commit()
            print("[VectorStore] Tabla protocol_chunks truncada exitosamente.")
        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"[VectorStore - Error] Error al vaciar la tabla: {e}")
            raise

    def _get_searcher(self):
        """
        Devuelve (creándolo de forma diferida) el ``VectorSearcher`` asociado, usado para
        generar embeddings. El import es local para evitar la dependencia circular con
        ``search.py`` (que a su vez importa este módulo).
        """
        if getattr(self, "_searcher", None) is None:
            from src.retrieval.search import VectorSearcher
            self._searcher = VectorSearcher(self)
        return self._searcher

    def insert_chunks(self, chunks: List[DocumentChunk]) -> None:
        """
        Inserta una lista de fragmentos con sus metadatos en la base de datos, generando
        automáticamente el vector de embeddings de cada uno.

        Args:
            chunks (List[DocumentChunk]): Fragmentos procesados.
        """
        if self.use_mock:
            for chunk in chunks:
                self._mock_db[chunk.id] = chunk
            print(f"[VectorStore - Mock] {len(chunks)} fragmentos insertados en la base de datos simulada.")
            return

        searcher = self._get_searcher()
        embeddings = [searcher.get_embeddings(chunk.text) for chunk in chunks]
        self._persist(chunks, embeddings)

    def _persist(self, chunks: List[DocumentChunk], embeddings: List[List[float]]) -> None:
        """
        Auxiliar interno: persiste en pgvector los chunks junto con sus embeddings ya
        calculados (mismo orden y longitud que ``chunks``).
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"El número de chunks ({len(chunks)}) no coincide con el de embeddings ({len(embeddings)})."
            )

        try:
            rows = [
                (chunk.id, chunk.text, json.dumps(chunk.metadata, ensure_ascii=False), embedding)
                for chunk, embedding in zip(chunks, embeddings)
            ]
            execute_values(
                self.cursor,
                """
                INSERT INTO protocol_chunks (id, texto_del_chunk, metadatos, embedding)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    texto_del_chunk = EXCLUDED.texto_del_chunk,
                    metadatos = EXCLUDED.metadatos,
                    embedding = EXCLUDED.embedding;
                """,
                rows,
                template="(%s, %s, %s::jsonb, %s::vector)",
            )
            self.conn.commit()
            print(f"[VectorStore] {len(chunks)} fragmentos insertados/actualizados en pgvector.")
        except Exception as e:
            self.conn.rollback()
            print(f"[VectorStore - Error] Error al insertar fragmentos: {e}")
            raise

    def insert_from_json(self, json_path: str) -> None:
        """
        Lee el JSON de chunks (producido por el módulo de ingesta de Andrés), construye los
        ``DocumentChunk`` y los inserta en pgvector (los embeddings se generan dentro de
        ``insert_chunks``).

        Args:
            json_path (str): Ruta al archivo JSON con la lista de chunks
                             (formato ``[{"id", "text", "metadata"}, ...]``).
        """
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chunks = [
            DocumentChunk(
                id=item.get("id"),
                text=item["text"],
                metadata=item.get("metadata", {}),
            )
            for item in data
        ]
        print(f"[VectorStore] Leídos {len(chunks)} fragmentos desde '{json_path}'. Generando embeddings e insertando...")
        self.insert_chunks(chunks)

    def close(self) -> None:
        """Cierra las conexiones abiertas."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("[VectorStore] Conexiones cerradas.")


if __name__ == "__main__":
    manager = VectorStoreManager()
    manager.connect()
    manager.initialize_schema()

    sample_chunk = DocumentChunk(
        text="FASE DE TOMA DE CONOCIMIENTO: Operador atiende llamada.",
        metadata={"fase_protocolo": "TOMA DE CONOCIMIENTO", "source": "test.pdf"},
    )
    manager.insert_chunks([sample_chunk])
    manager.close()
