import os
import re

class ProtocolExtractor:
    """Clase encargada de la extracción y limpieza del texto de protocolos oficiales."""

    def __init__(self) -> None:
        pass

    def extract_text(self, pdf_path: str) -> str:
        """
        Extrae el texto plano crudo del archivo PDF especificado.
        
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
        
        # Simulación de extracción si el archivo existe
        filename = os.path.basename(pdf_path)
        return f"Contenido extraído del archivo real: {filename}. Detalle de emergencia vial..."

    def clean_text(self, raw_text: str) -> str:
        """
        Limpia el texto plano extraído eliminando secciones no accionables 
        para la respuesta de emergencia (por ejemplo, pericias judiciales).
        
        Args:
            raw_text (str): Texto crudo recién extraído.
            
        Returns:
            str: Texto limpio y optimizado para el procesamiento.
        """
        # Limpieza básica de espacios múltiples
        cleaned = re.sub(r'\s+', ' ', raw_text).strip()
        
        # Ejemplo de regla de limpieza: remover secciones legales no relevantes para respuesta rápida
        # Esto cumple con la tarea asignada a Andrés (limpieza de pericias judiciales/pruebas)
        cleaned = re.sub(r'INFORMACION JUDICIAL Y PRESERVACION DE PRUEBAS:.*$', '', cleaned, flags=re.IGNORECASE)
        
        return cleaned.strip()

if __name__ == "__main__":
    extractor = ProtocolExtractor()
    raw = extractor.extract_text("data/raw/protocolo_siniestros.pdf")
    clean = extractor.clean_text(raw)
    print("--- Texto Crudo ---")
    print(raw)
    print("\n--- Texto Limpio ---")
    print(clean)
