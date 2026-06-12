import re
from typing import List
from src.ingestion.chunking import DocumentChunk

class PromptBuilder:
    """Clase encargada de diseñar los prompts y aplicar los Guardrails de seguridad."""

    def __init__(self) -> None:
        # Palabras clave permitidas para determinar si la consulta está en el alcance
        # de siniestros viales o primeros auxilios.
        self.scope_keywords = [
            "accidente", "siniestro", "vial", "choque", "volcamiento", 
            "chofer", "herido", "lesionado", "ambulancia", "vía", "tránsito", 
            "conocimiento", "arribo", "intervención", "protocolo", "primeros auxilios",
            "asfixia", "fractura", "sangrado", "emergencia", "ayuda", "qué hacer", "colisión", 
            "vehículo", "automóvil", "camión", "moto", "motocicleta", "motociclista", "peatón", 
            "rescate", "atrapado", "auto", "camioneta", "bicicleta", "ciclista", "camionero"
        ]

        # Situaciones médicas de alto riesgo
        self.high_risk_medical_keywords = [
            "inconsciente", "no respira", "hemorragia", "shock", "convulsion", "convulsión", 
            "paro cardíaco", "paro cardiorespiratorio", "atrapado", "politraumatismo"
        ]

        # Situaciones legales
        self.legal_keywords = [
            "judicial", "peritaje", "perito", "demanda", "abogado", "tribunal", "juez", 
            "sentencia", "documentación", "agencia de seguros", "legal"
        ]

        # Llamadas de broma
        self.prank_keywords = [
            "broma", "jajaja", "prueba", "joda", "chiste"
        ]

    def get_system_prompt(self) -> str:
        """
        Retorna el System Prompt base con reglas estrictas de comportamiento.
        """
        return (
             "Eres el Asistente de Respuesta Temprana a Emergencias Viales, un sistema experto diseñado para proveer "
             "información rápida, clara y concisa a los operadores de emergencia en el lugar del hecho.\n\n"
             "OBJETIVO:\n"
             "Brindar información operativa inmediata utilizando exclusivamente los protocolos incluidos en el contexto provisto.\n\n"
             "REGLAS OBLIGATORIAS DE COMPORTAMIENTO (GUARDRAILS):\n"
             "1. Responde ÚNICAMENTE utilizando la información presente en el contexto provisto.\n"
             "2. No utilices conocimientos generales, inferencias, suposiciones ni información externa al contexto.\n"
             "3. Si la respuesta no se encuentra explícitamente en el contexto, si el contexto es insuficiente o si existe cualquier grado de incertidumbre, responde exactamente:\n"
             "   'No poseo ese procedimiento en mis protocolos de emergencia viales registrados. Por favor, realiza la consulta pertinente o procede según el protocolo general.'\n"
             "4. Bajo ninguna circunstancia inventes o alucines procedimientos médicos, de rescate, extinción o seguridad.\n"
             "5. Nunca diagnostiques enfermedades, lesiones, fracturas, hemorragias internas ni estados clínicos.\n"
             "6. Nunca recomiendes medicamentos, dosis, tratamientos, maniobras invasivas o procedimientos médicos avanzados que no estén explícitamente descritos en el contexto.\n"
             "7. Ante situaciones médicas críticas, no improvises instrucciones ni completes pasos faltantes del protocolo.\n"
             "8. Si una situación crítica no posee un procedimiento explícito en el contexto, utiliza el mensaje de respuesta por defecto y no generes contenido adicional.\n"
             "9. No asumas información sobre el estado de una víctima cuando los datos proporcionados sean incompletos.\n"
             "10. Considera como situaciones de alto riesgo: inconsciencia, ausencia de respiración, hemorragias graves, convulsiones, shock, atrapamiento severo y lesiones potencialmente fatales.\n"
             "11. Prioriza siempre la preservación de la vida humana y la seguridad de los intervinientes.\n"
             "12. Sé extremadamente directo y accionable.\n"
             "13. Cuando exista un procedimiento aplicable en el contexto:\n"
             "   - Preséntalo mediante viñetas.\n"
             "   - Respeta el orden de los pasos indicado en el protocolo.\n"
             "   - Destaca primero las acciones críticas o de riesgo vital.\n"
             "14. No incluyas explicaciones teóricas, opiniones, interpretaciones ni recomendaciones personales.\n"
             "15. NO menciones trámites administrativos, pericias judiciales, responsabilidades legales ni cuestiones burocráticas.\n"
             "16. Si existen múltiples procedimientos posibles, responde únicamente con el que mejor coincida con la consulta.\n\n"
             
             "FORMATO DE RESPUESTA:\n"
             "- Utiliza viñetas para cada acción.\n"
             "- Emplea frases cortas y directas.\n"
             "- Evita introducciones y conclusiones innecesarias.\n"
             "- Limita la respuesta a la información estrictamente necesaria para la actuación inmediata.\n"
        )

    def is_out_of_scope(self, query: str) -> bool:
        """
        Verifica si la consulta está fuera del alcance del manual de emergencias viales.
        
        Args:
            query (str): Consulta del usuario.
            
        Returns:
            bool: True si está fuera de alcance, False de lo contrario.
        """
        query_lower = query.lower()
        
        # Emergencias fuera del dominio del sistema
        if any(k in query_lower for k in self.legal_keywords):
            return True

        # Llamadas no válidas
        if any(k in query_lower for k in self.prank_keywords):
            return True
        
        # Emergencias viales válidas
        if any(k in query_lower for k in self.scope_keywords):
            return False
            
        return True

    def build_prompt(self, query: str, contexts: List[DocumentChunk]) -> str:
        """
        Construye el prompt final inyectando el contexto y la consulta.
        
        Args:
            query (str): Consulta del usuario.
            contexts (List[DocumentChunk]): Fragmentos recuperados de pgvector.
            
        Returns:
            str: Prompt completo formateado para el LLM.
        """
        # Formatear los fragmentos de contexto
        context_str = ""
        for idx, chunk in enumerate(contexts):
            fase = chunk.metadata.get("fase_protocolo", "GENERAL")
            context_str += f"[Documento {idx+1} - Fase: {fase}]\n{chunk.text}\n\n"

        prompt = (
            f"SYSTEM: {self.get_system_prompt()}\n\n"
            f"CONTEXTO DE PROTOCOLOS VIALES:\n"
            f"=========================================\n"
            f"{context_str}"
            f"=========================================\n\n"
            f"PREGUNTA DEL OPERADOR: {query}\n\n"
            f"RESPUESTA RÁPIDA (Paso a paso):"
        )
        return prompt

if __name__ == "__main__":
    builder = PromptBuilder()
    
    # Test dentro de alcance
    q1 = "¿Qué hacer ante un choque con heridos graves?"
    print(f"¿'{q1}' está fuera de alcance?: {builder.is_out_of_scope(q1)}")
    
    # Test llamada no valida
    q2 = "Esto es una broma"
    print(f"¿'{q2}' está fuera de alcance?: {builder.is_out_of_scope(q2)}")

    # Test fuera del alcance 
    q3 = "Necesito un peritaje judicial"
    print(f"¿'{q3}' está fuera de alcance?: {builder.is_out_of_scope(q3)}")

    
    # Mock chunks
    chunks = [
        DocumentChunk(text="FASE DE INTERVENCION: Estabilizar el cuello del lesionado si sospecha fractura.", metadata={"fase_protocolo": "INTERVENCION"})
    ]
    print("\n--- Prompt Construido ---")
    print(builder.build_prompt(q1, chunks))
