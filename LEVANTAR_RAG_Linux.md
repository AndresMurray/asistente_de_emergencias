# Guía para Levantar el RAG en Linux (Fedora/Ubuntu)

Versión Linux de `LEVANTAR_RAG.md`. Los comandos son equivalentes pero adaptados a bash.
Probado en **Fedora 44** con SELinux activo.

---

## Prerequisitos

- **Docker Engine** instalado y corriendo (`sudo systemctl start docker`)
- **Python 3.10+** con virtualenv
- **Git** con la rama `main` actualizada (`git pull`)
- Tu usuario en el grupo `docker` (para no necesitar sudo en cada comando):
  ```bash
  sudo usermod -aG docker $USER
  # cerrar sesión y volver a entrar para que tome efecto
  ```

---

## Antes de empezar (solo Fedora con SELinux)

SELinux bloquea los bind mounts de Docker aunque los permisos Unix sean correctos.
Hay que aplicar el label correcto a los directorios del proyecto **una sola vez**,
y luego registrar la política para que **persista entre reinicios**.

### Aplicar labels (primera vez o después de clonar el repo)

```bash
sudo chcon -Rt svirt_sandbox_file_t appdata/
sudo chcon -Rt svirt_sandbox_file_t src/
sudo chcon -t svirt_sandbox_file_t requirements.txt
```

### Hacer que persista entre reinicios

```bash
sudo dnf install policycoreutils-python-utils   # solo si no está instalado

RUTA=$(pwd)
sudo semanage fcontext -a -t svirt_sandbox_file_t "${RUTA}/appdata(/.*)?"
sudo semanage fcontext -a -t svirt_sandbox_file_t "${RUTA}/src(/.*)?"
sudo semanage fcontext -a -t svirt_sandbox_file_t "${RUTA}/requirements.txt"
sudo restorecon -Rv appdata/ src/ requirements.txt
```

> En Ubuntu/Debian SELinux no está activo por defecto — este paso no es necesario.

---

## PASO 1 — Clonar/actualizar y activar el entorno

```bash
git checkout main
git pull

# Activar el entorno virtual
source venv/bin/activate

# Instalar dependencias (si es la primera vez)
pip install -r requirements.txt
```

---

## PASO 2 — Crear las carpetas de datos persistentes

> Solo la primera vez. Docker las necesita para montar los volúmenes.

```bash
mkdir -p appdata/{ollama,owui,postgress,postgress_vector,pipelines,rawdata}
mkdir -p data/{raw,processed}
```

---

## PASO 3 — Levantar los contenedores Docker

```bash
docker compose up -d
```

Verificar que todos estén `Up`:

```bash
docker compose ps
```

| Servicio | Puerto | Descripción |
|---|---|---|
| `ollama` | 11434 | LLM local |
| `db` | 5434 | PostgreSQL estándar |
| `vdb` | 5433 | PostgreSQL + pgvector (base vectorial) |
| `pipelines` | 9099 | El pipeline RAG (main.py) |
| `open-webui` | 8180 | Interfaz web |

Si `ollama` queda en `Restarting` con error de puerto ocupado, es porque tenés Ollama
instalado nativamente. Paralo antes de levantar Docker:

```bash
sudo systemctl stop ollama
docker compose restart ollama
```

---

## PASO 4 — Descargar los modelos en Ollama

> Solo la primera vez.

```bash
# Modelo de embeddings (~562 MB) — para búsqueda vectorial
docker exec -it asistente_de_emergencias-ollama-1 ollama pull paraphrase-multilingual

# Modelo LLM — para generar respuestas
docker exec -it asistente_de_emergencias-ollama-1 ollama pull gemma2:2b
```

---

## PASO 5 — Obtener los PDFs y generar los chunks

> Solo la primera vez, o cuando haya documentos nuevos.

`data/raw/` y `data/processed/` están en `.gitignore` y no se commitean.
Hay que conseguir los PDFs y colocarlos en `data/raw/`.

Una vez que estén los PDFs, generar los chunks:

```bash
PYTHONPATH=. python src/ingestion/chunking.py
```

Esto crea `data/processed/protocolos_chunks.json`.

---

## PASO 6 — Ingestar los chunks en pgvector

```bash
PYTHONPATH=. PYTHONIOENCODING=utf-8 python ingest.py
```

Verificar que se insertaron correctamente:

```bash
docker exec -it asistente_de_emergencias-vdb-1 psql -U postgres -d emergencias_vdb -c "SELECT COUNT(*) FROM protocol_chunks;"
# → ~372
```

---

## PASO 7 — Usar el sistema

Abrir en el navegador: **http://localhost:8180**

1. Primera vez: crear cuenta de administrador (solo local, no sale de tu máquina)
2. Seleccionar modelo **"Early Emergency Response RAG"** en el chat
3. Hacer preguntas

---

## Apagar el sistema

```bash
docker compose down
```

Para reset completo (borra todos los datos):

```bash
docker compose down -v
```

> Si hacés `down -v` vas a tener que repetir los **Pasos 4, 5 y 6** la próxima vez.

---

## Problemas comunes

| Síntoma | Causa | Solución |
|---|---|---|
| `ollama` en `Restarting`, error de puerto | Ollama nativo corriendo en el host | `sudo systemctl stop ollama` |
| `Permission denied` en logs de ollama o pipelines | SELinux bloqueando bind mounts | Aplicar `chcon` del paso "Antes de empezar" |
| `pipelines` en mock mode | Dependencias no instaladas | Verificar que `PIPELINES_REQUIREMENTS_PATH` esté en `pipelines.env` |
| `FileNotFoundError: protocolos_chunks.json` | No se generaron los chunks | Repetir Paso 5 |
| `vdb` no arranca healthy | Carpetas `appdata/` no existen | Repetir Paso 2 |
| Modelo no aparece en Open WebUI | Pipeline no cargó | `docker compose restart pipelines` y refrescar |
