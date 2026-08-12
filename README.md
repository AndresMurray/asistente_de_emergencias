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
DATABASE_URL=tudatabase_url

# Conexión LiveKit Cloud (para pruebas WebRTC remotas)
LIVEKIT_URL=tulivekiturl
LIVEKIT_API_KEY=tu_api_key
LIVEKIT_API_SECRET=tu_api_secret

# Clon de Voz
CARTESIA_API_KEY=tu_api_key

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

### 3. Despliegue en LiveKit Cloud (Producción)

Para desplegar el agente en LiveKit Cloud, se utiliza el CLI oficial de LiveKit (`lk`).

#### Prerrequisitos:
1. Tener instalado el **LiveKit CLI** (`lk`).
2. Autenticarse en tu cuenta de LiveKit Cloud:
   ```bash
   lk cloud auth
   ```

#### Comando de Despliegue:
Para subir cambios en el código o en las dependencias al agente en la nube:
```bash
lk agent deploy
```
*Este comando lee el archivo [livekit.toml](file:///c:/Users/ASUS/Desktop/LS/Construccion%20sistemas%20RAG/Asistente_de_emergencias/livekit.toml) en la raíz del proyecto para identificar la aplicación y el ID del agente, compila el entorno y realiza el redespliegue.*

---

#### ❓ ¿Qué cambios requieren redespliegue y cuáles no?

| Tipo de Cambio | ¿Requiere Despliegue (`lk agent deploy`)? | Detalles / Acción Requerida |
| :--- | :---: | :--- |
| **Código del Agente** (`agent.py` o scripts importados) | **Sí** | Cualquier cambio en la lógica de respuestas, prompts del LLM, herramientas de función (`function_tool`), configuración de voces, etc. |
| **Dependencias del Proyecto** (`requirements.txt`) | **Sí** | Al modificar o añadir librerías en `requirements.txt`, es necesario redesplegar para reconstruir la imagen del contenedor con el nuevo entorno. |
| **Configuraciones de LiveKit** (`livekit.toml`) | **Sí** | Cambios que afecten la metadata o identificadores del agente en LiveKit. |
| **Ingesta de Documentos (Base de Datos)** | **No** | Si agregas nuevos PDFs y ejecutas la ingesta (`ingest.py`), los cambios impactan directamente a la base de datos remota en Supabase. El agente en producción consume esta base de datos dinámicamente en tiempo real. |
| **Variables de Entorno en Producción** | **No** *(Requiere configuración en consola)* | Las variables de entorno de producción (como `COHERE_API_KEY`, `DATABASE_URL`, etc.) **no** se suben a través del archivo local `.env.local` por motivos de seguridad. Debes configurarlas en el **LiveKit Cloud Dashboard** en la sección de configuraciones del Agente. Al guardarlas en la consola de LiveKit, se aplican automáticamente sin requerir un comando de despliegue. |

