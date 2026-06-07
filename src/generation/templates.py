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
            "asfixia", "fractura", "sangrado", "emergencia", "ayuda", "qué hacer"
        ]

    def get_system_prompt(self) -> str:
        """
        Retorna el System Prompt base con reglas estrictas de comportamiento.
        """
        return (
            "Eres el Asistente de Respuesta Temprana a Emergencias Viales, un sistema experto diseñado para proveer "
            "información rápida, clara y concisa a los operadores de emergencia en el lugar del hecho.\n\n"
            "REGLAS OBLIGATORIAS DE COMPORTAMIENTO (GUARDRAILS):\n"
            "1. Responde ÚNICAMENTE basándote en el contexto provisto.\n"
            "2. Si la respuesta no se encuentra en el contexto provisto o no estás completamente seguro, di exactamente:\n"
            "   'No poseo ese procedimiento en mis protocolos de emergencia viales registrados. Por favor, realiza la consulta pertinente o procede según el protocolo general.'\n"
            "3. Bajo ninguna circunstancia inventes o alucines procedimientos médicos o de seguridad.\n"
            "4. Sé extremadamente directo y prioriza la vida humana. Utiliza viñetas para instrucciones paso a paso.\n"
            "5. NO menciones trámites burocráticos ni pericias judiciales en la respuesta inmediata."
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
        
        # Filtro de términos judiciales o legales no accionables (deben redirigirse al 911)
        if any(kw in query_lower for kw in ["judicial", "peritaje", "perito", "prueba judicial", "muestra"]):
            return True
        
        # Si la consulta no tiene ninguna palabra relacionada con emergencias, se considera fuera de alcance
        has_keyword = any(kw in query_lower for kw in self.scope_keywords)
        
        # Filtro explícito para preguntas genéricas sin sentido para el asistente
        if not has_keyword:
            return True
            
        return False

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
    
    # Test fuera de alcance
    q2 = "Dame una receta para hacer pan."
    print(f"¿'{q2}' está fuera de alcance?: {builder.is_out_of_scope(q2)}")
    
    # Mock chunks
    chunks = [
        DocumentChunk(text="FASE DE INTERVENCION: Estabilizar el cuello del lesionado si sospecha fractura.", metadata={"fase_protocolo": "INTERVENCION"})
    ]
    print("\n--- Prompt Construido ---")
    print(builder.build_prompt(q1, chunks))
