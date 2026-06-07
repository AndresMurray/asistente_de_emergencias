import time
import json
from typing import Generator
import requests

class OllamaClient:
    """Cliente para interactuar con la API local de Ollama o vLLM."""

    def __init__(self, base_url: str = "http://localhost:11434", model_name: str = "llama3:8b") -> None:
        """
        Inicializa el cliente de Ollama.
        
        Args:
            base_url (str): Dirección base de la API local de Ollama.
            model_name (str): Nombre del modelo a utilizar.
        """
        self.base_url = base_url
        self.model_name = model_name
        self.generate_url = f"{self.base_url}/api/generate"

    def generate_stream(self, prompt: str) -> Generator[str, None, None]:
        """
        Envía el prompt a la API local de Ollama y devuelve la respuesta en formato de streaming.
        Si la API no está disponible o falla, cae en un generador simulado (mock) para pruebas.
        
        Args:
            prompt (str): Prompt completo formateado.
            
        Yields:
            str: Token o fragmento de texto generado.
        """
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True
        }
        
        try:
            # Intentar conexión con tiempo de espera corto para evitar bloqueos
            response = requests.post(self.generate_url, json=payload, stream=True, timeout=2)
            
            if response.status_code == 200:
                print(f"[LLM Client] Conectado exitosamente a Ollama ({self.model_name}). Iniciando stream real...")
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line.decode('utf-8'))
                        token = data.get("response", "")
                        yield token
                return
            else:
                print(f"[LLM Client - Warning] Ollama retornó código {response.status_code}. Activando stream mock.")
        except (requests.exceptions.RequestException, Exception) as e:
            print(f"[LLM Client - Fallback] No se pudo establecer conexión con Ollama ({e}). Generando stream simulado...")

        # Simulación de respuesta en tiempo real (baja latencia) para la PoC
        mock_response = (
            "**PROTOCOLO DE ACCIÓN INMEDIATA:**\n\n"
            "1. **Fase de Toma de Conocimiento:** Registre la ubicación exacta del siniestro y la cantidad de lesionados.\n"
            "2. **Fase de Arribo al Lugar:** El equipo llega a la escena en menos de 10 minutos. Evalúe riesgos secundarios.\n"
            "3. **Fase de Intervención:** Brinde auxilio médico primario urgente y proceda a la estabilización de heridos graves.\n\n"
            "⚠️ *Mantenga la calma y espere el arribo de las ambulancias en comunicación constante.*"
        )
        
        # Simular streaming con palabras/tokens individuales y un retraso corto
        words = mock_response.split(" ")
        for word in words:
            yield word + " "
            time.sleep(0.04)  # Simula latencia de 40ms por token

if __name__ == "__main__":
    client = OllamaClient()
    print("--- Probando Streaming ---")
    for chunk in client.generate_stream("Test de conexión"):
        print(chunk, end="", flush=True)
    print("\n--- Streaming finalizado ---")
