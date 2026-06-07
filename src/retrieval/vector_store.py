import os
import json
from typing import List, Dict, Any, Optional
from src.ingestion.chunking import DocumentChunk

# Intentar importar psycopg2 y pgvector para el tipado y llamadas reales
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from pgvector.psycopg2 import register_vector
    HAS_DB_DRIVERS = True
except ImportError:
    HAS_DB_DRIVERS = False

class VectorStoreManager:
    """Clase encargada de la conexión, creación de esquema e inserción en pgvector."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        """
        Inicializa el gestor de base de datos vectorial.
        
        Args:
            dsn (str, opcional): URI de conexión de PostgreSQL. 
                                 Si no se provee, lee de variables de entorno o usa default.
        """
        self.dsn = dsn or os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/emergencias_db")
        self.conn = None
        self.cursor = None
        self.use_mock = not HAS_DB_DRIVERS
        
        # Almacenamiento simulado en memoria si no hay base de datos disponible
        self._mock_db: Dict[str, DocumentChunk] = {}

    def connect(self) -> None:
        """Establece la conexión con PostgreSQL o activa el modo mock si falla."""
        if self.use_mock:
            print("[VectorStore - Mock] Controladores de BD no instalados. Usando simulador en memoria.")
            return

        try:
            # En la PoC real, esto abriría la conexión
            # Para garantizar que el pipeline sea ejecutable, intentamos conectar y atrapamos excepciones.
            self.conn = psycopg2.connect(self.dsn, connect_timeout=2)
            self.cursor = self.conn.cursor()
            # Registrar pgvector en la conexión
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
            # Asegurar la extensión pgvector (longitud de embedding típica de 384 o 768 para modelos en español)
            # Usaremos 384 como estándar de modelos ligeros en español (ej. sentence-transformers/all-MiniLM-L6-v2)
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Tabla de chunks
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS protocol_chunks (
                    id UUID PRIMARY KEY,
                    texto_del_chunk TEXT NOT NULL,
                    metadatos JSONB NOT NULL,
                    embedding VECTOR(384)
                );
            """)
            self.conn.commit()
            print("[VectorStore] Esquema de base de datos inicializado (extensión pgvector y tabla creadas).")
        except Exception as e:
            print(f"[VectorStore - Error] Error al inicializar esquema: {e}")
            self.use_mock = True

    def insert_chunks(self, chunks: List[DocumentChunk]) -> None:
        """
        Inserta una lista de fragmentos con sus metadatos y vectores simulados en la base de datos.
        
        Args:
            chunks (List[DocumentChunk]): Fragmentos procesados.
        """
        if self.use_mock:
            for chunk in chunks:
                self._mock_db[chunk.id] = chunk
            print(f"[VectorStore - Mock] {len(chunks)} fragmentos insertados en la base de datos simulada.")
            return

        try:
            for chunk in chunks:
                # Simulación de vector de 384 dimensiones relleno con ceros/valores para esta PoC
                mock_embedding = [0.1] * 384
                
                self.cursor.execute(
                    """
                    INSERT INTO protocol_chunks (id, texto_del_chunk, metadatos, embedding)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        texto_del_chunk = EXCLUDED.texto_del_chunk,
                        metadatos = EXCLUDED.metadatos,
                        embedding = EXCLUDED.embedding;
                    """,
                    (chunk.id, chunk.text, json.dumps(chunk.metadata), mock_embedding)
                )
            self.conn.commit()
            print(f"[VectorStore] {len(chunks)} fragmentos insertados/actualizados en pgvector.")
        except Exception as e:
            print(f"[VectorStore - Error] Error al insertar fragmentos: {e}. Almacenando en fallback en memoria.")
            # Fallback a memoria
            for chunk in chunks:
                self._mock_db[chunk.id] = chunk

    def close(self) -> None:
        """Cierra las conexiones abiertas."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("[VectorStore] Conexiones cerradas.")

if __name__ == "__main__":
    # Prueba de concepto aislada de vector_store
    from src.ingestion.chunking import DocumentChunk
    
    manager = VectorStoreManager()
    manager.connect()
    manager.initialize_schema()
    
    sample_chunk = DocumentChunk(
        text="FASE DE TOMA DE CONOCIMIENTO: Operador atiende llamada.",
        metadata={"fase_protocolo": "TOMA DE CONOCIMIENTO", "source": "test.pdf"}
    )
    
    manager.insert_chunks([sample_chunk])
    manager.close()
