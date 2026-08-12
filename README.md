# Asistente de Respuesta Temprana a Emergencias Viales - LiveKit Agent & RAG Cloud

Este repositorio contiene la arquitectura actualizada y optimizada para un **Asistente de Respuesta Temprana a Emergencias Viales** que opera por voz en tiempo real. 

El sistema utiliza **LiveKit Agents** para la conexión WebRTC multiturno, conectándose a bases de datos e inferencias 100% en la nube para garantizar baja latencia y alta disponibilidad.

---

## 🛠️ Stack Tecnológico Actual

- **Orquestación de Voz en Tiempo Real**: [LiveKit Agents SDK](https://docs.livekit.io/agents/) (Python)
- **STT (Reconocimiento de Voz)**: **Deepgram** (`nova-3`, Español `es`)
- **LLM (Cerebro de Inferencia)**: **OpenAI** (`gpt-4o-mini`)
- **TTS (Síntesis de Voz)**: **Cartesia** / **Deepgram** (`aura-2-agustina-es` o `sonic-3`)
- **RAG (Recuperación y Embeddings)**:
  - **Modelos de Embeddings**: **Cohere** (`embed-multilingual-v3.0` de 1024 dimensiones)
  - **Base de Datos Vectorial**: **Supabase** (PostgreSQL + `pgvector`)

---

## 📂 Estructura del Proyecto

```text
asistente_de_emergencias/
│
├── data/                         # Datos locales (ignorados en git)
│   ├── raw/                      # PDFs oficiales de los protocolos de emergencia
│   └── processed/                # JSONs procesados conteniendo los chunks de texto
│
├── ingestion/                    # Pipeline de datos (PDF -> Supabase)
│   ├── chunking.py               # Extrae texto limpio de los PDFs y genera el archivo de chunks JSON
│   ├── extractors.py             # Extrae y limpia texto plano de PDFs usando PyPDF2/pdfplumber
│   └── ingest.py                 # Calcula embeddings (Cohere) e inserta los chunks en Supabase
│
├── metricas/                     # Carpeta de Métricas y Evaluación del sistema
│   ├── critical_information_coverage.py  # Métrica multiturno con evaluación local y soporte de LiveKit Cloud
│   ├── mrr.py                    # Métrica de Mean Reciprocal Rank (MRR)
│   ├── answer_relevancy.py       # Métrica de relevancia de respuestas
│   └── recall_at_5.py            # Métrica de Recall @ 5
│
├── benchmarks/                   # Benchmarks de rendimiento y latencia
│   └── benchmark.py              # Medición de TTFT y tokens/seg en Ollama
│
├── docs/                         # Documentación técnica
│   └── arquitectura_stack.md     # Documento técnico detallando el flujo de datos
│
├── agent.py                      # Código principal del agente LiveKit (voz y chat)
├── livekit.toml                  # Configuración de despliegue para LiveKit CLI
├── requirements.txt              # Dependencias del proyecto
└── .env.local                    # Archivo de configuración de variables de entorno locales
```

---

## ⚙️ Configuración y Variables de Entorno

Crea un archivo `.env.local` en la raíz del proyecto con la siguiente configuración:

```env
# Cohere (Generación de embeddings en la ingesta)
COHERE_API_KEY=tu_cohere_key

# Base de Datos (Supabase)
DATABASE_URL=postgresql://postgres.vbspedxghlkucshoacif:Z%26%40q8XKA%2Af%21%2BJ7F@aws-1-us-west-2.pooler.supabase.com:5432/postgres

# Conexión LiveKit Cloud (para pruebas WebRTC remotas)
LIVEKIT_URL=wss://tu-proyecto.livekit.cloud
LIVEKIT_API_KEY=tu_api_key
LIVEKIT_API_SECRET=tu_api_secret
```

---

## 🚀 Guía de Uso

### 1. Ingesta de Nuevos Protocolos (RAG)
Si deseas agregar nuevos manuales de emergencias en PDF:
1. Coloca los archivos `.pdf` en la carpeta `data/raw/`.
2. Genera los fragmentos de texto (chunks):
   ```bash
   python ingestion/chunking.py data/raw/
   ```
   *Esto guardará los fragmentos estructurados en `data/processed/protocolos_chunks.json`.*
3. Sube los fragmentos y sus embeddings a Supabase:
   ```bash
   python ingestion/ingest.py
   ```

### 2. Ejecutar el Agente Localmente (Desarrollo)
Para iniciar el agente de LiveKit en modo desarrollo:
```bash
python agent.py dev
```

### 3. Evaluar Cobertura de Información Crítica (Métrica Coverage)
La métrica simula llamadas multiturno y evalúa si el agente transmitió todos los puntos críticos del protocolo oficial (exigiendo un score `>= 0.8`).

Ejecutar la suite de pruebas mediante pytest:
```bash
pytest metricas/critical_information_coverage.py -v
```

*Nota: La prueba se conectará a tu sala de LiveKit Cloud mediante WebRTC si las credenciales de LiveKit están configuradas, y enviará consultas de texto. Si el agente en la nube no responde a tiempo, conmutará automáticamente al simulador local e implementará una validación heurística de cobertura sin requerir créditos externos.*
