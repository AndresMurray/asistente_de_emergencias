import os
from typing import List
import requests

from src.ingestion.chunking import DocumentChunk
from src.retrieval.vector_store import VectorStoreManager


class VectorSearcher:
    """Clase encargada de la generación de embeddings, búsquedas semánticas e índices HNSW."""

    def __init__(self, db_manager: VectorStoreManager) -> None:
        """
        Inicializa el buscador con una referencia al gestor de base de datos.

        Args:
            db_manager (VectorStoreManager): Gestor de conexión e inserción.
        """
        self.db_manager = db_manager
        # Servicio de embeddings de Ollama. Modelo multilingüe liviano (768 dimensiones).
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.embed_model = os.getenv("EMBED_MODEL", "paraphrase-multilingual")
        self.embed_url = f"{self.ollama_url}/api/embeddings"

    def get_embeddings(self, text: str) -> List[float]:
        """
        Genera el vector de embeddings del texto provisto usando el modelo multilingüe
        local 'paraphrase-multilingual' a través de la API de embeddings de Ollama.

        Args:
            text (str): Texto a vectorizar.

        Returns:
            List[float]: Vector de embeddings (768 dimensiones).
        """
        response = requests.post(
            self.embed_url,
            json={"model": self.embed_model, "prompt": text},
            timeout=30,
        )
        response.raise_for_status()
        embedding = response.json().get("embedding")
        if not embedding:
            raise ValueError(f"Ollama no devolvió embedding para el texto: '{text[:50]}...'")
        return embedding

    def search_similarity(self, query: str, limit: int = 3) -> List[DocumentChunk]:
        """
        Realiza la búsqueda de similitud de coseno en pgvector.
        Si la base de datos está en modo mock, realiza una simulación basada en palabras clave.

        Args:
            query (str): Consulta del operador de emergencia.
            limit (int): Número máximo de resultados relevantes a retornar.

        Returns:
            List[DocumentChunk]: Lista de los fragmentos más relevantes.
        """
        print(f"[Search] Buscando similitud para la consulta: '{query}'")

        # Modo fallback/mock: búsqueda heurística por coincidencia de palabras.
        if self.db_manager.use_mock:
            return self._mock_search(query, limit)

        # Consulta real usando el operador de distancia de coseno (<=>) de pgvector.
        try:
            query_vector = self.get_embeddings(query)
            self.db_manager.cursor.execute(
                """
                SELECT id, texto_del_chunk, metadatos, (embedding <=> %s::vector) AS distancia
                FROM protocol_chunks
                ORDER BY embedding <=> %s::vector ASC
                LIMIT %s;
                """,
                (query_vector, query_vector, limit),
            )
            rows = self.db_manager.cursor.fetchall()

            results = [
                DocumentChunk(id=str(row[0]), text=row[1], metadata=row[2])
                for row in rows
            ]
            print(f"[Search] Encontrados {len(results)} fragmentos vía pgvector (distancia coseno).")
            return results
        except Exception as e:
            self.db_manager.conn.rollback()
            print(f"[Search - Error] Error en consulta a base de datos: {e}. Retornando vacío.")
            return []

    def _mock_search(self, query: str, limit: int) -> List[DocumentChunk]:
        """Búsqueda heurística por coincidencia de palabras para el modo simulado."""
        query_words = set(query.lower().split())
        candidates = list(self.db_manager._mock_db.values())

        if not candidates:
            candidates = [
                DocumentChunk(
                    text="FASE DE TOMA DE CONOCIMIENTO:\nEl operador recibe la llamada de emergencia. Se deben registrar: ubicación exacta, tipo de siniestro y lesionados.",
                    metadata={"fase_protocolo": "TOMA DE CONOCIMIENTO", "source": "protocolo_default.pdf"},
                ),
                DocumentChunk(
                    text="FASE DE ARRIBO AL LUGAR:\nEl equipo de emergencia llega al lugar en menos de 10 minutos. Evaluar la escena por riesgos secundarios.",
                    metadata={"fase_protocolo": "ARRIBO AL LUGAR", "source": "protocolo_default.pdf"},
                ),
                DocumentChunk(
                    text="FASE DE INTERVENCION:\nBrindar auxilio médico a los heridos graves. Priorizar estabilización.",
                    metadata={"fase_protocolo": "INTERVENCION", "source": "protocolo_default.pdf"},
                ),
            ]

        scored = [
            (sum(1 for word in query_words if word in c.text.lower()), c)
            for c in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [c for _, c in scored[:limit]]
        print(f"[Search - Mock] Encontrados {len(results)} fragmentos en base simulada.")
        return results

    def create_hnsw_index(self) -> None:
        """
        Crea el índice HNSW en la columna embedding de la tabla para optimizar la latencia.
        Se usa el operador de distancia de coseno (vector_cosine_ops).
        """
        if self.db_manager.use_mock:
            print("[Search - Mock] Creación de índice HNSW simulado con éxito.")
            return

        try:
            self.db_manager.cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS protocol_chunks_embedding_hnsw_idx
                ON protocol_chunks USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
                """
            )
            self.db_manager.conn.commit()
            print("[Search] Índice HNSW creado exitosamente en la columna embedding de PostgreSQL.")
        except Exception as e:
            self.db_manager.conn.rollback()
            print(f"[Search - Error] No se pudo crear el índice HNSW: {e}")


if __name__ == "__main__":
    manager = VectorStoreManager()
    manager.connect()

    searcher = VectorSearcher(manager)
    results = searcher.search_similarity("¿Qué hacer al llegar al lugar del accidente vial?", limit=2)

    for idx, r in enumerate(results):
        print(f"\nResultado {idx + 1}:")
        print(f"Fase: {r.metadata.get('fase_protocolo')}")
        print(f"Texto: {r.text}")

    searcher.create_hnsw_index()
    manager.close()
