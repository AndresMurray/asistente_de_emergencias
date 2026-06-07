import os
from typing import List, Dict, Any
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

    def get_embeddings(self, text: str) -> List[float]:
        """
        Genera el vector de embeddings del texto provisto.
        En producción: Se puede conectar con un modelo local de Ollama (ej. nomic-embed-text) 
        o HuggingFace (ej. sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).
        
        Args:
            text (str): Texto a vectorizar.
            
        Returns:
            List[float]: Vector de dimensiones fijas (384 en este ejemplo).
        """
        # Mock de vectorización: devuelve un vector simple basado en la longitud y caracteres del texto
        # para simular cierta variabilidad numérica de forma determinista.
        dimension = 384
        val = sum(ord(c) for c in text) % 100 / 100.0
        return [val * (i / dimension) for i in range(dimension)]

    def search_similarity(self, query: str, limit: int = 3) -> List[DocumentChunk]:
        """
        Realiza la búsqueda de similitud de coseno o distancia L2 en pgvector.
        Si la base de datos está en modo mock, realiza una simulación basada en palabras clave.
        
        Args:
            query (str): Consulta del operador de emergencia.
            limit (int): Número máximo de resultados relevantes a retornar.
            
        Returns:
            List[DocumentChunk]: Lista de los fragmentos más relevantes.
        """
        print(f"[Search] Buscando similitud para la consulta: '{query}'")
        
        # Modo fallback/mock: Búsqueda heurística por coincidencia de palabras
        if self.db_manager.use_mock:
            results: List[DocumentChunk] = []
            query_words = set(query.lower().split())
            
            # Buscar en el diccionario de simulación de memoria
            candidates = list(self.db_manager._mock_db.values())
            
            # Si no hay candidatos guardados, generar fragmentos de respuesta mock predefinidos
            if not candidates:
                candidates = [
                    DocumentChunk(
                        text="FASE DE TOMA DE CONOCIMIENTO:\nEl operador recibe la llamada de emergencia. Se deben registrar: ubicación exacta, tipo de siniestro y lesionados.",
                        metadata={"fase_protocolo": "TOMA DE CONOCIMIENTO", "source": "protocolo_default.pdf"}
                    ),
                    DocumentChunk(
                        text="FASE DE ARRIBO AL LUGAR:\nEl equipo de emergencia llega al lugar en menos de 10 minutos. Evaluar la escena por riesgos secundarios.",
                        metadata={"fase_protocolo": "ARRIBO AL LUGAR", "source": "protocolo_default.pdf"}
                    ),
                    DocumentChunk(
                        text="FASE DE INTERVENCION:\nBrindar auxilio médico a los heridos graves. Priorizar estabilización.",
                        metadata={"fase_protocolo": "INTERVENCION", "source": "protocolo_default.pdf"}
                    )
                ]
            
            # Puntuar candidatos según palabras coincidentes
            scored_candidates = []
            for candidate in candidates:
                match_count = sum(1 for word in query_words if word in candidate.text.lower())
                scored_candidates.append((match_count, candidate))
            
            # Ordenar de mayor a menor puntuación
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            results = [cand for score, cand in scored_candidates[:limit]]
            print(f"[Search - Mock] Encontrados {len(results)} fragmentos en base simulada.")
            return results

        # Consulta real en base de datos usando pgvector
        try:
            query_vector = self.get_embeddings(query)
            self.db_manager.cursor.execute(
                """
                SELECT id, texto_del_chunk, metadatos, (embedding <=> %s::vector) AS distancia
                FROM protocol_chunks
                ORDER BY distancia ASC
                LIMIT %s;
                """,
                (query_vector, limit)
            )
            rows = self.db_manager.cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(
                    DocumentChunk(
                        id=str(row[0]),
                        text=row[1],
                        metadata=row[2]
                    )
                )
            print(f"[Search] Encontrados {len(results)} fragmentos vía pgvector.")
            return results
        except Exception as e:
            print(f"[Search - Error] Error en consulta a base de datos: {e}. Retornando vacío.")
            return []

    def create_hnsw_index(self) -> None:
        """
        Crea el índice HNSW en la columna embedding de la tabla para optimizar la latencia.
        Nota: pgvector soporta HNSW utilizando operadores de distancia coseno (<=>) o L2 (<->).
        """
        if self.db_manager.use_mock:
            print("[Search - Mock] Creación de índice HNSW simulado con éxito.")
            return

        try:
            # Creamos el índice usando la distancia del coseno.
            # 'lists' u otros parámetros pueden ajustarse según volumen.
            self.db_manager.cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS protocol_chunks_embedding_hnsw_idx 
                ON protocol_chunks USING hnsw (embedding vector_cosine_ops);
                """
            )
            self.db_manager.conn.commit()
            print("[Search] Índice HNSW creado exitosamente en la columna embedding de PostgreSQL.")
        except Exception as e:
            print(f"[Search - Error] No se pudo crear el índice HNSW: {e}")

if __name__ == "__main__":
    # Prueba de concepto aislada de vector search
    manager = VectorStoreManager()
    manager.connect()
    
    searcher = VectorSearcher(manager)
    results = searcher.search_similarity("¿Qué hacer al llegar al lugar del accidente vial?", limit=2)
    
    for idx, r in enumerate(results):
        print(f"\nResultado {idx+1}:")
        print(f"Fase: {r.metadata.get('fase_protocolo')}")
        print(f"Texto: {r.text}")
        
    searcher.create_hnsw_index()
    manager.close()
