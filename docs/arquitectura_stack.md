# Asistente de Emergencias Viales - Stack y Flujo de Ejecución

Este documento resume la arquitectura actualizada, el stack tecnológico 100% cloud y el flujo de datos para el asistente de voz en tiempo real.

## 🛠️ Stack Tecnológico Actual

El proyecto fue migrado de un procesamiento RAG local a un esquema completamente en la nube (serverless y APIs gratuitas/freemium) para maximizar la velocidad y reducir el consumo de recursos.

- **Framework Core**: [LiveKit Agents](https://docs.livekit.io/agents/) (Python)
- **STT (Reconocimiento de Voz)**: **Deepgram** 
  - Modelo: `nova-3`
  - Idioma: Español (`es`)
- **LLM (Cerebro e Inferencia)**: **Groq** 
  - Modelo: `llama-3.3-70b-versatile` (Integrado a través del plugin de OpenAI)
- **TTS (Síntesis de Voz)**: **Deepgram**
  - Modelo: `aura-2-agustina-es` (Voz nativa en español)
- **Embeddings (RAG)**: **Cohere**
  - Modelo: `embed-multilingual-v3.0` (1024 dimensiones)
- **Base de Datos Vectorial**: **Supabase** (PostgreSQL + pgvector)
  - Tabla: `chunks`

---

## 🔄 Flujo del Sistema

El funcionamiento se divide en dos grandes etapas:

### 1. Fase de Ingesta (`ingest.py`)
1. **Carga**: Lee los protocolos de emergencia desde el archivo local `protocolos_chunks.json`.
2. **Generación de Vectores**: Llama a la API HTTP de Cohere (`embed-multilingual-v3.0`) para vectorizar cada texto.
3. **Almacenamiento**: Se conecta vía `psycopg2` directamente al pool de conexiones de Supabase y guarda el par `(texto, vector)` en la tabla `chunks`. 
   *(Si se usa el flag `--reset`, la tabla se vacía antes de insertar).*

### 2. Fase de Ejecución en Tiempo Real (`agent.py`)
El asistente corre como un servidor en espera de conexiones a una sala (Room) de LiveKit.

1. **Escucha y Transcripción (STT)**: 
   - El operador habla. Deepgram convierte el audio a texto en tiempo real.
2. **Razonamiento (LLM)**: 
   - El texto llega al modelo Llama 3.3 alojado en Groq.
   - Si la consulta requiere conocimiento específico, el LLM decide utilizar la herramienta (tool) `buscar_protocolo`.
3. **Recuperación Vectorial (RAG)**:
   - *Dentro de `buscar_protocolo`:* Se vectoriza la pregunta del usuario usando Cohere.
   - Se ejecuta una búsqueda de similitud asíncrona (`<=>`) en Supabase para recuperar los fragmentos de protocolo más relevantes (TOP_K = 3).
   - Este paso corre en un *hilo secundario* (`asyncio.to_thread`) para no bloquear el flujo asíncrono de LiveKit.
4. **Respuesta Contextualizada**:
   - Los protocolos recuperados se inyectan en el prompt del LLM. Llama redacta una respuesta táctica, directa y accionable.
5. **Síntesis de Audio (TTS)**:
   - Deepgram recibe el texto generado por Llama y lo convierte a audio con voz en español (`aura-2-agustina-es`).
   - El audio se envía de inmediato al operador por el canal WebRTC de LiveKit.
