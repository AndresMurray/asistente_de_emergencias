import os
import json
import uuid
from typing import Dict, Any, List
from pydantic import BaseModel, Field

class DocumentChunk(BaseModel):
    """Modelo Pydantic que representa un fragmento de texto procesado con sus metadatos."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProtocolChunker:
    """Clase encargada de la partición (chunking) del texto y gestión de metadatos."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str, doc_metadata: Dict[str, Any]) -> List[DocumentChunk]:
        """
        Divide el texto en fragmentos (chunks) lógicos y asigna metadatos específicos de la fase.
        
        Args:
            text (str): Texto limpio a particionar.
            doc_metadata (dict): Metadatos del documento base (ej. autor, fecha).
            
        Returns:
            List[DocumentChunk]: Lista de fragmentos estructurados con metadatos.
        """
        chunks: List[DocumentChunk] = []
        
        # En una PoC real, esto puede dividir por caracteres o delimitadores semánticos.
        # Simulación de chunking estructurado por fases del protocolo:
        phases = [
            ("TOMA DE CONOCIMIENTO", "FASE DE TOMA DE CONOCIMIENTO:"),
            ("ARRIBO AL LUGAR", "FASE DE ARRIBO AL LUGAR:"),
            ("INTERVENCION", "FASE DE INTERVENCION:")
        ]
        
        found_chunks = False
        for phase_name, phrase in phases:
            if phrase in text:
                found_chunks = True
                # Extraer la sección del texto correspondiente a esta fase
                start_idx = text.find(phrase)
                # Buscar el inicio de la siguiente fase para recortar
                end_idx = len(text)
                for _, next_phrase in phases:
                    if next_phrase != phrase and text.find(next_phrase) > start_idx:
                        next_end = text.find(next_phrase)
                        if next_end < end_idx:
                            end_idx = next_end
                
                chunk_text = text[start_idx:end_idx].strip()
                
                # Crear metadatos específicos para este fragmento
                chunk_meta = doc_metadata.copy()
                chunk_meta["fase_protocolo"] = phase_name
                
                chunks.append(
                    DocumentChunk(
                        text=chunk_text,
                        metadata=chunk_meta
                    )
                )
        
        # Fallback si el texto no contiene las frases clave (división por longitud estándar)
        if not found_chunks:
            words = text.split()
            for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
                chunk_words = words[i:i + self.chunk_size]
                chunk_text = " ".join(chunk_words)
                
                chunk_meta = doc_metadata.copy()
                chunk_meta["fase_protocolo"] = "GENERAL"
                
                chunks.append(
                    DocumentChunk(
                        text=chunk_text,
                        metadata=chunk_meta
                    )
                )
                if i + self.chunk_size >= len(words):
                    break
                    
        return chunks

    def save_chunks(self, chunks: List[DocumentChunk], output_path: str) -> None:
        """
        Guarda los fragmentos estructurados en un archivo JSON en la ruta especificada.
        
        Args:
            chunks (List[DocumentChunk]): Lista de fragmentos.
            output_path (str): Ruta del archivo JSON destino.
        """
        # Crear directorios si no existen
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        serialized = [chunk.model_dump() for chunk in chunks]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, ensure_ascii=False, indent=4)
        print(f"[Chunker] Se han guardado {len(chunks)} fragmentos en '{output_path}'.")

if __name__ == "__main__":
    from src.ingestion.extractors import ProtocolExtractor
    
    extractor = ProtocolExtractor()
    raw = extractor.extract_text("data/raw/protocolo_siniestros.pdf")
    clean = extractor.clean_text(raw)
    
    chunker = ProtocolChunker()
    meta = {"source": "protocolo_siniestros.pdf", "autor": "Ministerio de Transporte"}
    chunks = chunker.chunk_text(clean, meta)
    
    chunker.save_chunks(chunks, "data/processed/protocolos_chunks.json")
