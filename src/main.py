import os
from typing import List, Generator, Union
from pydantic import BaseModel, Field

from src.retrieval.vector_store import VectorStoreManager
from src.retrieval.search import VectorSearcher
from src.generation.templates import PromptBuilder
from src.generation.llm_client import OllamaClient

class Pipeline:
    """Clase principal compatible con el framework de Pipelines de Open WebUI."""

    class Valves(BaseModel):
        """Configuraciones ajustables desde el panel de control de Open WebUI."""
        DATABASE_URL: str = Field(
            default="postgresql://postgres:postgres@localhost:5432/emergencias_db",
            description="URI de conexión de PostgreSQL/pgvector"
        )
        OLLAMA_URL: str = Field(
            default="http://localhost:11434",
            description="URL del servicio local de Ollama o vLLM"
        )
        MODEL_NAME: str = Field(
            default="llama3:8b",
            description="Nombre del modelo LLM local a utilizar"
        )

    def __init__(self) -> None:
        self.name = "Early Emergency Response RAG"
        self.valves = self.Valves()
        self.db_manager = None
        self.searcher = None
        self.prompt_builder = PromptBuilder()
        self.llm_client = None

    async def on_startup(self) -> None:
        """Ciclo de vida: Ejecutado al iniciar el pipeline en Open WebUI."""
        print(f"[Pipeline] Inicializando {self.name}...")
        self.db_manager = VectorStoreManager(dsn=self.valves.DATABASE_URL)
        self.db_manager.connect()
        self.db_manager.initialize_schema()
        
        self.searcher = VectorSearcher(self.db_manager)
        self.llm_client = OllamaClient(
            base_url=self.valves.OLLAMA_URL, 
            model_name=self.valves.MODEL_NAME
        )
        print("[Pipeline] Inicialización completa.")

    async def on_shutdown(self) -> None:
        """Ciclo de vida: Ejecutado al apagar el pipeline en Open WebUI."""
        if self.db_manager:
            self.db_manager.close()
        print("[Pipeline] Finalizado.")

    def pipe(
        self, 
        user_message: str, 
        model_id: str, 
        messages: List[dict]
    ) -> Union[str, Generator[str, None, None]]:
        """
        Método de ejecución de tubería obligatorio en Open WebUI.
        Recibe el mensaje del usuario y retorna un generador (stream) o string de respuesta.
        
        Args:
            user_message (str): Mensaje actual del usuario.
            model_id (str): Identificador del modelo solicitado.
            messages (List[dict]): Historial completo del chat.
            
        Returns:
            Union[str, Generator[str, None, None]]: Respuesta final.
        """
        # Inicialización diferida por seguridad si no se corre vía on_startup (e.g. testing directo)
        if not self.db_manager:
            self.db_manager = VectorStoreManager(dsn=self.valves.DATABASE_URL)
            self.db_manager.connect()
            self.searcher = VectorSearcher(self.db_manager)
            self.llm_client = OllamaClient(
                base_url=self.valves.OLLAMA_URL, 
                model_name=self.valves.MODEL_NAME
            )

        # 1. Regla Dura / Guardrail: Validar si la consulta está fuera del alcance de emergencias
        if self.prompt_builder.is_out_of_scope(user_message):
            out_of_scope_msg = "No poseo ese procedimiento, por favor comunícate con el 911"
            print(f"[Pipeline - Guardrail] Consulta fuera de alcance detectada: '{user_message}'")
            return out_of_scope_msg

        # 2. Recuperación (Retrieval)
        # Recupera los fragmentos semánticamente más similares usando pgvector
        contexts = self.searcher.search_similarity(user_message, limit=2)
        
        # 3. Prompt Engineering
        # Construye el prompt estructurado con directrices de seguridad
        prompt = self.prompt_builder.build_prompt(user_message, contexts)
        
        # 4. Generación (Generation)
        # Llama al cliente LLM en formato streaming
        return self.llm_client.generate_stream(prompt)

if __name__ == "__main__":
    # Script ejecutable de prueba local
    import asyncio
    
    async def test_run():
        pipe_instance = Pipeline()
        await pipe_instance.on_startup()
        
        print("\n=== PRUEBA 1: CONSULTA DENTRO DE ALCANCE ===")
        user_q = "¿Qué datos se deben registrar al tomar conocimiento de un siniestro vial?"
        response = pipe_instance.pipe(user_q, "mock-model", [])
        
        if isinstance(response, str):
            print(response)
        else:
            for token in response:
                print(token, end="", flush=True)
            print()

        print("\n=== PRUEBA 2: CONSULTA FUERA DE ALCANCE ===")
        out_q = "¿Cuál es el mejor equipo de fútbol de Argentina?"
        response_out = pipe_instance.pipe(out_q, "mock-model", [])
        print(response_out)
        
        await pipe_instance.on_shutdown()

    asyncio.run(test_run())
