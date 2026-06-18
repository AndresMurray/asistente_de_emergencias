# Asistente de Respuesta Temprana a Emergencias Viales - PoC RAG

https://drive.google.com/drive/u/1/folders/1gd0nOFq6WJUgUpMEAZjwt4JArX_Nic_G

Este proyecto es una Prueba de Concepto (PoC) para un **Asistente de Respuesta Temprana a Emergencias Viales** auto-alojado localmente y optimizado para baja latencia (tiempo real).

## 🚀 Tecnologías Principales
- **Interfaz:** Open WebUI (utilizando su framework de Pipelines nativo en Python).
- **Base de Datos Vectorial:** PostgreSQL con la extensión `pgvector`.
- **Modelos / Inferencia Local:** Ollama / vLLM.
- **Backend de Procesamiento:** Python 3.10+ (Tipado estricto con Pydantic).

---

## 🛠️ Requisitos Previos

Asegúrate de tener instalado en tu sistema:
1. **Python 3.10 o superior**.
2. **PostgreSQL** instalado localmente o corriendo en Docker (con soporte para `pgvector`).
3. **Ollama** instalado y corriendo en segundo plano (`http://localhost:11434`).

---

## ⚙️ Instalación y Configuración

### 1. Clonar el repositorio y acceder a la carpeta
```bash
git clone <url-del-repositorio>
cd Asistente_de_emergencias
```

### 2. Crear y activar el entorno virtual
En Windows:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
En Linux/macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

---

## 🗄️ Configuración de la Base de Datos (PostgreSQL + pgvector)

1. Crea una base de datos llamada `emergencias_db` en tu instancia de PostgreSQL.
2. Si corres PostgreSQL localmente, asegúrate de activar la extensión en la consola de la base de datos:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Configura la variable de entorno `DATABASE_URL` con tus credenciales. Por ejemplo:
   ```powershell
   # Windows PowerShell
   $env:DATABASE_URL="postgresql://usuario:contraseña@localhost:5432/emergencias_db"
   
   # Linux/macOS/Git Bash
   export DATABASE_URL="postgresql://usuario:contraseña@localhost:5432/emergencias_db"
   ```
   *Nota: Si la base de datos no está disponible, el sistema activará automáticamente un **simulador de base de datos en memoria (mock)** para que puedas probar el pipeline sin interrupciones.*

---

## 🧠 Configuración del LLM Local (Ollama)

1. Abre tu terminal y asegúrate de que el servicio de Ollama esté activo.
2. Descarga el modelo recomendado para esta PoC (por defecto `llama3:8b` o similar de 8 mil millones de parámetros):
   ```bash
   ollama pull llama3:8b
   ```
3. Si deseas utilizar otro modelo ligero (ej. `phi3` o `gemma2`), puedes descargarlo e indicar su nombre configurando la variable de entorno o directamente en las opciones del Pipeline en Open WebUI.
   *Nota: Si Ollama no está en ejecución, el cliente LLM caerá automáticamente en un **stream simulado (mock) de baja latencia** que genera tokens a un promedio de 40ms por palabra.*

---

## 🧪 Pruebas y Validación Local

### Ejecutar el Pipeline Aislado (Mocks de verificación)
Puedes validar el funcionamiento básico del pipeline ejecutando directamente:
```bash
# Definir la ruta del proyecto en el PYTHONPATH
$env:PYTHONPATH="."
python src/main.py
```

### Ejecutar la Suite de Evaluación Automatizada
Para validar la latencia y la calidad de la respuesta (guardrails y detección fuera de alcance/judiciales), corre el siguiente comando:
```bash
$env:PYTHONPATH="."
python tests_eval/evaluator.py
```

Esto procesará el dataset ubicado en `tests_eval/test_dataset.json` y generará un reporte de métricas en consola con el siguiente formato:
- **Latencia promedio** por consulta (orientado a tiempo real).
- **Precisión de Guardrails** (validando que redirija consultas fuera de alcance o judiciales al 911).
- **Precisión de Respuestas** (validando presencia de palabras clave del manual de emergencia).

---

## 🔌 Integración con Open WebUI Pipelines

Este proyecto cumple estrictamente con el contrato del framework de **Open WebUI Pipelines**.

Para integrar este RAG como una tubería activa en Open WebUI:
1. Copia el archivo `src/main.py` o cárgalo en tu instancia de Open WebUI Pipelines.
2. En la sección de administración de Open WebUI, edita los valores de las **Valves** (válvulas de configuración) para definir:
   - `DATABASE_URL`: URI de conexión a pgvector.
   - `OLLAMA_URL`: URL del endpoint local de Ollama (ej. `http://localhost:11434`).
   - `MODEL_NAME`: Nombre del modelo a consultar (ej. `llama3:8b`).
3. El pipeline aparecerá disponible como un nuevo "modelo" para chatear en la interfaz de usuario, procesando y recuperando información en tiempo real ante emergencias viales.
