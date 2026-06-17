import os
import json
import uuid
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """Modelo Pydantic que representa un fragmento de texto procesado con sus metadatos."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    fase_protocolo: str = Field(default="GENERAL")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ── Recursive Character Splitter (Python puro, sin dependencias externas) ────────────
# Implementación equivalente al RecursiveCharacterTextSplitter de LangChain.
# Divide el texto intentando respetar separadores semánticos en orden de prioridad.

class _RecursiveCharacterSplitter:
    """
    Splitter recursivo liviano que no requiere dependencias externas.
    Intenta dividir usando los separadores en orden; si un fragmento sigue siendo
    mayor que chunk_size, recurse con el siguiente separador.
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: Optional[List[str]] = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS

    def split(self, text: str) -> List[str]:
        """Punto de entrada público."""
        chunks = self._split_recursive(text, self.separators)
        return self._merge_with_overlap(chunks)

    # ── Internos ──────────────────────────────────────────────────────────────────

    def _split_recursive(self, text: str, separators: List[str]) -> List[str]:
        """Divide recursivamente eligiendo el separador más apropiado."""
        if not separators:
            # Último recurso: dividir por caracteres
            return [text[i:i + self.chunk_size]
                    for i in range(0, len(text), self.chunk_size - self.chunk_overlap)]

        separator = separators[0]
        remaining = separators[1:]

        if separator == "":
            # Nivel más profundo: corte por carácter
            return [text[i:i + self.chunk_size]
                    for i in range(0, len(text), max(1, self.chunk_size - self.chunk_overlap))]

        parts = text.split(separator)
        final_chunks: List[str] = []

        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) <= self.chunk_size:
                final_chunks.append(part)
            else:
                # El fragmento sigue siendo grande; recurse con el siguiente separador
                sub_chunks = self._split_recursive(part, remaining)
                final_chunks.extend(sub_chunks)

        return final_chunks

    def _merge_with_overlap(self, chunks: List[str]) -> List[str]:
        """
        Fusiona fragmentos pequeños para acercarse a chunk_size y añade
        el overlap deslizando texto del chunk anterior al inicio del siguiente.
        """
        if not chunks:
            return []

        merged: List[str] = []
        current = chunks[0]

        for next_chunk in chunks[1:]:
            candidate = current + " " + next_chunk
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                merged.append(current.strip())
                # Overlap: tomar los últimos chunk_overlap caracteres del chunk actual
                overlap_text = current[-self.chunk_overlap:] if self.chunk_overlap > 0 else ""
                current = (overlap_text + " " + next_chunk).strip() if overlap_text else next_chunk

        if current.strip():
            merged.append(current.strip())

        return merged


# ─────────────────────────────────────────────────────────────────────────────────────

class ProtocolChunker:
    """Clase encargada de la partición (chunking) del texto y gestión de metadatos."""

    # Marcadores de fase del protocolo. El chunker los detecta en el texto y los
    # usa para partir semanticamente antes de aplicar el splitter recursivo.
    # Los patrones cubren la metodologia PAS (Proteger-Alertar-Socorrer) y las
    # denominaciones de fase encontradas en los documentos oficiales argentinos.
    PHASE_MARKERS = [
        # Frases exactas del mock / documentos tipo
        ("TOMA DE CONOCIMIENTO", r"FASE\s+DE\s+TOMA\s+DE\s+CONOCIMIENTO\s*:?"),
        ("ARRIBO AL LUGAR",      r"FASE\s+DE\s+ARRIBO\s+AL\s+LUGAR\s*:?"),
        ("INTERVENCION",         r"FASE\s+DE\s+INTERVENCI[OO]N\s*:?"),
        # Numeradas
        ("TOMA DE CONOCIMIENTO", r"1[.]?\s*[-]?\s*TOMA\s+DE\s+CONOCIMIENTO"),
        ("ARRIBO AL LUGAR",      r"2[.]?\s*[-]?\s*ARRIBO\s+AL\s+LUGAR"),
        ("INTERVENCION",         r"3[.]?\s*[-]?\s*INTERVENCI[OO]N"),
        # Metodologia PAS (Proteger-Alertar-Socorrer)
        # Presente en "Guia Siniestros Viales VF.pdf" y similares
        ("PROTEGER",             r"1\s*PROTEGER\s*:?"),
        ("ALERTAR",              r"2\s*ALERTAR\s*:?"),
        ("SOCORRER",             r"3\s*SOCORRER\s*:?"),
        # Variante sin numeracion explicita
        ("PROTEGER",             r"^\s*PROTEGER\s*:\s*$"),
        ("ALERTAR",              r"^\s*ALERTAR\s*:\s*$"),
        ("SOCORRER",             r"^\s*SOCORRER\s*:\s*$"),
        # Secciones tipo AVISO / SOCORRO (Guia de vehiculos)
        ("AVISAR",               r"^\s*AVISAR\s*$"),
        # Primeros auxilios
        ("EVALUACION VICTIMA",   r"EVALUACI[OO]N\s+DE\s+LA\s+V[II]CTIMA"),
        ("RCP",                  r"REANIMACI[OO]N\s+CARDIO[-\s]?PULMONAR"),
        # Procedimiento (Ministerio GBA)
        ("PROCEDIMIENTO",        r"PROCEDIMIENTO\s*(?:DE\s+ACTUACI[OO]N)?\s*:?"),
        # Seccion generica
        ("ACTUACION",            r"C[OO]MO\s+ACTUAR\s+FRENTE\s+A\s+UN\s+SINIESTRO"),
        ("GESTION EMERGENCIA",   r"GESTI[OO]N\s+(?:DE\s+)?(?:LA\s+)?EMERGENCIA"),
        ("RECURSOS",             r"RECURSOS\s+(?:HUMANOS|LOG[II]STICOS|PARA\s+RESPONDER)"),
    ]


    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = _RecursiveCharacterSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def chunk_text(self, text: str, doc_metadata: Dict[str, Any]) -> List[DocumentChunk]:
        """
        Divide el texto en fragmentos (chunks) lógicos y asigna metadatos específicos de la fase.

        Estrategia:
          1. Detectar marcadores de fase del protocolo en el texto.
          2. Segmentar el texto por fases cuando son encontradas.
          3. Aplicar el Recursive Character Splitter sobre cada segmento de fase.
          4. Si no hay fases, aplicar el splitter al texto completo con fase "GENERAL".

        Args:
            text (str): Texto limpio a particionar.
            doc_metadata (dict): Metadatos del documento base (ej. autor, fecha).

        Returns:
            List[DocumentChunk]: Lista de fragmentos estructurados con metadatos.
        """
        chunks: List[DocumentChunk] = []

        # ── Paso 1: Detectar posiciones de cada fase en el texto ─────────────────
        phase_positions: List[tuple] = []  # (start_idx, phase_name)

        for phase_name, pattern in self.PHASE_MARKERS:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                # Evitar duplicados si ya registramos esta fase (varias variantes)
                already_found = any(pn == phase_name for _, pn in phase_positions)
                if not already_found:
                    phase_positions.append((match.start(), phase_name))

        # Ordenar por posición de aparición en el texto
        phase_positions.sort(key=lambda x: x[0])

        # ── Paso 2: Extraer segmentos de texto por fase ───────────────────────────
        if phase_positions:
            for idx, (start, phase_name) in enumerate(phase_positions):
                # El segmento va desde este marcador hasta el inicio del siguiente
                if idx + 1 < len(phase_positions):
                    end = phase_positions[idx + 1][0]
                else:
                    end = len(text)

                segment = text[start:end].strip()
                if not segment:
                    continue

                # ── Paso 3: Splitter recursivo sobre el segmento de fase ──────────
                sub_texts = self._splitter.split(segment)
                for chunk_idx, sub_text in enumerate(sub_texts):
                    if not sub_text.strip():
                        continue

                    chunk_meta = doc_metadata.copy()
                    chunk_meta["fase_protocolo"] = phase_name
                    chunk_meta["chunk_index"] = chunk_idx
                    chunk_meta["total_chunks_in_phase"] = len(sub_texts)

                    chunks.append(
                        DocumentChunk(
                            text=sub_text.strip(),
                            fase_protocolo=phase_name,
                            metadata=chunk_meta,
                        )
                    )

        # ── Paso 4: Fallback — splitter recursivo puro sin fases ──────────────────
        if not chunks:
            sub_texts = self._splitter.split(text)
            for chunk_idx, sub_text in enumerate(sub_texts):
                if not sub_text.strip():
                    continue

                chunk_meta = doc_metadata.copy()
                chunk_meta["fase_protocolo"] = "GENERAL"
                chunk_meta["chunk_index"] = chunk_idx

                chunks.append(
                    DocumentChunk(
                        text=sub_text.strip(),
                        fase_protocolo="GENERAL",
                        metadata=chunk_meta,
                    )
                )

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
    import sys
    import glob
    from src.ingestion.extractors import ProtocolExtractor

    extractor = ProtocolExtractor()
    chunker = ProtocolChunker(chunk_size=500, chunk_overlap=50)

    all_chunks: List[DocumentChunk] = []

    # Directorio donde se guarda el texto limpio (un .txt por PDF)
    CLEAN_TEXT_DIR = "data/processed/clean"
    os.makedirs(CLEAN_TEXT_DIR, exist_ok=True)

    # Permitir especificar un archivo PDF o directorio por parámetro de línea de comandos
    target_path = sys.argv[1] if len(sys.argv) > 1 else "data/raw"

    if os.path.isfile(target_path):
        if target_path.lower().endswith(".pdf"):
            pdf_files = [target_path]
        else:
            print(f"[Main] El archivo especificado '{target_path}' no es un PDF.")
            sys.exit(1)
    elif os.path.isdir(target_path):
        pdf_files = glob.glob(os.path.join(target_path, "*.pdf"))
    else:
        # Intentar tratar target_path como un patrón glob
        pdf_files = glob.glob(target_path)

    if not pdf_files:
        print(f"[Main] No se encontraron archivos PDF en '{target_path}'. Usando mock.")
        raw = extractor.extract_text("data/raw/protocolo_siniestros.pdf")
        clean = extractor.clean_text(raw)

        # Persistir texto limpio del mock
        clean_path = os.path.join(CLEAN_TEXT_DIR, "protocolo_siniestros_clean.txt")
        with open(clean_path, "w", encoding="utf-8") as f:
            f.write(clean)
        print(f"[Main] Texto limpio guardado en '{clean_path}'.")

        meta = {"source": "protocolo_siniestros.pdf", "autor": "Mock"}
        chunks = chunker.chunk_text(clean, meta)
        all_chunks.extend(chunks)
    else:
        for pdf_path in pdf_files:
            filename = os.path.basename(pdf_path)
            print(f"\n[Main] Procesando: {filename}")

            raw = extractor.extract_text(pdf_path)
            if not raw.strip():
                print(f"[Main] '{filename}' no produjo texto. Saltando.")
                continue

            clean = extractor.clean_text(raw)

            # Persistir texto limpio: mismo nombre que el PDF pero con _clean.txt
            stem = os.path.splitext(filename)[0]          # nombre sin extensión
            clean_path = os.path.join(CLEAN_TEXT_DIR, f"{stem}_clean.txt")
            with open(clean_path, "w", encoding="utf-8") as f:
                f.write(clean)
            print(f"[Main]   Texto limpio guardado -> '{clean_path}' ({len(clean)} chars)")

            meta = {
                "source": filename,
                "pdf_path": pdf_path,
                "clean_text_path": clean_path,  # referencia al texto limpio en metadata
            }

            chunks = chunker.chunk_text(clean, meta)
            print(f"[Main]   Chunks generados -> {len(chunks)}")
            all_chunks.extend(chunks)

    output_path = "data/processed/protocolos_chunks.json"
    chunker.save_chunks(all_chunks, output_path)

    # Estadísticas rápidas
    phases = {}
    for c in all_chunks:
        phases[c.fase_protocolo] = phases.get(c.fase_protocolo, 0) + 1
    print("\n[Main] Distribucion por fase:")
    for phase, count in sorted(phases.items()):
        print(f"  {phase}: {count} chunks")

