import os
import re

# PyMuPDF se importa como 'fitz'. Si no está instalado, el extracto real no funciona
# pero el fallback mock permite que el resto del equipo siga sin romper la PoC.
try:
    import fitz  # pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("[Extractor] AVISO: PyMuPDF no está instalado. Ejecutar: pip install pymupdf")


class ProtocolExtractor:
    """Clase encargada de la extracción y limpieza del texto de protocolos oficiales."""

    def __init__(self) -> None:
        pass

    def extract_text(self, pdf_path: str) -> str:
        """
        Extrae el texto plano crudo del archivo PDF especificado usando PyMuPDF.
        Concatena el contenido de todas las páginas del documento.

        Args:
            pdf_path (str): Ruta absoluta o relativa al archivo PDF.

        Returns:
            str: El texto crudo extraído del archivo.
        """
        if not os.path.exists(pdf_path):
            # Retorno simulado si el archivo no existe para permitir ejecuciones de PoC
            print(f"[Extractor - Mock] El archivo '{pdf_path}' no existe. Devolviendo texto de protocolo simulado.")
            return (
                "PROTOCOLO OFICIAL DE ACTUACION ANTE SINIESTROS VIALES\n"
                "FASE DE TOMA DE CONOCIMIENTO:\n"
                "El operador recibe la llamada de emergencia. Se deben registrar: ubicación exacta, tipo de siniestro y lesionados.\n"
                "FASE DE ARRIBO AL LUGAR:\n"
                "El equipo de emergencia llega al lugar en menos de 10 minutos. Evaluar la escena por riesgos secundarios.\n"
                "FASE DE INTERVENCION:\n"
                "Brindar auxilio médico a los heridos graves. Priorizar estabilización.\n"
                "INFORMACION JUDICIAL Y PRESERVACION DE PRUEBAS:\n"
                "Asegurar la escena y esperar peritos judiciales para la toma de muestras del accidente."
            )

        if not PYMUPDF_AVAILABLE:
            print(f"[Extractor] PyMuPDF no disponible. Instalá: pip install pymupdf")
            return ""

        pages_text = []
        try:
            with fitz.open(pdf_path) as doc:
                print(f"[Extractor] Procesando '{os.path.basename(pdf_path)}' — {len(doc)} páginas.")
                for page_num, page in enumerate(doc, start=1):
                    page_text = page.get_text("text")
                    if page_text.strip():
                        pages_text.append(page_text)

        except Exception as e:
            print(f"[Extractor] Error al leer '{pdf_path}': {e}")
            return ""

        raw_text = "\n".join(pages_text)
        print(f"[Extractor] Texto crudo extraído: {len(raw_text)} caracteres.")
        return raw_text

    def clean_text(self, raw_text: str) -> str:
        """
        Limpia el texto plano extraído eliminando secciones no accionables
        para la respuesta de emergencia (pericias judiciales, artefactos de PDF,
        headers/footers repetidos, numeración de páginas, etc.).

        Args:
            raw_text (str): Texto crudo recién extraído.

        Returns:
            str: Texto limpio y optimizado para el procesamiento.
        """
        cleaned = raw_text

        # ── 0. Filtrar por secciones específicas (Temas 3, 4, 5 y 6) ──────────
        # Si el documento contiene TEMA 1, TEMA 2 y TEMA 3, nos quedamos solo con TEMA 3 hasta BIBLIOGRAFÍA
        if "TEMA 3" in cleaned and "TEMA 1" in cleaned and "TEMA 2" in cleaned:
            tema3_matches = list(re.finditer(r'^\s*TEMA\s+3\s*$', cleaned, flags=re.MULTILINE))
            if tema3_matches:
                start_idx = tema3_matches[0].start()
                bib_match = re.search(r'^\s*BIBLIOGRAF[IÍ]A\s*$', cleaned, flags=re.MULTILINE | re.IGNORECASE)
                if bib_match:
                    end_idx = bib_match.start()
                    cleaned = cleaned[start_idx:end_idx]
                else:
                    cleaned = cleaned[start_idx:]
                print(f"[Extractor] Preprocesamiento: Conservados Temas 3 a 6 ({len(cleaned)} caracteres).")

        # ── 1. Eliminar secciones judiciales / periciales completas ──────────────
        # Se eliminan desde el encabezado de la sección hasta el final del bloque
        # (hasta doble salto de línea o inicio de otra sección reconocida).
        judicial_patterns = [
            r'INFORMACI[OÓ]N JUDICIAL.*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
            r'PRESERVACI[OÓ]N DE PRUEBAS.*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
            r'CADENA DE CUSTODIA.*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
            r'PERITOS?[:\s].*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
            r'ACTUACI[OÓ]N PERICIAL.*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
            r'DECLARACI[OÓ]N TESTIMONIAL.*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
            r'INSTRUCCI[OÓ]N JUDICIAL.*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
            r'FALLO JUDICIAL.*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
            r'EXPEDIENTE\s+N[°º]?\s*\d+.*?(?=\n[A-ZÁÉÍÓÚÑ]{4,}:|\Z)',
        ]
        for pattern in judicial_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.DOTALL)

        # ── 2. Eliminar artefactos comunes de PDFs ───────────────────────────────
        # Números de página aislados (ej. "- 12 -", "Página 3 de 45", "3\n")
        cleaned = re.sub(r'[-–]\s*\d{1,4}\s*[-–]', '', cleaned)
        cleaned = re.sub(r'[Pp][áa]gina\s+\d+\s+de\s+\d+', '', cleaned)
        cleaned = re.sub(r'^\s*\d{1,4}\s*$', '', cleaned, flags=re.MULTILINE)

        # URLs y correos electrónicos de pie de página
        cleaned = re.sub(r'https?://\S+', '', cleaned)
        cleaned = re.sub(r'\S+@\S+\.\S+', '', cleaned)

        # Líneas de solo guiones, asteriscos o subrayados (separadores visuales)
        cleaned = re.sub(r'^[\s\-_=*]{3,}$', '', cleaned, flags=re.MULTILINE)

        # ── 3. Limpiar ligaduras y caracteres unicode problemáticos de PDFs ──────
        unicode_replacements = {
            '\ufb01': 'fi',   # ﬁ ligadura
            '\ufb02': 'fl',   # ﬂ ligadura
            '\u2019': "'",    # comilla tipográfica derecha
            '\u2018': "'",    # comilla tipográfica izquierda
            '\u201c': '"',
            '\u201d': '"',
            '\u2013': '-',    # guión en
            '\u2014': '-',    # guión em
            '\u00a0': ' ',    # espacio no separable
            '\u2022': '-',    # viñeta
        }
        for char, replacement in unicode_replacements.items():
            cleaned = cleaned.replace(char, replacement)

        # ── 4. Detectar y eliminar headers/footers repetidos ────────────────────
        # Líneas que aparecen más de 3 veces en el documento son candidatas a
        # encabezados o pies de página repetidos.
        lines = cleaned.split('\n')
        from collections import Counter
        line_counts = Counter(ln.strip() for ln in lines if len(ln.strip()) > 10)
        repeated_lines = {ln for ln, count in line_counts.items() if count >= 3}
        if repeated_lines:
            lines = [ln for ln in lines if ln.strip() not in repeated_lines]
            cleaned = '\n'.join(lines)

        # ── 5. Normalización de espacios y líneas en blanco ──────────────────────
        # Colapsar múltiples líneas en blanco consecutivas en máximo dos
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        # Eliminar espacios múltiples dentro de una línea
        cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
        # Limpiar espacios al inicio y fin de cada línea
        cleaned = '\n'.join(ln.strip() for ln in cleaned.split('\n'))

        return cleaned.strip()


if __name__ == "__main__":
    import glob

    extractor = ProtocolExtractor()
    pdf_files = glob.glob("data/raw/*.pdf")

    if not pdf_files:
        print("[Main] No se encontraron PDFs en data/raw/. Usando mock.")
        raw = extractor.extract_text("data/raw/protocolo_inexistente.pdf")
        clean = extractor.clean_text(raw)
        print("--- Texto Limpio (Mock) ---")
        print(clean[:1000])
    else:
        for pdf_path in pdf_files:
            print(f"\n{'='*60}")
            print(f"Procesando: {pdf_path}")
            raw = extractor.extract_text(pdf_path)
            clean = extractor.clean_text(raw)
            print(f"Caracteres tras limpieza: {len(clean)}")
            print("--- Primeros 500 chars ---")
            print(clean[:500])
