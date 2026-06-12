# Estructura del Proyecto y Guía de Desarrollo para el Equipo

Este documento detalla la arquitectura de la Prueba de Concepto (PoC) del **Asistente de Respuesta Temprana a Emergencias Viales**, el estado actual del código base ("contratos y mocks") y las tareas técnicas específicas que cada integrante debe realizar en su respectiva rama de Git.

---

## 🏛️ Arquitectura de la PoC: Contratos y Mocks

Para que todo el equipo pueda programar de forma simultánea sin bloquearse, el proyecto se ha estructurado con **Contratos de Software (firmas de funciones y tipados estáticos)** y **Mocks (simuladores en memoria)**.

### ¿Qué significa esto?
- **Ejecución desde el Día 1:** Si corres `python tests_eval/evaluator.py`, el pipeline ejecutará y responderá de inmediato.
- **Independencia de Tareas:** Si el Integrante 3 aún no ha configurado Ollama, Salvador todavía puede desarrollar y probar el módulo de base de datos porque el pipeline principal tiene mocks autocontenidos.
- **Integridad de Tipado:** Todas las clases y funciones usan `Type Hints` en Python para evitar fallos de compilación e integración al momento de fusionar las ramas (`merge`).

---

## 📁 Árbol de Directorios y Archivos Creados

```text
asistente-emergencias-rag/
├── data/
│   ├── raw/                 # PDFs oficiales en bruto
│   └── processed/           # JSONs/Markdown limpios procesados
├── src/                     # Código fuente principal
│   ├── __init__.py          # Inicializador de paquete src
│   ├── ingestion/           # Extracción y partición (Andrés)
│   │   ├── __init__.py
│   │   ├── extractors.py    # Clase ProtocolExtractor (extracción y limpieza)
│   │   └── chunking.py      # Clase ProtocolChunker y DocumentChunk (Pydantic)
│   ├── retrieval/           # Base de datos vectorial (Salvador)
│   │   ├── __init__.py
│   │   ├── vector_store.py  # Clase VectorStoreManager (conexión pgvector y esquema)
│   │   └── search.py        # Clase VectorSearcher (embeddings e índice HNSW)
│   ├── generation/          # Prompts y API del LLM (Integrantes 3 y 4)
│   │   ├── __init__.py
│   │   ├── llm_client.py    # Clase OllamaClient (conexión e inferencia local)
│   │   └── templates.py     # Clase PromptBuilder (guardrails y 911 fallback)
│   └── main.py              # Clase Pipeline (orquestador compatible con Open WebUI)
├── tests_eval/              # Framework de evaluación automatizada
│   ├── test_dataset.json    # Preguntas de prueba e indicaciones esperadas
│   └── evaluator.py         # Script evaluador de latencias y cumplimiento de guardrails
├── requirements.txt         # Dependencias del sistema
├── .gitignore               # Exclusiones de control de versiones Git
└── hoja_ruta_quincena.md    # Asignaciones del equipo y hitos
```

---

## 🛠️ Estado Actual vs. Tarea por Integrante

### 👤 Andrés: Curación de Datos e Ingesta
* **Rama:** `feature/data-ingestion`
* **Lo que está hecho (Mock):**
  - [`extractors.py`](file:///c:/Users/ASUS/Desktop/LS/Construccion%20sistemas%20RAG/Asistente_de_emergencias/src/ingestion/extractors.py): Si el archivo PDF no existe, retorna un texto plano simulado en memoria. La limpieza de texto utiliza una expresión regular simple.
  - [`chunking.py`](file:///c:/Users/ASUS/Desktop/LS/Construccion%20sistemas%20RAG/Asistente_de_emergencias/src/ingestion/chunking.py): El particionado se simula buscando palabras clave específicas y dividiendo el texto por secciones estáticas.
* **Lo que DEBES hacer en tu rama:**
  1. Instalar y configurar una librería de Python para extraer texto de PDF (por ejemplo, `pdfplumber`, `pypdf` o `PyMuPDF`).
  2. Implementar la lectura real del archivo PDF oficial ubicado en `data/raw/`.
  3. Perfeccionar el método `clean_text` para eliminar secciones judiciales o periciales no deseadas para la respuesta a emergencias.
  4. Desarrollar un algoritmo de particionado real (ej. *Recursive Character Splitter* o particionado semántico) en `ProtocolChunker`.
  5. Asegurar la persistencia de los metadatos de fase (Toma de conocimiento, arribo, intervención) en el modelo Pydantic `DocumentChunk`.
  6. Exportar los chunks a un archivo JSON en `data/processed/` para que Salvador pueda consumirlos.

---

### 👤 Salvador: Base de Datos Vectorial ✅ IMPLEMENTADO
* **Rama:** `feature/vector-retrieval`
* **Doc detallado:** [`docs/modulo_retrieval_salvador.md`](docs/modulo_retrieval_salvador.md)
* **Estado actual (real, sin mock):**
  - [`vector_store.py`](src/retrieval/vector_store.py): Conexión real a PostgreSQL 17 con `psycopg2` + `pgvector` 0.8.2. Crea la extensión, el esquema `protocol_chunks` con `VECTOR(768)` e inserta los chunks en lote (`execute_values` + upsert). `insert_from_json()` lee el JSON de Andrés y genera+inserta los embeddings. Mantiene fallback a memoria si faltan drivers.
  - [`search.py`](src/retrieval/search.py): Embeddings reales vía API de Ollama con el modelo multilingüe liviano `paraphrase-multilingual` (768 dim). `search_similarity()` consulta por distancia de coseno (`<=>`) real y `create_hnsw_index()` crea el índice HNSW (`vector_cosine_ops`).
* **Tareas completadas:**
  1. ✅ PostgreSQL local + extensión `pgvector`.
  2. ✅ Conexión real en `VectorStoreManager.connect` con `psycopg2`.
  3. ✅ Tabla `protocol_chunks` con columna de embeddings.
  4. ✅ Ingesta del JSON de Andrés (`insert_from_json` + `insert_chunks`).
  5. ✅ `get_embeddings` real en español vía Ollama (`paraphrase-multilingual`).
  6. ✅ `search_similarity` con similitud de coseno real en PostgreSQL.
  7. ✅ Índice HNSW en la columna de embeddings.
* **Nota de integración:** las firmas públicas (`insert_chunks(chunks)`,
  `search_similarity(query, limit)`) se mantienen intactas; los embeddings se generan
  internamente. Detalles y guía de testing en el doc del módulo.

---

### 👤 Integrante 3: Infraestructura LLM Local
* **Rama:** `feature/local-llm`
* **Lo que está hecho (Mock):**
  - [`llm_client.py`](file:///c:/Users/ASUS/Desktop/LS/Construccion%20sistemas%20RAG/Asistente_de_emergencias/src/generation/llm_client.py): Simula una conexión HTTP. Al fallar, actúa como un generador de streaming devolviendo un texto predefinido palabra por palabra con un retardo controlado de 40ms.
* **Lo que DEBES hacer en tu rama:**
  1. Instalar y levantar Ollama localmente (o configurar un entorno con vLLM o Llama.cpp).
  2. Descargar los modelos a evaluar (ej. `llama3:8b`, `phi3` o `gemma2`).
  3. Modificar `OllamaClient.generate_stream` para realizar una petición HTTP real en streaming (usando `requests(stream=True)`) al endpoint local de Ollama `/api/generate`.
  4. Garantizar que los chunks de texto recibidos del LLM real sean decodificados y transmitidos ("yielded") hacia la interfaz del usuario sin retrasos innecesarios.

---

### 👤 Alex: Prompt Engineering y Reglas de Seguridad
* **Rama:** `feature/prompt-generation`
* **Lo que está hecho (Mock):**
  - [`templates.py`](file:///c:/Users/ASUS/Desktop/LS/Construccion%20sistemas%20RAG/Asistente_de_emergencias/src/generation/templates.py): Tiene definidos los prompts iniciales y un analizador simple de términos de exclusión (judiciales/incompatibles) para derivar al 911.
* **Lo que DEBES hacer en tu rama:**
  1. Refinar y iterar sobre el System Prompt base en `get_system_prompt` para guiar al modelo a responder con extrema claridad, usando viñetas y priorizando pasos críticos.
  2. Ampliar las reglas de Guardrails para evitar alucinaciones médicas de alto riesgo en situaciones críticas.
  3. Programar lógica de validación semántica más avanzada en `is_out_of_scope` para interceptar de manera precisa preguntas ajenas a emergencias viales o protocolos judiciales.
  4. Testear localmente (mediante consola o UI) el prompt inyectando contextos simulados con diferentes dificultades para comprobar que el modelo no invente instrucciones que no están en el manual.

---

### 👤 Lauty: Docker y Orquestación de Open WebUI
* **Rama:** `feature/pipeline-orchestrator`
* **Lo que está hecho (Mock):**
  - [`main.py`](file:///c:/Users/ASUS/Desktop/LS/Construccion%20sistemas%20RAG/Asistente_de_emergencias/src/main.py): Orquestador listo con el formato de clase e inicio/cierre requeridos por Open WebUI.
* **Lo que DEBES hacer en tu rama:**
  1. Crear un archivo `docker-compose.yml` en la raíz del proyecto para empaquetar de forma homogénea los contenedores de:
     - PostgreSQL (habilitando la extensión `pgvector`).
     - Servicio de Ollama (configurando el acceso a GPU si está disponible).
     - Open WebUI.
  2. Validar que al correr `docker-compose up` todo el ecosistema levante sin problemas en cualquier máquina del equipo.
  3. Implementar en `main.py` cualquier hook adicional que requiera la interfaz Open WebUI.
  4. Realizar la integración del archivo `main.py` dentro del gestor de Pipelines de Open WebUI, verificando el correcto envío y recepción de datos.

---

## 🤝 Flujo de Integración y Sincronización

Para evitar romper los contratos establecidos en la rama principal (`main`):
1. **No modifiques las firmas ni los nombres de los métodos base** sin comunicarlo al resto del grupo. Los nombres como `pipe()`, `extract_text()`, `insert_chunks()`, `search_similarity()` y `generate_stream()` deben mantenerse.
2. Cada integrante debe trabajar de forma aislada en su propia rama `feature/...`.
3. Al finalizar cada módulo, se debe crear un Pull Request (PR) hacia la rama principal.
4. Antes de fusionar (`merge`), ejecuten el validador automatizado:
   ```bash
   $env:PYTHONPATH="."
   python tests_eval/evaluator.py
   ```
   *Si todas las pruebas marcan `PASSED` y el promedio de latencia cumple con los requerimientos, la integración es segura.*
