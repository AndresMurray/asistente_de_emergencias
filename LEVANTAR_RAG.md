# 🚀 Guía para Levantar el RAG — Asistente de Emergencias Viales

Este documento explica **qué cambios se hicieron para que el sistema funcione de punta a punta**
y cómo levantarlo desde cero en cualquier máquina del equipo.

---

## 📋 Prerequisitos

- **Docker Desktop** instalado y corriendo (ícono de ballena en la barra de tareas en verde)
- **Python 3.10+** con virtualenv
- **Git** con la rama `main` actualizada (`git pull`)

---

## 🔧 Cambios que se hicieron para la integración

> Estos cambios ya están en `main`. No hay que hacerlos de nuevo.
> Se documentan aquí para que todos entiendan **por qué** se modificaron.

### 1. `src/main.py` — Leer variables de entorno en `Valves`

**Problema:** El `Valves` de Pydantic usaba defaults hardcodeados con `localhost`, que no funciona
dentro de Docker (los servicios se comunican por nombre, ej. `vdb`, `ollama`).

**Solución:** Cambiar `default=` por `default_factory=lambda: os.getenv(...)` para que lea
las variables del `pipelines.env` al arrancar el contenedor.

```python
# ANTES (no funcionaba en Docker)
DATABASE_URL: str = Field(default="postgresql://postgres:postgres@localhost:5432/emergencias_db")

# DESPUÉS (lee del entorno → usa vdb:5432 dentro de Docker, localhost fuera)
DATABASE_URL: str = Field(
    default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/emergencias_db")
)
```

---

### 2. `src/retrieval/search.py` — Endpoint de embeddings actualizado

**Problema:** El endpoint `/api/embeddings` (legacy de Ollama) devuelve error 500 con ciertos
tokens del modelo `paraphrase-multilingual`. Esto hacía que la búsqueda vectorial fallara en
cada consulta.

**Solución:** Usar el endpoint actual `/api/embed` (disponible desde Ollama 0.1.26), que es
robusto y soporta todos los textos correctamente. También cambia el formato:

```python
# ANTES
self.embed_url = f"{self.ollama_url}/api/embeddings"
json={"model": self.embed_model, "prompt": text}
embedding = response.json().get("embedding")        # lista plana

# DESPUÉS
self.embed_url = f"{self.ollama_url}/api/embed"
json={"model": self.embed_model, "input": text}     # "input" en vez de "prompt"
embeddings = response.json().get("embeddings")[0]   # lista de listas → tomar [0]
```

---

### 3. `docker-env/pipelines.env` — Instalar dependencias Python en el contenedor

**Problema:** La imagen base `ghcr.io/open-webui/pipelines` no trae `psycopg2` ni `pgvector`
instalados, por lo que el pipeline caía en modo mock (sin BD real).

**Solución:** Agregar `PIPELINES_REQUIREMENTS_PATH` para que el entrypoint del contenedor
instale automáticamente las dependencias del proyecto al arrancar:

```env
PIPELINES_REQUIREMENTS_PATH=/app/pipelines/requirements.txt
```

---

### 4. `docker-compose.yml` — Montar `requirements.txt` en el contenedor

Para que el contenedor pueda leer el `requirements.txt` del proyecto:

```yaml
volumes:
  - ./requirements.txt:/app/pipelines/requirements.txt   # ← línea agregada
```

---

### 5. `ingest.py` — Script de ingesta de chunks (archivo nuevo)

**Propósito:** Poblar la base de datos vectorial (`pgvector`) con los 372 chunks de los
PDFs procesados por Andrés. Se corre **una sola vez** (o cada vez que haya nuevos documentos).

No modifica ningún archivo existente — simplemente usa el `VectorStoreManager` de Salvador
para leer `data/processed/protocolos_chunks.json` y generar los embeddings.

---

## 🏁 Cómo levantar el sistema desde cero

### PASO 1 — Clonar/actualizar y activar el entorno

```powershell
git checkout main
git pull

# Activar el entorno virtual
.\venv\Scripts\Activate.ps1

# Instalar dependencias (si es la primera vez)
pip install -r requirements.txt
```

### PASO 2 — Crear las carpetas de datos persistentes

> Solo la primera vez. Docker las necesita para montar los volúmenes.

```powershell
New-Item -ItemType Directory -Force -Path appdata\ollama
New-Item -ItemType Directory -Force -Path appdata\owui
New-Item -ItemType Directory -Force -Path appdata\postgress
New-Item -ItemType Directory -Force -Path appdata\postgress_vector
New-Item -ItemType Directory -Force -Path appdata\pipelines
New-Item -ItemType Directory -Force -Path appdata\rawdata
```

### PASO 3 — Levantar los contenedores Docker

```powershell
docker compose up -d
```

Verificar que todos estén `Up`:

```powershell
docker compose ps
```

| Servicio | Puerto | Descripción |
|---|---|---|
| `ollama` | 11434 | LLM local (gemma2:2b) |
| `db` | 5434 | PostgreSQL estándar |
| `vdb` | 5433 | PostgreSQL + pgvector (base vectorial) |
| `pipelines` | 9099 | El pipeline RAG (main.py) |
| `open-webui` | 8180 | Interfaz web |

### PASO 4 — Descargar los modelos en Ollama

> Solo la primera vez. Verificar el nombre del contenedor primero:

```powershell
docker ps --filter "name=ollama" --format "{{.Names}}"
# → asistente_de_emergencias-ollama-1
```

```powershell
# Modelo de embeddings (~562 MB) — para búsqueda vectorial
docker exec -it asistente_de_emergencias-ollama-1 ollama pull paraphrase-multilingual

# Modelo LLM (~1.6 GB) — para generar respuestas
docker exec -it asistente_de_emergencias-ollama-1 ollama pull gemma2:2b
```

### PASO 5 — Ingestar los chunks en pgvector

> Solo la primera vez, o cuando Andrés actualice los PDFs procesados.

```powershell
$env:PYTHONPATH = "."
$env:PYTHONIOENCODING = "utf-8"
python ingest.py
```

Verificar que se insertaron los 372 chunks:

```powershell
docker exec -it asistente_de_emergencias-vdb-1 psql -U postgres -d emergencias_vdb -c "SELECT COUNT(*) FROM protocol_chunks;"
# → 372
```

### PASO 6 — Usar el sistema

Abrir en el navegador: **http://localhost:8180**

1. Primera vez: crear cuenta de administrador (solo local, no sale de tu máquina)
2. Seleccionar modelo **"Early Emergency Response RAG"** en el chat
3. ¡Hacer preguntas!

---

## 💬 Qué preguntas acepta el sistema

El guardrail de Alex acepta preguntas que contengan palabras clave del dominio vial/emergencias.

**✅ Preguntas válidas (in scope):**
- *"¿Qué hacer al llegar al lugar de un accidente vial?"*
- *"¿Cómo actuar ante heridos graves en un choque?"*
- *"¿Qué datos hay que registrar de los vehículos involucrados?"*
- *"¿Cómo evaluar la escena de un siniestro?"*
- *"¿Qué hacer con un motociclista lesionado?"*
- *"¿Cómo actuar ante una hemorragia en el lugar del accidente?"*
- *"¿Qué hacer si hay un herido atrapado en el vehículo?"*

**🚫 Preguntas bloqueadas por guardrail (out of scope):**
- Cualquier consulta con palabras: `judicial`, `perito`, `demanda`, `abogado`, `tribunal`
- Llamadas de broma: `broma`, `joda`, `chiste`
- Preguntas fuera del dominio: *"¿Cuál es la capital de Francia?"*

---

## 🛑 Apagar el sistema

```powershell
docker compose down
```

Para reset completo (borra todos los datos):

```powershell
docker compose down -v
```

> ⚠️ Si hacés `down -v` vas a tener que repetir los **Pasos 4 y 5** la próxima vez.

---

## ⚠️ Problemas comunes

| Síntoma | Causa | Solución |
|---|---|---|
| Pipelines en mock mode | Dependencias no instaladas | Verificar que `PIPELINES_REQUIREMENTS_PATH` esté en `pipelines.env` |
| Respuesta siempre igual (3 fases) | Modo mock activo | Verificar logs: `docker compose logs pipelines --tail=20` |
| `vdb` no arranca healthy | Carpetas `appdata/` no existen | Paso 2 |
| Error 500 en embeddings | Usando endpoint `/api/embeddings` (legacy) | Ya corregido en `search.py` — usar `git pull` |
| Modelo no aparece en Open WebUI | Pipeline no cargó | `docker compose restart pipelines` y refrescar |
| Descargas muy lentas | `gemma2:2b` = 1.6 GB | Esperar, es normal la primera vez |
